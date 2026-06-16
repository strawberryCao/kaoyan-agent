from __future__ import annotations

from typing import Any, Dict

from kaoyan_agent.ui.components.common import (
    mistake_reason_label,
    render_status_badge,
    sign_level_label,
    source_label,
)


PROBLEM_TYPE_LABELS = {
    "concept_gap": "概念漏洞",
    "execution_issue": "执行问题",
    "planning_issue": "计划问题",
    "method_gap": "方法问题",
    "emotion_issue": "情绪/动力问题",
    "other": "其他问题",
}

CARD_TYPE_LABELS = {
    "daily_sign": "每日签",
    "random_task": "随机小任务",
    "soothing_task": "安抚签",
}


def to_task_view_model(row: Dict[str, Any], date_label: str = "") -> Dict[str, Any]:
    minutes = int(row.get("estimated_minutes") or row.get("minutes") or 25)
    subject = str(row.get("subject") or "未指定")
    return {
        "raw_id": int(row.get("id") or row.get("raw_id") or 0),
        "title": str(row.get("title") or "未命名任务"),
        "subject": subject,
        "minutes": minutes,
        "status": str(row.get("status") or "todo"),
        "status_label": render_status_badge(str(row.get("status") or "todo")),
        "source_label": source_label(str(row.get("source") or "manual")),
        "date_label": date_label or str(row.get("scheduled_date") or ""),
        "detail_text": f"{subject} / {minutes} 分钟",
    }


def to_review_card_view_model(row: Dict[str, Any]) -> Dict[str, Any]:
    priority = int(row.get("review_priority") or 1)
    return {
        "raw_id": int(row.get("id") or row.get("raw_id") or 0),
        "subject": str(row.get("subject") or "未指定科目"),
        "chapter": str(row.get("chapter") or "未指定章节"),
        "question": str(row.get("question") or ""),
        "knowledge_points": str(row.get("knowledge_points") or ""),
        "mistake_reason": str(row.get("mistake_reason") or "unknown"),
        "mistake_reason_label": mistake_reason_label(str(row.get("mistake_reason") or "unknown")),
        "analysis": str(row.get("analysis") or ""),
        "priority_label": f"{priority} / 5",
        "mastery_status": str(row.get("mastery_status") or "unmastered"),
        "mastery_status_label": render_status_badge(str(row.get("mastery_status") or "unmastered")),
    }


def to_problem_view_model(row: Dict[str, Any]) -> Dict[str, Any]:
    evidence = row.get("evidence_refs") or row.get("evidence") or []
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    confidence = float(row.get("confidence") or 0)
    severity = int(row.get("severity") or 1)
    return {
        "raw_id": int(row.get("id") or 0),
        "problem_type_label": PROBLEM_TYPE_LABELS.get(
            str(row.get("problem_type") or "other"),
            str(row.get("problem_type") or "其他问题"),
        ),
        "subject": str(row.get("subject") or "未指定科目"),
        "description": str(row.get("description") or "未命名问题"),
        "root_cause": str(row.get("root_cause") or ""),
        "severity_label": f"{severity} / 5",
        "confidence_label": f"{confidence:.2f}",
        "suggested_action": str(row.get("suggested_action") or ""),
        "status_label": render_status_badge(str(row.get("status") or "open")),
        "evidence_summary": f"{evidence_count} 条证据" if evidence_count else "证据已保留在原始事件中",
    }


def to_motivation_view_model(row: Dict[str, Any]) -> Dict[str, Any]:
    sign_type = str(row.get("sign_type") or "")
    card_type = CARD_TYPE_LABELS.get(sign_type, "签记录")
    content = str(row.get("content") or row.get("sign_text") or row.get("title") or "")
    action = str(row.get("suggested_action") or row.get("action") or "")
    return {
        "raw_id": int(row.get("id") or 0),
        "card_type_label": card_type,
        "title": sign_level_label(str(row.get("sign_level") or "")) if sign_type == "daily_sign" else card_type,
        "main_text": content,
        "advice": str(row.get("today_advice") or row.get("reason") or ""),
        "action": action,
        "minutes": int(row.get("estimated_minutes") or 0),
        "fallback_hint": "当前使用本地备用结果。" if row.get("generation_error") else "",
    }
