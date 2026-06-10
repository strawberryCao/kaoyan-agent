from datetime import datetime, timezone
from typing import Optional

from repositories.focus_session_repository import FocusSessionRepository
from repositories.task_repository import TaskRepository
from schemas.focus_session import (
    FocusSessionCreate,
    FocusSessionFinish,
    FocusSessionRecord,
    FocusStats,
    FocusTimerState,
    FocusTimerStatus,
)
from schemas.task import DailyTaskRecord, DailyTaskStatus


FOCUS_TIMER_STATE_KEY = "focus_timer_state"
FOCUS_DB_SESSION_ID_KEY = "focus_db_session_id"


class FocusTimerWorkflow:
    def __init__(
        self,
        task_repository: Optional[TaskRepository] = None,
        focus_repository: Optional[FocusSessionRepository] = None,
    ) -> None:
        self.task_repository = task_repository or TaskRepository()
        self.focus_repository = focus_repository or FocusSessionRepository()

    def get_timer_state(self, session_state) -> FocusTimerState:
        raw = session_state.get(FOCUS_TIMER_STATE_KEY)
        if raw is None:
            return FocusTimerState()
        if isinstance(raw, FocusTimerState):
            return raw
        return FocusTimerState.model_validate(raw)

    def save_timer_state(self, session_state, state: FocusTimerState) -> None:
        session_state[FOCUS_TIMER_STATE_KEY] = state.model_dump()

    def prepare_from_task(self, session_state, task_id: int) -> FocusTimerState:
        task = self.task_repository.get_task_by_id(task_id)
        if task is None:
            raise ValueError(f"任务不存在: {task_id}")

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
            raise ValueError("请先选择任务")

        now = self._now_iso()
        if state.status == FocusTimerStatus.IDLE:
            state.session_started_at = now
            state.segment_started_at = now
            state.accumulated_seconds = 0
            state.pause_count = 0

            payload = FocusSessionCreate(
                task_id=state.task_id,
                task_title=state.task_title,
                subject=state.subject,
                planned_minutes=state.planned_minutes,
            )
            session_id = self.focus_repository.create_session(payload, started_at=now)
            session_state[FOCUS_DB_SESSION_ID_KEY] = session_id

            if state.task_id is not None:
                self.task_repository.update_task_status(
                    state.task_id,
                    DailyTaskStatus.IN_PROGRESS,
                )
        elif state.status == FocusTimerStatus.PAUSED:
            state.segment_started_at = now
        else:
            raise ValueError("当前状态无法开始")

        state.status = FocusTimerStatus.RUNNING
        self.save_timer_state(session_state, state)
        return state

    def pause_timer(self, session_state) -> FocusTimerState:
        state = self.get_timer_state(session_state)
        if state.status != FocusTimerStatus.RUNNING:
            raise ValueError("计时未在进行中")

        elapsed = self._segment_elapsed_seconds(state)
        state.accumulated_seconds += elapsed
        state.pause_count += 1
        state.segment_started_at = None
        state.status = FocusTimerStatus.PAUSED
        self.save_timer_state(session_state, state)
        return state

    def resume_timer(self, session_state) -> FocusTimerState:
        state = self.get_timer_state(session_state)
        if state.status != FocusTimerStatus.PAUSED:
            raise ValueError("计时未处于暂停状态")

        state.segment_started_at = self._now_iso()
        state.status = FocusTimerStatus.RUNNING
        self.save_timer_state(session_state, state)
        return state

    def end_timer(
        self,
        session_state,
        reflection: str = "",
    ) -> FocusSessionRecord:
        state = self.get_timer_state(session_state)
        if state.status == FocusTimerStatus.IDLE:
            raise ValueError("尚未开始督学")

        actual_seconds = self.get_elapsed_seconds(state)
        ended_at = self._now_iso()
        planned_seconds = state.planned_minutes * 60
        completed = actual_seconds >= planned_seconds

        db_session_id = session_state.get(FOCUS_DB_SESSION_ID_KEY)
        if db_session_id is None:
            raise ValueError("缺少专注记录，无法保存")

        payload = FocusSessionFinish(
            actual_seconds=actual_seconds,
            pause_count=state.pause_count,
            completed=completed,
            reflection=reflection,
        )
        record = self.focus_repository.finish_session(
            int(db_session_id),
            payload,
            ended_at=ended_at,
        )

        if state.task_id is not None:
            next_status = (
                DailyTaskStatus.DONE if completed else DailyTaskStatus.IN_PROGRESS
            )
            self.task_repository.update_task_status(state.task_id, next_status)

        state.status = FocusTimerStatus.FINISHED
        self.save_timer_state(session_state, state)
        session_state.pop(FOCUS_DB_SESSION_ID_KEY, None)
        return record

    def reset_timer(self, session_state) -> None:
        session_state.pop(FOCUS_TIMER_STATE_KEY, None)
        session_state.pop(FOCUS_DB_SESSION_ID_KEY, None)

    def get_elapsed_seconds(self, state: FocusTimerState) -> int:
        elapsed = state.accumulated_seconds
        if state.status == FocusTimerStatus.RUNNING and state.segment_started_at:
            elapsed += self._segment_elapsed_seconds(state)
        return max(elapsed, 0)

    def get_remaining_seconds(self, state: FocusTimerState) -> int:
        planned_seconds = state.planned_minutes * 60
        return max(planned_seconds - self.get_elapsed_seconds(state), 0)

    def get_stats(self) -> FocusStats:
        return self.focus_repository.get_stats()

    def list_recent_sessions(self, limit: int = 20):
        return self.focus_repository.list_recent_sessions(limit=limit)

    def get_task_for_timer(self, task_id: int) -> DailyTaskRecord:
        task = self.task_repository.get_task_by_id(task_id)
        if task is None:
            raise ValueError(f"任务不存在: {task_id}")
        return task

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _segment_elapsed_seconds(state: FocusTimerState) -> int:
        if not state.segment_started_at:
            return 0
        started = datetime.fromisoformat(state.segment_started_at)
        now = datetime.now(timezone.utc)
        return max(int((now - started).total_seconds()), 0)
