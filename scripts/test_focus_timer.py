from db.database import init_db, get_connection
from workflows.daily_task_workflow import DailyTaskWorkflow
from workflows.focus_timer_workflow import FocusTimerWorkflow
from schemas.task import DailyTaskCreate


class FakeSession:
    def __init__(self):
        self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __setitem__(self, key, value):
        self._data[key] = value

    def pop(self, key, default=None):
        return self._data.pop(key, default)


def main() -> None:
    init_db()

    task_workflow = DailyTaskWorkflow()
    task = task_workflow.add_task(
        DailyTaskCreate(subject="数学", task="测试任务", estimated_minutes=25)
    )
    print("Created task:", task.id, task.display_title)

    session_state = FakeSession()
    focus_workflow = FocusTimerWorkflow()
    focus_workflow.prepare_from_task(session_state, task.id)
    focus_workflow.start_timer(session_state)
    focus_workflow.pause_timer(session_state)
    focus_workflow.resume_timer(session_state)
    record = focus_workflow.end_timer(session_state, reflection="测试心得")
    print(
        "Finished:",
        record.actual_seconds,
        record.completed,
        record.reflection,
    )

    stats = focus_workflow.get_stats()
    print("Stats:", stats.today_sessions, stats.today_focus_minutes)

    with get_connection() as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        print("Tables:", tables)

    print("ALL OK")


if __name__ == "__main__":
    main()
