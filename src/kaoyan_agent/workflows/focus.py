from typing import Any, Dict, Optional

from kaoyan_agent.agents.focus_supervision_agent import FocusSupervisionAgent
from kaoyan_agent.repositories.focus import FocusRepository
from kaoyan_agent.repositories.raw_events import RawEventRepository


class FocusWorkflow:
    workflow_name = "focus"

    def __init__(
        self,
        focus_repository: FocusRepository | None = None,
        raw_event_repository: RawEventRepository | None = None,
        supervision_agent: FocusSupervisionAgent | None = None,
        project_id: Optional[int] = None,
    ):
        self.focus_repository = focus_repository or FocusRepository()
        self.raw_event_repository = raw_event_repository or RawEventRepository()
        self.supervision_agent = supervision_agent or FocusSupervisionAgent()
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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        event_id = self.focus_repository.record_state_event(
            focus_session_id=focus_session_id,
            state_type=state_type,
            confidence=confidence,
            explanation=explanation,
        )
        session = self.focus_repository.get_session(focus_session_id) or {}
        event_metadata = {
            "focus_session_id": focus_session_id,
            "state_type": state_type,
            "confidence": confidence,
        }
        if metadata:
            event_metadata.update(metadata)

        self.raw_event_repository.create(
            project_id=session.get("project_id") or self.project_id,
            content=(
                f"Focus supervision state: {state_type}; "
                f"confidence={confidence:.2f}; explanation={explanation}"
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
        event_id = self.record_camera_state(
            focus_session_id=focus_session_id,
            state_type=recognition["state_type"],
            confidence=float(recognition["confidence"]),
            explanation=recognition["explanation"],
            metadata={
                "recognition_source": recognition.get("recognition_source", "multimodal"),
                "metrics": recognition.get("metrics", {}),
            },
        )
        return {**recognition, "event_id": event_id}

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
            report_id = self.focus_repository.create_report(focus_session_id, report)
            self.record_report_raw_event(focus_session_id, report_id, report)
            return report_id

        session = self.focus_repository.get_session(focus_session_id) or {}
        state_events = self.focus_repository.list_state_events(focus_session_id)
        timeline_events = self.focus_repository.list_timeline_events(focus_session_id)
        generated_report = self.supervision_agent.generate_report(
            session=session,
            state_events=state_events,
            timeline_events=timeline_events,
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
                "focus_quality": report.get("focus_quality", ""),
            },
        )

    def get_focus_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        return self.focus_repository.get_report(report_id)
