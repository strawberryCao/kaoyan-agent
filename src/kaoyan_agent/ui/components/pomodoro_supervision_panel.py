import threading
import time
from datetime import datetime
from io import BytesIO

import streamlit as st

from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.workflows.focus import FocusWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


SUPERVISION_STATUSES = ["completed", "interrupted", "failed"]
STATE_LABELS = ["focused", "away", "distracted", "blocked", "unknown"]
STATE_LABEL_ZH = {
    "focused": "专注",
    "away": "离开画面",
    "distracted": "疑似分心",
    "blocked": "摄像头遮挡无法判断",
    "unknown": "无法判断",
}


class AutoFocusFrameProcessor:
    """Keep only the latest camera frame in memory for periodic recognition."""

    def __init__(self):
        self._lock = threading.Lock()
        self._latest_image_bytes = b""
        self._latest_frame_at = 0.0
        self._last_capture_at = 0.0
        self._last_recognition_at = 0.0
        self._recognizing = False
        self._focus_session_id = 0
        self._camera_context = ""
        self._interval_seconds = 60
        self._latest_recognition = None
        self._latest_error = ""
        self._workflow = FocusWorkflow()

    def configure(
        self,
        focus_session_id: int,
        camera_context: str,
        interval_seconds: int,
    ) -> None:
        with self._lock:
            self._focus_session_id = focus_session_id
            self._camera_context = camera_context
            self._interval_seconds = max(15, int(interval_seconds))

    def recv(self, frame):
        now = time.time()
        if now - self._last_capture_at >= 2:
            image = frame.to_image()
            image.thumbnail((640, 640))
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=80)
            image_bytes = buffer.getvalue()
            with self._lock:
                self._latest_image_bytes = image_bytes
                self._latest_frame_at = now
            self._last_capture_at = now
            self._maybe_start_recognition(image_bytes, now)
        return frame

    def latest_snapshot(self) -> tuple[bytes, str, float]:
        with self._lock:
            return self._latest_image_bytes, "image/jpeg", self._latest_frame_at

    def latest_status(self) -> dict:
        with self._lock:
            return {
                "latest_frame_at": self._latest_frame_at,
                "last_recognition_at": self._last_recognition_at,
                "recognizing": self._recognizing,
                "latest_recognition": self._latest_recognition,
                "latest_error": self._latest_error,
                "interval_seconds": self._interval_seconds,
            }

    def _maybe_start_recognition(self, image_bytes: bytes, now: float) -> None:
        with self._lock:
            if not self._focus_session_id or self._recognizing:
                return
            if now - self._last_recognition_at < self._interval_seconds:
                return
            self._recognizing = True
            self._last_recognition_at = now
            focus_session_id = self._focus_session_id
            camera_context = self._camera_context

        thread = threading.Thread(
            target=self._recognize_snapshot,
            args=(focus_session_id, image_bytes, camera_context),
            daemon=True,
        )
        thread.start()

    def _recognize_snapshot(
        self,
        focus_session_id: int,
        image_bytes: bytes,
        camera_context: str,
    ) -> None:
        try:
            recognition = self._workflow.recognize_camera_snapshot(
                focus_session_id=focus_session_id,
                image_bytes=image_bytes,
                mime_type="image/jpeg",
                context=camera_context,
            )
            with self._lock:
                self._latest_recognition = recognition
                self._latest_error = ""
        except Exception as exc:
            with self._lock:
                self._latest_error = str(exc)
        finally:
            with self._lock:
                self._recognizing = False


def fragment_compat(run_every: str):
    if hasattr(st, "fragment"):
        return st.fragment(run_every=run_every)
    return lambda func: func


def render_camera_stream(
    workflow: FocusWorkflow,
    focus_session_id: int,
    camera_context: str,
    interval_seconds: int,
):
    try:
        from streamlit_webrtc import WebRtcMode, webrtc_streamer
    except ModuleNotFoundError:
        st.warning(
            "自动摄像头督学需要安装 streamlit-webrtc。安装依赖后，系统会自动定时识别状态。"
        )
        return None

    st.caption("开启后仅在内存中读取最近一帧；默认不保存原始图片。")
    context = webrtc_streamer(
        key=f"supervision_auto_camera_{focus_session_id}",
        mode=WebRtcMode.SENDRECV,
        media_stream_constraints={"video": True, "audio": False},
        video_processor_factory=AutoFocusFrameProcessor,
        async_processing=True,
    )

    if not context.video_processor:
        st.info("等待摄像头授权和画面输入。")
        return context

    context.video_processor.configure(
        focus_session_id=focus_session_id,
        camera_context=camera_context,
        interval_seconds=interval_seconds,
    )
    return context


@fragment_compat(run_every="5s")
def render_auto_camera_status(context) -> None:
    if not context or not context.video_processor:
        return

    status = context.video_processor.latest_status()
    if not status["latest_frame_at"]:
        st.info("摄像头已开启，等待第一帧画面。")
        return

    recognition = status.get("latest_recognition")
    if recognition:
        st.session_state.latest_supervision_recognition = recognition
        state_label = STATE_LABEL_ZH.get(recognition["state_type"], "无法判断")
        st.success(
            f"自动记录：{state_label}，置信度 {recognition['confidence']:.2f}，"
            f"专注度 {int(recognition.get('focus_score') or 0)}/100"
        )
    elif status.get("recognizing"):
        st.caption("自动识别学习状态中...")
    else:
        st.caption(f"自动识别运行中，间隔 {int(status['interval_seconds'])} 秒。")

    if status.get("latest_error"):
        st.caption(f"自动识别暂不可用：{status['latest_error']}")


def render_focus_report_summary(report: dict) -> None:
    st.subheader("最近督学报告")
    metric_columns = st.columns(3)
    metric_columns[0].metric("专注度", f"{int(report.get('focus_score') or 0)}/100")
    metric_columns[1].metric("有效专注", f"{int(report.get('effective_focus_minutes') or 0)} 分钟")
    metric_columns[2].metric("最长连续专注", f"{int(report.get('longest_focus_minutes') or 0)} 分钟")
    st.write(f"专注质量：{report.get('focus_quality', '')}")
    st.write(report.get("ai_summary", ""))
    st.write(f"问题线索：{report.get('possible_problem_signal', '')}")
    st.write(f"建议行动：{report.get('suggested_action', '')}")


def format_duration(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@fragment_compat(run_every="1s")
def render_live_focus_timer(session: dict) -> None:
    started_at = parse_iso_datetime(str(session.get("started_at") or ""))
    if not started_at:
        return
    now = datetime.now(started_at.tzinfo)
    elapsed_seconds = max(0, round((now - started_at).total_seconds()))
    planned_seconds = max(0, int(session.get("planned_minutes") or 0) * 60)
    remaining_seconds = max(0, planned_seconds - elapsed_seconds)

    columns = st.columns(3)
    columns[0].metric("已进行", format_duration(elapsed_seconds))
    columns[1].metric("计划时长", format_duration(planned_seconds))
    columns[2].metric("剩余", format_duration(remaining_seconds))


def render_pomodoro_supervision_panel() -> None:
    tasks = WorkspaceWorkflow().list_tasks(today=local_today(), limit=100)
    task_options = {"不关联任务": None}
    for task in tasks:
        task_options[f"#{task['id']} {task.get('title', '')}"] = int(task["id"])

    selected_task = st.selectbox("关联任务", list(task_options.keys()), key="supervision_task")
    planned_minutes = st.number_input(
        "计划学习分钟数",
        min_value=1,
        max_value=240,
        value=25,
        step=5,
        key="supervision_minutes",
    )
    workflow = FocusWorkflow()
    if st.button("开始番茄钟", type="primary", key="supervision_start"):
        session_id = workflow.start_focus_session(
            task_id=task_options[selected_task],
            planned_minutes=int(planned_minutes),
        )
        st.session_state.current_supervision_session_id = session_id
        st.success(f"番茄钟已开始：#{session_id}")

    current_id = st.session_state.get("current_supervision_session_id")
    if not current_id:
        latest_report = st.session_state.get("latest_supervision_report")
        if not latest_report:
            reports = workflow.list_focus_reports(limit=1)
            latest_report = reports[0] if reports else None
        if latest_report:
            render_focus_report_summary(latest_report)
        st.info("开始后可记录中断、状态和完成情况。")
        return

    st.markdown(f"**当前番茄钟 #{current_id}**")
    current_session = workflow.get_focus_session(int(current_id)) or {}
    render_live_focus_timer(current_session)
    camera_context = st.text_input(
        "当前学习任务或环境补充",
        key=f"supervision_camera_context_{current_id}",
    )
    auto_interval = st.number_input(
        "自动识别间隔（秒）",
        min_value=15,
        max_value=600,
        value=60,
        step=15,
        key=f"supervision_auto_interval_{current_id}",
    )
    camera_context_obj = render_camera_stream(
        workflow=workflow,
        focus_session_id=int(current_id),
        camera_context=camera_context,
        interval_seconds=int(auto_interval),
    )
    render_auto_camera_status(camera_context_obj)

    latest_recognition = st.session_state.get("latest_supervision_recognition")
    if latest_recognition:
        state_label = STATE_LABEL_ZH.get(latest_recognition["state_type"], "无法判断")
        st.write(
            f"最近识别：{state_label} / "
            f"{latest_recognition['confidence']:.2f} / "
            f"专注度 {int(latest_recognition.get('focus_score') or 0)}/100 / "
            f"{latest_recognition['explanation']}"
        )

    selected_state = st.selectbox(
        "备用手动状态记录",
        STATE_LABELS,
        format_func=lambda state: STATE_LABEL_ZH.get(state, state),
        key="supervision_state",
    )
    confidence = st.slider("置信度", min_value=0.0, max_value=1.0, value=0.7, key="supervision_confidence")
    explanation = st.text_input("简短说明", key="supervision_explanation")
    if st.button("记录状态", key="supervision_record_state"):
        workflow.record_camera_state(
            focus_session_id=int(current_id),
            state_type=selected_state,
            confidence=float(confidence),
            explanation=explanation,
        )
        st.success("状态已记录。")

    actual_minutes = st.number_input(
        "实际学习分钟数",
        min_value=0,
        max_value=240,
        value=int(planned_minutes),
        step=5,
        key="supervision_actual",
    )
    pause_count = st.number_input("暂停次数", min_value=0, max_value=50, value=0, key="supervision_pause")
    completion_status = st.selectbox("完成情况", SUPERVISION_STATUSES, key="supervision_done")
    reflection = st.text_area("复盘备注", key="supervision_reflection")
    if st.button("结束番茄钟", key="supervision_finish"):
        report_id = workflow.finish_focus_session(
            focus_session_id=int(current_id),
            actual_minutes=int(actual_minutes),
            pause_count=int(pause_count),
            completion_status=completion_status,
            reflection=reflection,
        )
        if report_id:
            st.session_state.latest_supervision_report = workflow.get_focus_report(report_id)
        st.session_state.pop("current_supervision_session_id", None)
        st.success("番茄钟已结束。")
        st.rerun()
