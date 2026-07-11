from datetime import datetime, timezone
from typing import Any, Dict, Optional

from kaoyan_agent.agents.focus_supervision_agent import FocusSupervisionAgent
from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.repositories.focus import FocusRepository
from kaoyan_agent.repositories.raw_events import RawEventRepository
from kaoyan_agent.repositories.study_tasks import StudyTaskRepository
from kaoyan_agent.schemas.focus import FocusTimerState, FocusTimerStatus
from kaoyan_agent.schemas.study_task import DailyTaskStatus
from kaoyan_agent.services.focus_report_calculator import calculate_focus_report
from kaoyan_agent.services.focus_temporal_tracker import DETECTOR_VERSION


FOCUS_TIMER_STATE_KEY = "focus_timer_state"
FOCUS_DB_SESSION_ID_KEY = "focus_db_session_id"


class FocusWorkflow:
    workflow_name = "focus"

    def __init__(
        self,
        focus_repository: FocusRepository | None = None,
        raw_event_repository: RawEventRepository | None = None,
        supervision_agent: FocusSupervisionAgent | None = None,
        task_repository: StudyTaskRepository | None = None,
        project_id: Optional[int] = None,
        settings: Settings | None = None,
    ):
        self.focus_repository = focus_repository or FocusRepository()
        self.raw_event_repository = raw_event_repository or RawEventRepository()
        self.supervision_agent = supervision_agent or FocusSupervisionAgent()
        self.task_repository = task_repository or StudyTaskRepository()
        self.project_id = project_id
        self.settings = settings or getattr(self.supervision_agent, "settings", None) or get_settings()

    def start_focus_session(
        self,
        task_id: Optional[int],
        planned_minutes: int,
        task_title: str = "",
        subject: str = "",
        project_id: Optional[int] = None,
    ) -> int:
        task = self.task_repository.get(task_id) if task_id is not None else None
        focus_session_id = self.focus_repository.create_session(
            task_id=task_id,
            planned_minutes=planned_minutes,
            task_title=str(task.get("title") or task_title) if task else task_title,
            subject=str(task.get("subject") or subject) if task else subject,
            project_id=project_id if project_id is not None else self.project_id,
        )
        if task_id is not None:
            self.task_repository.update_daily_status(
                task_id,
                DailyTaskStatus.IN_PROGRESS,
            )
        self.focus_repository.record_timeline_event(
            focus_session_id,
            event_type="start",
            note="Focus session started.",
        )
        return focus_session_id

    def get_active_timer_session(self, project_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        return self.focus_repository.get_active_timer_session(
            project_id=project_id if project_id is not None else self.project_id
        )

    def build_timer_state_from_session(self, session: Dict[str, Any]) -> FocusTimerState:
        status = FocusTimerStatus.RUNNING
        if str(session.get("timer_status")) == FocusTimerStatus.PAUSED.value:
            status = FocusTimerStatus.PAUSED
        return FocusTimerState(
            task_id=session.get("task_id"),
            task_title=str(session.get("task_title") or ""),
            subject=str(session.get("subject") or ""),
            planned_minutes=int(session.get("planned_minutes") or 25),
            status=status,
            session_started_at=session.get("started_at"),
            segment_started_at=session.get("segment_started_at"),
            accumulated_seconds=int(session.get("accumulated_seconds") or 0),
            pause_count=int(session.get("pause_count") or 0),
        )

    def restore_active_timer_to_state(self, session_state) -> Optional[FocusTimerState]:
        active = self.get_active_timer_session()
        if not active:
            return None
        state = self.build_timer_state_from_session(active)
        session_state[FOCUS_DB_SESSION_ID_KEY] = int(active["id"])
        self.save_timer_state(session_state, state)
        return state

    def get_timer_state(self, session_state) -> FocusTimerState:
        raw = session_state.get(FOCUS_TIMER_STATE_KEY)
        if raw is None:
            return FocusTimerState()
        if isinstance(raw, FocusTimerState):
            return raw
        return FocusTimerState.model_validate(raw)

    def save_timer_state(self, session_state, state: FocusTimerState) -> None:
        session_state[FOCUS_TIMER_STATE_KEY] = state.model_dump()

    def prepare_timer_from_task(self, session_state, task_id: int) -> FocusTimerState:
        task = self.task_repository.get_daily_task(task_id)
        if task is None:
            raise ValueError(f"Task does not exist: {task_id}")

        state = FocusTimerState(
            task_id=task.id,
            task_title=task.display_title,
            subject=task.subject,
            planned_minutes=task.estimated_minutes,
            status=FocusTimerStatus.IDLE,
        )
        session_state.pop(FOCUS_DB_SESSION_ID_KEY, None)
        self.save_timer_state(session_state, state)
        return state

    def start_timer(self, session_state) -> FocusTimerState:
        state = self.get_timer_state(session_state)
        if not state.task_title:
            raise ValueError("Please select a task before starting the focus timer.")

        now = self._now_iso()
        if state.status == FocusTimerStatus.IDLE:
            active = self.get_active_timer_session()
            if active:
                raise ValueError("There is already an active focus timer.")
            state.session_started_at = now
            state.segment_started_at = now
            state.accumulated_seconds = 0
            state.pause_count = 0
            session_id = self.start_focus_session(
                task_id=state.task_id,
                planned_minutes=state.planned_minutes,
                task_title=state.task_title,
                subject=state.subject,
            )
            session_state[FOCUS_DB_SESSION_ID_KEY] = session_id
        elif state.status == FocusTimerStatus.PAUSED:
            state.segment_started_at = now
        else:
            raise ValueError("The focus timer cannot be started from the current state.")

        state.status = FocusTimerStatus.RUNNING
        self.save_timer_state(session_state, state)
        return state

    def start_timer_for_task(
        self,
        *,
        task_id: Optional[int],
        task_title: str,
        subject: str,
        planned_minutes: int,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        active = self.get_active_timer_session(project_id=project_id)
        if active:
            return {
                "status": "conflict",
                "focus_session": active,
                "message": "已有番茄钟正在进行或暂停中。",
            }

        session_id = self.start_focus_session(
            task_id=task_id,
            planned_minutes=planned_minutes,
            task_title=task_title,
            subject=subject,
            project_id=project_id if project_id is not None else self.project_id,
        )
        session = self.focus_repository.get_session(session_id) or {}
        return {
            "status": "started",
            "focus_session_id": session_id,
            "focus_session": session,
            "message": "番茄钟已开始。",
        }

    def resume_active_timer(self, project_id: Optional[int] = None) -> Dict[str, Any]:
        active = self.get_active_timer_session(project_id=project_id)
        if not active:
            return {"status": "warning", "message": "当前没有可继续的番茄钟。"}
        if str(active.get("timer_status")) != FocusTimerStatus.PAUSED.value:
            return {"status": "warning", "focus_session": active, "message": "当前计时器没有暂停，无需继续。"}

        now = self._now_iso()
        self.focus_repository.update_timer_state(
            int(active["id"]),
            timer_status=FocusTimerStatus.RUNNING.value,
            accumulated_seconds=int(active.get("accumulated_seconds") or 0),
            pause_count=int(active.get("pause_count") or 0),
            segment_started_at=now,
            completion_status="running",
        )
        session = self.focus_repository.get_session(int(active["id"])) or active
        return {"status": "resumed", "focus_session": session, "message": "番茄钟已继续。"}

    def pause_timer(self, session_state) -> FocusTimerState:
        state = self.get_timer_state(session_state)
        if state.status != FocusTimerStatus.RUNNING:
            raise ValueError("The focus timer is not running.")

        state.accumulated_seconds += self._segment_elapsed_seconds(state)
        state.pause_count += 1
        state.segment_started_at = None
        state.status = FocusTimerStatus.PAUSED
        self.save_timer_state(session_state, state)
        focus_session_id = session_state.get(FOCUS_DB_SESSION_ID_KEY)
        if focus_session_id is not None:
            self.focus_repository.update_timer_state(
                int(focus_session_id),
                timer_status=FocusTimerStatus.PAUSED.value,
                accumulated_seconds=state.accumulated_seconds,
                pause_count=state.pause_count,
                segment_started_at=None,
                completion_status="paused",
            )
        return state

    def resume_timer(self, session_state) -> FocusTimerState:
        state = self.get_timer_state(session_state)
        if state.status != FocusTimerStatus.PAUSED:
            raise ValueError("The focus timer is not paused.")

        state.segment_started_at = self._now_iso()
        state.status = FocusTimerStatus.RUNNING
        self.save_timer_state(session_state, state)
        focus_session_id = session_state.get(FOCUS_DB_SESSION_ID_KEY)
        if focus_session_id is not None:
            self.focus_repository.update_timer_state(
                int(focus_session_id),
                timer_status=FocusTimerStatus.RUNNING.value,
                accumulated_seconds=state.accumulated_seconds,
                pause_count=state.pause_count,
                segment_started_at=state.segment_started_at,
                completion_status="running",
            )
        return state

    def end_timer(self, session_state, reflection: str = "") -> Dict[str, Any]:
        state = self.get_timer_state(session_state)
        if state.status == FocusTimerStatus.IDLE:
            raise ValueError("The focus timer has not started.")

        focus_session_id = session_state.get(FOCUS_DB_SESSION_ID_KEY)
        if focus_session_id is None:
            raise ValueError("Missing focus session record; cannot save timer result.")

        actual_seconds = self.get_elapsed_seconds(state)
        actual_minutes = round(actual_seconds / 60)
        completed = actual_seconds >= state.planned_minutes * 60
        completion_status = "completed" if completed else "interrupted"
        report_id = self.finish_focus_session(
            focus_session_id=int(focus_session_id),
            actual_minutes=int(actual_minutes),
            actual_seconds=actual_seconds,
            pause_count=state.pause_count,
            completion_status=completion_status,
            reflection=reflection,
        )
        if state.task_id is not None:
            self.task_repository.update_daily_status(
                state.task_id,
                DailyTaskStatus.DONE if completed else DailyTaskStatus.IN_PROGRESS,
            )

        state.accumulated_seconds = actual_seconds
        state.segment_started_at = None
        state.status = FocusTimerStatus.FINISHED
        self.save_timer_state(session_state, state)
        session_state.pop(FOCUS_DB_SESSION_ID_KEY, None)
        return {
            "focus_session_id": int(focus_session_id),
            "report_id": report_id,
            "actual_seconds": actual_seconds,
            "completed": completed,
            "completion_status": completion_status,
        }

    def safe_pause_timer(self, session_state) -> Dict[str, Any]:
        try:
            state = self.pause_timer(session_state)
            return {"ok": True, "state": state, "message": "番茄钟已暂停。"}
        except ValueError:
            return {"ok": False, "level": "warning", "message": "当前计时器没有运行，无需暂停。"}

    def safe_resume_timer(self, session_state) -> Dict[str, Any]:
        try:
            state = self.resume_timer(session_state)
            return {"ok": True, "state": state, "message": "番茄钟已继续。"}
        except ValueError:
            return {"ok": False, "level": "warning", "message": "当前计时器没有暂停，无需继续。"}

    def safe_end_timer(self, session_state, reflection: str = "") -> Dict[str, Any]:
        try:
            result = self.end_timer(session_state, reflection=reflection)
            return {"ok": True, "result": result, "message": "番茄钟已结束。"}
        except ValueError:
            return {"ok": False, "level": "warning", "message": "当前没有可结束的番茄钟。"}

    def reset_timer(self, session_state) -> None:
        session_state.pop(FOCUS_TIMER_STATE_KEY, None)
        session_state.pop(FOCUS_DB_SESSION_ID_KEY, None)

    def get_elapsed_seconds(self, state: FocusTimerState) -> int:
        elapsed = state.accumulated_seconds
        if state.status == FocusTimerStatus.RUNNING and state.segment_started_at:
            elapsed += self._segment_elapsed_seconds(state)
        return max(elapsed, 0)

    def get_remaining_seconds(self, state: FocusTimerState) -> int:
        return max(state.planned_minutes * 60 - self.get_elapsed_seconds(state), 0)

    def list_recent_sessions(self, limit: int = 20) -> list[Dict[str, Any]]:
        return self.focus_repository.list_recent_sessions(limit=limit)

    def get_stats(self) -> Dict[str, Any]:
        return self.focus_repository.get_stats()

    def record_focus_state(
        self,
        focus_session_id: int,
        state_type: str,
        confidence: float = 0.0,
        focus_score: Optional[int] = None,
        explanation: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        observed_seconds: int = 0,
        detector_version: str = DETECTOR_VERSION,
        force: bool = False,
        min_log_interval_seconds: int = 10,
    ) -> Dict[str, Any]:
        session = self.focus_repository.get_session(focus_session_id)
        if not self.is_session_active(session):
            return {
                "status": "rejected",
                "reason": "session_ended",
                "state_type": state_type,
            }
        state_type = state_type if state_type in {"focused", "away", "distracted", "blocked", "unknown"} else "unknown"
        latest = self.focus_repository.get_latest_state_event(focus_session_id)
        should_write = force or latest is None or str(latest.get("state_type")) != state_type
        if latest and not should_write:
            try:
                latest_at = datetime.fromisoformat(str(latest.get("created_at") or ""))
                if latest_at.tzinfo is None:
                    latest_at = latest_at.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - latest_at).total_seconds()
                should_write = elapsed >= max(1, min_log_interval_seconds)
            except ValueError:
                should_write = True
        if not should_write:
            return {
                "status": "skipped",
                "reason": "debounced",
                "latest_event_id": latest.get("id") if latest else None,
                "state_type": state_type,
            }
        if focus_score is None:
            focus_score = self.default_focus_score(state_type, confidence)
        event_id = self.record_camera_state(
            focus_session_id=focus_session_id,
            state_type=state_type,
            confidence=confidence,
            focus_score=focus_score,
            explanation=explanation,
            metadata=metadata,
            observed_seconds=observed_seconds,
            detector_version=detector_version,
        )
        return {
            "status": "recorded",
            "event_id": event_id,
            "state_type": state_type,
        }

    def record_camera_state(
        self,
        focus_session_id: int,
        state_type: str,
        confidence: float = 0.0,
        focus_score: Optional[int] = None,
        explanation: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        observed_seconds: int = 0,
        detector_version: str = DETECTOR_VERSION,
    ) -> int:
        session = self.focus_repository.get_session(focus_session_id)
        if not self.is_session_active(session):
            raise ValueError("Cannot write supervision evidence to an ended focus session.")
        if focus_score is None:
            focus_score = self.default_focus_score(state_type, confidence)
        event_id = self.focus_repository.record_state_event(
            focus_session_id=focus_session_id,
            state_type=state_type,
            confidence=confidence,
            focus_score=focus_score,
            explanation=explanation,
            observed_seconds=observed_seconds,
            detector_version=detector_version,
        )
        session = session or {}
        event_metadata = {
            "focus_session_id": focus_session_id,
            "state_type": state_type,
            "confidence": confidence,
            "focus_score": focus_score,
            "observed_seconds": max(0, int(observed_seconds)),
            "detector_version": detector_version,
            "evidence_status": "sufficient" if max(0, int(observed_seconds)) > 0 else "insufficient",
        }
        if metadata:
            event_metadata.update(metadata)
        self.raw_event_repository.create(
            project_id=session.get("project_id") or self.project_id,
            content=(
                f"Focus supervision state: {state_type}; "
                f"confidence={confidence:.2f}; "
                f"focus_score={focus_score}; explanation={explanation}"
            ),
            role="system",
            source_type="focus_state_event",
            source_id=event_id,
            metadata=event_metadata,
        )
        return event_id

    def recognize_camera_snapshot(
        self,
        focus_session_id: int,
        image_bytes: bytes,
        mime_type: str = "image/png",
        context: str = "",
    ) -> Dict[str, Any]:
        recognition = self.supervision_agent.recognize_snapshot(
            image_bytes=image_bytes,
            mime_type=mime_type,
            context=context,
        )
        recognition_focus_score = recognition.get("focus_score")
        if recognition_focus_score is None:
            recognition_focus_score = self.default_focus_score(
                recognition["state_type"],
                float(recognition["confidence"]),
            )
            recognition["focus_score"] = recognition_focus_score
        event_id = self.record_camera_state(
            focus_session_id=focus_session_id,
            state_type=recognition["state_type"],
            confidence=float(recognition["confidence"]),
            focus_score=int(recognition_focus_score),
            explanation=recognition["explanation"],
            metadata={
                "recognition_source": recognition.get("recognition_source", "multimodal"),
                "metrics": recognition.get("metrics", {}),
            },
            detector_version=str(recognition.get("detector_version") or DETECTOR_VERSION),
        )
        return {**recognition, "event_id": event_id}

    def finish_focus_session(
        self,
        focus_session_id: int,
        actual_minutes: int,
        pause_count: int,
        completion_status: str,
        reflection: str = "",
        actual_seconds: Optional[int] = None,
        report: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        self.focus_repository.finish_session(
            focus_session_id=focus_session_id,
            actual_minutes=actual_minutes,
            pause_count=pause_count,
            completion_status=completion_status,
            reflection=reflection,
            actual_seconds=actual_seconds,
        )
        session = self.focus_repository.get_session(focus_session_id) or {}
        task_id = session.get("task_id")
        if task_id is not None:
            self.task_repository.update_daily_status(
                int(task_id),
                DailyTaskStatus.DONE
                if completion_status == "completed"
                else DailyTaskStatus.IN_PROGRESS,
            )
        self.focus_repository.record_timeline_event(
            focus_session_id,
            event_type="finish",
            note=reflection,
        )
        session = self.focus_repository.get_session(focus_session_id) or {}
        state_events = self.focus_repository.list_state_events(focus_session_id)
        timeline_events = self.focus_repository.list_timeline_events(focus_session_id)
        narrative = report or self.supervision_agent.generate_report(
            session=session,
            state_events=state_events,
            timeline_events=timeline_events,
        )
        generated_report = calculate_focus_report(
            session,
            state_events,
            narrative,
            minimum_coverage=self.settings.focus_report_min_coverage,
        )
        report_id = self.focus_repository.create_report(focus_session_id, generated_report)
        self.record_report_raw_event(focus_session_id, report_id, generated_report)
        return report_id

    def record_report_raw_event(
        self,
        focus_session_id: int,
        report_id: int,
        report: Dict[str, Any],
    ) -> None:
        session = self.focus_repository.get_session(focus_session_id) or {}
        self.raw_event_repository.create(
            project_id=session.get("project_id") or self.project_id,
            content=(
                "Focus supervision report: "
                f"focus_score={report.get('focus_score', 0)}; "
                f"quality={report.get('focus_quality', '')}; "
                f"summary={report.get('ai_summary', '')}; "
                f"problem_signal={report.get('possible_problem_signal', '')}; "
                f"suggested_action={report.get('suggested_action', '')}"
            ),
            role="system",
            source_type="focus_report",
            source_id=report_id,
            metadata={
                "focus_session_id": focus_session_id,
                "focus_score": report.get("focus_score", 0),
                "focus_quality": report.get("focus_quality", ""),
                "evidence_status": report.get("evidence_status", "insufficient"),
                "coverage_ratio": report.get("coverage_ratio", 0.0),
                "detector_version": report.get("detector_version", DETECTOR_VERSION),
            },
        )

    def get_focus_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        return self.focus_repository.get_report(report_id)

    def list_focus_reports(self, limit: int = 10) -> list[Dict[str, Any]]:
        return self.focus_repository.list_reports(limit=limit)

    def default_focus_score(self, state_type: str, confidence: float) -> int:
        confidence_score = round(max(0.0, min(1.0, float(confidence))) * 100)
        if state_type == "focused":
            return confidence_score
        if state_type == "distracted":
            return max(0, round((1.0 - float(confidence)) * 40))
        if state_type in {"away", "blocked"}:
            return 0
        return 0

    @staticmethod
    def is_session_active(session: Optional[Dict[str, Any]]) -> bool:
        if not session:
            return False
        return (
            str(session.get("timer_status") or "") == "running"
            and not session.get("ended_at")
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _segment_elapsed_seconds(state: FocusTimerState) -> int:
        if not state.segment_started_at:
            return 0
        started = datetime.fromisoformat(state.segment_started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max(int((datetime.now(timezone.utc) - started).total_seconds()), 0)
