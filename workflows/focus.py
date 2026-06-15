from typing import Any, Dict, Optional

from kaoyan_agent.repositories.focus import FocusRepository


class FocusWorkflow:
    workflow_name = "focus"

    def __init__(
        self,
        focus_repository: FocusRepository | None = None,
        project_id: Optional[int] = None,
    ):
        self.focus_repository = focus_repository or FocusRepository()
        self.project_id = project_id

    def start_focus_session(
        self,
        task_id: Optional[int],
        planned_minutes: int,
        project_id: Optional[int] = None,
    ) -> int:
        focus_session_id = self.focus_repository.create_session(
            task_id=task_id,
            planned_minutes=planned_minutes,
            project_id=project_id if project_id is not None else self.project_id,
        )
        self.focus_repository.record_timeline_event(
            focus_session_id,
            event_type="start",
            note="Focus session started.",
        )
        return focus_session_id

    def record_camera_state(
        self,
        focus_session_id: int,
        state_type: str,
        confidence: float = 0.0,
        explanation: str = "",
    ) -> int:
        return self.focus_repository.record_state_event(
            focus_session_id=focus_session_id,
            state_type=state_type,
            confidence=confidence,
            explanation=explanation,
        )

    def finish_focus_session(
        self,
        focus_session_id: int,
        actual_minutes: int,
        pause_count: int,
        completion_status: str,
        reflection: str = "",
        report: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        self.focus_repository.finish_session(
            focus_session_id=focus_session_id,
            actual_minutes=actual_minutes,
            pause_count=pause_count,
            completion_status=completion_status,
            reflection=reflection,
        )
        self.focus_repository.record_timeline_event(
            focus_session_id,
            event_type="finish",
            note=reflection,
        )
        if report:
            return self.focus_repository.create_report(focus_session_id, report)
        return None


