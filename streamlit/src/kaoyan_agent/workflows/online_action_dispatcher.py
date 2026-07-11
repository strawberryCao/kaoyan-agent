from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Optional

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.repositories.online_actions import OnlineActionRepository
from kaoyan_agent.repositories.pending_actions import PendingActionRepository
from kaoyan_agent.schemas.contracts import RouterDecision
from kaoyan_agent.schemas.online_actions import ActionIntentDecision, OnlineActionResult
from kaoyan_agent.workflows.focus import FocusWorkflow
from kaoyan_agent.workflows.planning import PlanningWorkflow


SUBJECT_KEYWORDS = {
    "数学": ("数学", "积分", "极限", "线代", "概率", "高数"),
    "英语": ("英语", "单词", "阅读", "作文", "翻译"),
    "政治": ("政治", "马原", "史纲", "毛中特", "思修"),
    "408": ("408", "操作系统", "计网", "组成原理", "数据结构"),
}


class OnlineActionDispatcher:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        planning_workflow: Optional[PlanningWorkflow] = None,
        focus_workflow: Optional[FocusWorkflow] = None,
        action_repository: Optional[OnlineActionRepository] = None,
        pending_repository: Optional[PendingActionRepository] = None,
    ):
        self.settings = settings or get_settings()
        self.planning_workflow = planning_workflow or PlanningWorkflow(self.settings)
        self.focus_workflow = focus_workflow or FocusWorkflow()
        self.action_repository = action_repository or OnlineActionRepository()
        self.pending_repository = pending_repository or PendingActionRepository()

    def dispatch(
        self,
        *,
        decision: RouterDecision,
        user_input: str,
        session_id: int,
        user_event_id: int,
        project_id: Optional[int] = None,
        intent_decision: Optional[ActionIntentDecision] = None,
    ) -> Optional[OnlineActionResult]:
        route = decision.route
        intent_decision = intent_decision or self.classify_intent(decision, user_input)
        if intent_decision.intent in {"no_action"}:
            return None

        if route == "practice_review":
            action_type = intent_decision.action_type or "create_review_card"
        elif route == "focus":
            action_type = "focus_resume" if "继续" in user_input else "focus_start"
        elif route == "planning":
            action_type = "create_task"
        elif route in {"motivation", "score_trend"}:
            action_type = f"{route}_guide"
        elif decision.need_search or decision.need_file or decision.need_tools:
            action_type = "unsupported_tool_request"
        else:
            return None

        action_key = self.build_action_key(
            session_id=session_id,
            user_event_id=user_event_id,
            route=route,
            action_type=action_type,
            user_input=user_input,
        )
        existing = self.action_repository.get_by_key(action_key)
        if existing:
            stored = existing.get("result") or {}
            return OnlineActionResult(
                action_type=str(stored.get("action_type") or action_type),
                status="idempotent",
                user_message=str(stored.get("user_message") or "这条消息已经处理过，未重复执行。"),
                data=dict(stored.get("data") or {}),
                error_message=str(stored.get("error_message") or ""),
                debug={**dict(stored.get("debug") or {}), "idempotent": True},
                intent=str(stored.get("intent") or intent_decision.intent),
                pending_action_id=stored.get("pending_action_id"),
                requires_chat_answer=bool(stored.get("requires_chat_answer")),
            )

        content_hash = hashlib.sha256(
            " ".join(user_input.strip().split()).encode("utf-8")
        ).hexdigest()[:16]
        try:
            result = self._execute(
                route=route,
                action_type=action_type,
                user_input=user_input,
                project_id=project_id,
                session_id=session_id,
                user_event_id=user_event_id,
                intent_decision=intent_decision,
            )
        except Exception as exc:
            result = OnlineActionResult(
                action_type=action_type,
                status="failed",
                user_message="已识别到你的请求，但执行时遇到问题。你可以稍后重试，或到对应页面手动操作。",
                error_message=str(exc),
                debug={"exception_type": exc.__class__.__name__},
                intent=intent_decision.intent,
            )
        result.debug.setdefault("content_hash", content_hash)
        result.debug.setdefault("action_intent", intent_decision.to_dict())
        if not result.intent:
            result.intent = intent_decision.intent

        self.action_repository.create(
            action_key=action_key,
            route=route,
            action_type=action_type,
            status=result.status,
            result=result.to_dict(),
            user_event_id=user_event_id,
            session_id=session_id,
            project_id=project_id,
            error_message=result.error_message,
        )
        return result

    def classify_intent(
        self,
        decision: RouterDecision,
        user_input: str,
    ) -> ActionIntentDecision:
        route = decision.route
        if route == "focus":
            return ActionIntentDecision(
                intent="explicit_action",
                action_type="focus_resume" if "继续" in user_input else "focus_start",
                reason="focus requests are explicit timer commands",
                should_execute=True,
            )
        if route == "planning":
            return ActionIntentDecision(
                intent="explicit_action",
                action_type="create_task",
                reason="planning requests create or guide today's task",
                should_execute=True,
            )
        if route in {"motivation", "score_trend"} or decision.need_search or decision.need_file or decision.need_tools:
            return ActionIntentDecision(
                intent="explicit_action",
                action_type=f"{route}_guide" if route in {"motivation", "score_trend"} else "unsupported_tool_request",
                reason="route has deterministic page guidance",
                should_execute=True,
            )
        if route != "practice_review":
            return ActionIntentDecision(intent="no_action", reason="normal chat")

        parsed = self.parse_practice_review(user_input)
        explicit = self.is_explicit_mistake_card_command(user_input)
        asks_suggestion = any(
            phrase in user_input
            for phrase in ("要不要记错题", "是否要记错题", "应该记错题", "以后怎么复习", "怎么复习")
        )
        asks_answer = any(
            phrase in user_input
            for phrase in ("不会", "不会做", "看懂答案", "做不出来", "为什么", "原因是")
        )
        missing_for_save = [
            name
            for name in ("question", "user_reason")
            if not parsed.get(name)
        ]
        if explicit:
            if missing_for_save:
                return ActionIntentDecision(
                    intent="need_clarification",
                    action_type="create_review_card",
                    reason="explicit card command lacks question or mistake evidence",
                    parsed=parsed,
                    missing_fields=missing_for_save,
                )
            return ActionIntentDecision(
                intent="explicit_action",
                action_type="create_review_card",
                reason="user explicitly asked to save a mistake card",
                parsed=parsed,
                should_execute=True,
            )
        if asks_suggestion:
            if not parsed.get("question"):
                return ActionIntentDecision(
                    intent="need_clarification",
                    action_type="create_review_card",
                    reason="suggestion request lacks question evidence",
                    parsed=parsed,
                    missing_fields=["question"],
                )
            return ActionIntentDecision(
                intent="suggest_action",
                action_type="create_review_card",
                reason="user is asking whether this should become a review card",
                parsed=parsed,
                requires_chat_answer=True,
                should_create_pending=True,
            )
        if asks_answer:
            if not parsed.get("question"):
                return ActionIntentDecision(
                    intent="need_clarification",
                    action_type="create_review_card",
                    reason="answer-first request lacks enough question evidence",
                    parsed=parsed,
                    missing_fields=["question"],
                )
            return ActionIntentDecision(
                intent="answer_first_then_suggest",
                action_type="create_review_card",
                reason="user is primarily asking for help, not issuing a save command",
                parsed=parsed,
                requires_chat_answer=True,
                should_create_pending=True,
            )
        return ActionIntentDecision(intent="no_action", reason="practice route but no actionable review intent", parsed=parsed)

    def _execute(
        self,
        *,
        route: str,
        action_type: str,
        user_input: str,
        project_id: Optional[int],
        session_id: int,
        user_event_id: int,
        intent_decision: ActionIntentDecision,
    ) -> OnlineActionResult:
        if route == "focus":
            return self._handle_focus(user_input, project_id)
        if route == "planning":
            return self._handle_planning(user_input, project_id)
        if route == "practice_review":
            return self._handle_practice_review(
                user_input=user_input,
                project_id=project_id,
                session_id=session_id,
                user_event_id=user_event_id,
                intent_decision=intent_decision,
            )
        if route == "motivation":
            return OnlineActionResult(
                action_type=action_type,
                status="unsupported",
                user_message="已识别为「Fortune Card / 上岸签」请求。请打开侧边栏「Fortune Card」抽每日签、生成随机微行动或安抚签。",
            )
        if route == "score_trend":
            return OnlineActionResult(
                action_type=action_type,
                status="unsupported",
                user_message="已识别为「成绩趋势」请求。请打开侧边栏「成绩趋势」记录分数并查看趋势。",
            )
        return OnlineActionResult(
            action_type=action_type,
            status="unsupported",
            user_message="已识别到需要外部工具或文件能力，但当前演示版尚未接入完整执行链路。",
        )

    def _handle_focus(self, user_input: str, project_id: Optional[int]) -> OnlineActionResult:
        active = self.focus_workflow.get_active_timer_session(project_id=project_id)
        if active and str(active.get("timer_status")) == "running":
            elapsed = self.focus_workflow.get_elapsed_seconds(
                self.focus_workflow.build_timer_state_from_session(active)
            )
            return OnlineActionResult(
                action_type="focus_start",
                status="warning",
                user_message=(
                    f"当前已有番茄钟正在进行：{active.get('task_title') or '临时专注任务'}，"
                    f"已专注 {self.format_minutes(elapsed)}。你可以在「督学模式」查看、暂停或结束。"
                ),
                data={"focus_session_id": active.get("id"), "timer_status": "running"},
            )

        if active and str(active.get("timer_status")) == "paused":
            if "继续" in user_input:
                resumed = self.focus_workflow.resume_active_timer(project_id=project_id)
                session = resumed.get("focus_session") or active
                return OnlineActionResult(
                    action_type="focus_resume",
                    status="success" if resumed.get("status") == "resumed" else "warning",
                    user_message=(
                        f"已继续番茄钟：{session.get('task_title') or '临时专注任务'}。"
                        "你可以在「督学模式」查看、暂停或结束。"
                    ),
                    data={"focus_session_id": session.get("id"), "timer_status": session.get("timer_status")},
                )
            return OnlineActionResult(
                action_type="focus_start",
                status="warning",
                user_message="当前有一个暂停中的番茄钟。请先在「督学模式」结束它，或发送“继续番茄钟”。",
                data={"focus_session_id": active.get("id"), "timer_status": "paused"},
            )

        minutes = self.parse_minutes(user_input, default=25)
        title = self.parse_focus_title(user_input)
        subject = self.infer_subject(user_input)
        task_id = self.create_or_reuse_today_task(
            title=title,
            subject=subject,
            minutes=minutes,
            source="chat",
            project_id=project_id,
        )
        started = self.focus_workflow.start_timer_for_task(
            task_id=task_id,
            task_title=title,
            subject=subject,
            planned_minutes=minutes,
            project_id=project_id,
        )
        if started.get("status") != "started":
            return OnlineActionResult(
                action_type="focus_start",
                status="warning",
                user_message="当前已有番茄钟，未重复创建。请在「督学模式」查看当前计时器。",
                data=started,
            )
        return OnlineActionResult(
            action_type="focus_start",
            status="success",
            user_message=f"已开始 {minutes} 分钟番茄钟：{title}。你可以在「督学模式」查看、暂停或结束。",
            data={
                "task_id": task_id,
                "task_title": title,
                "subject": subject,
                "planned_minutes": minutes,
                "focus_session_id": started.get("focus_session_id"),
            },
        )

    def _handle_planning(self, user_input: str, project_id: Optional[int]) -> OnlineActionResult:
        minutes = self.parse_minutes(user_input, default=25)
        title = self.parse_task_title(user_input)
        if not title:
            return OnlineActionResult(
                action_type="create_task",
                status="needs_input",
                user_message="你想创建什么今日任务？请补充一个任务标题。",
            )
        subject = self.infer_subject(user_input)
        task_id = self.create_or_reuse_today_task(
            title=title,
            subject=subject,
            minutes=minutes,
            source="chat",
            project_id=project_id,
        )
        return OnlineActionResult(
            action_type="create_task",
            status="success",
            user_message=f"已加入今日任务：{title}，预计 {minutes} 分钟。",
            data={
                "task_id": task_id,
                "title": title,
                "subject": subject,
                "planned_minutes": minutes,
                "status": "todo",
                "source": "chat",
            },
        )

    def _handle_practice_review(
        self,
        *,
        user_input: str,
        project_id: Optional[int],
        session_id: int,
        user_event_id: int,
        intent_decision: ActionIntentDecision,
    ) -> OnlineActionResult:
        parsed = intent_decision.parsed or self.parse_practice_review(user_input)
        if intent_decision.intent == "need_clarification":
            return OnlineActionResult(
                action_type="create_review_card",
                status="needs_input",
                user_message="我可以帮你整理错题卡。请补充题目或错误证据，最好包含题目、科目/章节，以及你觉得卡住的原因。",
                data={
                    "action_intent": intent_decision.to_dict(),
                    "missing_fields": intent_decision.missing_fields,
                    "parsed": parsed,
                },
                intent=intent_decision.intent,
            )

        if intent_decision.should_create_pending:
            payload = self.build_pending_practice_payload(parsed, user_input)
            pending_key = self.build_pending_key(
                session_id=session_id,
                user_event_id=user_event_id,
                action_type="create_review_card",
            )
            pending = self.pending_repository.create_pending(
                pending_key=pending_key,
                action_type="create_review_card",
                payload=payload,
                session_id=session_id,
                user_event_id=user_event_id,
                project_id=project_id,
            )
            return OnlineActionResult(
                action_type="create_review_card",
                status="pending_confirmation",
                user_message="我会先回答你的问题，再给出是否保存为错题卡的建议。",
                data={
                    "action_intent": intent_decision.to_dict(),
                    "pending_action": pending,
                    "pending_action_payload": payload,
                },
                intent=intent_decision.intent,
                pending_action_id=pending.get("id"),
                requires_chat_answer=True,
            )

        missing = [
            name
            for name in ("subject", "chapter", "question", "user_reason")
            if not parsed.get(name)
        ]
        if missing:
            return OnlineActionResult(
                action_type="create_review_card",
                status="needs_input",
                user_message="请补充题目或错误证据，最好包含科目、章节和你认为的错因，我再帮你生成错题卡。",
                data={"missing_fields": missing},
                intent=intent_decision.intent,
            )

        card = self.planning_workflow.generate_and_save_practice_card(
            subject=parsed["subject"],
            chapter=parsed["chapter"],
            question=parsed["question"],
            user_reason=parsed["user_reason"],
            project_id=project_id,
        )
        return OnlineActionResult(
            action_type="create_review_card",
            status="success",
            user_message=(
                "已生成错题卡："
                f"知识点 {card.get('knowledge_points', '未归纳')}，"
                f"错因 {card.get('mistake_reason', 'unknown')}，"
                f"复习优先级 {card.get('review_priority', 1)}。"
                "你可以在「错题复盘」查看。"
            ),
            data={"card": card},
            intent=intent_decision.intent,
        )

    @staticmethod
    def build_pending_key(
        *,
        session_id: int,
        user_event_id: int,
        action_type: str,
    ) -> str:
        return f"pending:session:{session_id}:event:{user_event_id}:action:{action_type}"

    @classmethod
    def build_pending_practice_payload(
        cls,
        parsed: Dict[str, str],
        user_input: str,
    ) -> Dict[str, Any]:
        question = parsed.get("question") or cls.clean_title(user_input)
        user_reason = parsed.get("user_reason") or "用户表示这题不会或做不出来。"
        return {
            "subject": parsed.get("subject") or "未指定",
            "chapter": parsed.get("chapter") or "未指定",
            "question": question,
            "question_summary": question[:80],
            "user_reason": user_reason,
            "mistake_reason": "method_gap" if "换元" in user_reason or "方法" in user_reason else "unknown",
            "knowledge_points": parsed.get("chapter") or "",
            "review_priority": 3,
            "source_text": user_input,
        }

    def create_or_reuse_today_task(
        self,
        *,
        title: str,
        subject: str,
        minutes: int,
        source: str,
        project_id: Optional[int],
    ) -> int:
        today = self.local_today()
        return self.planning_workflow.create_task(
            title=title,
            subject=subject,
            estimated_minutes=minutes,
            source=source,
            status="todo",
            scheduled_date=today,
            project_id=project_id,
        )

    @staticmethod
    def build_action_key(
        *,
        session_id: int,
        user_event_id: int,
        route: str,
        action_type: str,
        user_input: str,
    ) -> str:
        return f"session:{session_id}:event:{user_event_id}:route:{route}:action:{action_type}"

    @staticmethod
    def is_explicit_mistake_card_command(text: str) -> bool:
        return any(
            phrase in text
            for phrase in (
                "帮我生成错题卡",
                "生成错题卡",
                "保存成错题卡",
                "保存为错题卡",
                "加入错题本",
                "加到错题本",
                "把这题加入错题本",
                "记入错题",
                "写进错题",
                "整理成错题卡",
            )
        )

    @staticmethod
    def parse_minutes(text: str, default: int = 25) -> int:
        match = re.search(r"(\d{1,3})\s*(?:分钟|分|mins?|minutes?)", text, re.IGNORECASE)
        if not match:
            return default
        return max(1, min(480, int(match.group(1))))

    @staticmethod
    def infer_subject(text: str) -> str:
        explicit = re.search(r"科目[:：]?\s*([^，,。；;\s]+)", text)
        if explicit:
            return explicit.group(1).strip()
        for subject, keywords in SUBJECT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return subject
        return ""

    @classmethod
    def parse_focus_title(cls, text: str) -> str:
        title = cls.strip_common_action_words(text)
        title = re.sub(r"(开始|继续|我要|我想|用|番茄钟|计时|专注)", "", title)
        title = re.sub(r"\d{1,3}\s*(分钟|分|mins?|minutes?)", "", title, flags=re.IGNORECASE)
        title = cls.clean_title(title)
        return title or "临时专注任务"

    @classmethod
    def parse_task_title(cls, text: str) -> str:
        title = cls.strip_common_action_words(text)
        title = re.sub(r"\d{1,3}\s*(分钟|分|mins?|minutes?)", "", title, flags=re.IGNORECASE)
        title = cls.clean_title(title)
        if title in {"任务", "一个任务", "今日任务"}:
            return ""
        return title

    @classmethod
    def parse_practice_review(cls, text: str) -> Dict[str, str]:
        subject = cls.infer_subject(text)
        chapter_match = re.search(r"章节[:：]?\s*([^，,。；;\s]+)", text)
        chapter = chapter_match.group(1).strip() if chapter_match else ""
        if not chapter and "积分" in text:
            chapter = "积分"
        reason_match = re.search(r"原因是([^，,。；;]+)", text)
        user_reason = reason_match.group(1).strip() if reason_match else ""
        question = text
        if reason_match:
            question = text[: reason_match.start()]
        question = re.sub(r"(帮我)?生成错题卡|帮我|这道|这题|不会做|不会", "", question)
        question = cls.clean_title(question)
        return {
            "subject": subject,
            "chapter": chapter,
            "question": question,
            "user_reason": user_reason,
        }

    @staticmethod
    def strip_common_action_words(text: str) -> str:
        value = text.strip()
        prefixes = (
            "帮我创建一个",
            "帮我创建",
            "创建一个",
            "创建",
            "今天安排",
            "给我加一个",
            "给我加",
            "今日任务加上",
            "今日任务添加",
            "今日任务",
            "请",
            "帮我",
            "我要",
            "我想",
        )
        for prefix in prefixes:
            if value.startswith(prefix):
                value = value[len(prefix) :]
                break
        return value

    @staticmethod
    def clean_title(value: str) -> str:
        value = re.sub(r"[，,。；;：:！!？?]+", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value[:60]

    @staticmethod
    def local_today() -> str:
        return datetime.now().astimezone().date().isoformat()

    @staticmethod
    def format_minutes(seconds: int) -> str:
        minutes = max(0, int(seconds)) // 60
        remaining = max(0, int(seconds)) % 60
        return f"{minutes:02d}:{remaining:02d}"
