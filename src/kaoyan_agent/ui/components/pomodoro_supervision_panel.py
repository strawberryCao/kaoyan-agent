import threading
import time
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

    def recv(self, frame):
        now = time.time()
        if now - self._last_capture_at >= 2:
            image = frame.to_image()
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=80)
            with self._lock:
                self._latest_image_bytes = buffer.getvalue()
                self._latest_frame_at = now
            self._last_capture_at = now
        return frame

    def latest_snapshot(self) -> tuple[bytes, str, float]:
        with self._lock:
            return self._latest_image_bytes, "image/jpeg", self._latest_frame_at


def fragment_compat(run_every: str):
    if hasattr(st, "fragment"):
        return st.fragment(run_every=run_every)
    return lambda func: func


@fragment_compat(run_every="5s")
def render_auto_camera_sampler(
    workflow: FocusWorkflow,
    focus_session_id: int,
    camera_context: str,
    interval_seconds: int,
) -> None:
    try:
        from streamlit_webrtc import WebRtcMode, webrtc_streamer
    except ModuleNotFoundError:
        st.warning(
            "自动摄像头督学需要安装 streamlit-webrtc。安装依赖后，系统会自动定时识别状态。"
        )
        return

    st.caption("开启后仅在内存中读取最近一帧；默认不保存原始图片。")
    context = webrtc_streamer(
        key=f"supervision_auto_camera_{focus_session_id}",
        mode=WebRtcMode.SENDONLY,
        media_stream_constraints={"video": True, "audio": False},
        video_processor_factory=AutoFocusFrameProcessor,
        async_processing=True,
    )

    if not context.video_processor:
        st.info("等待摄像头授权和画面输入。")
        return

    image_bytes, mime_type, frame_at = context.video_processor.latest_snapshot()
    if not image_bytes:
        st.info("摄像头已开启，等待第一帧画面。")
        return

    now = time.time()
    last_sample_key = f"supervision_last_auto_sample_at_{focus_session_id}"
    last_frame_key = f"supervision_last_auto_frame_at_{focus_session_id}"
    last_sample_at = float(st.session_state.get(last_sample_key, 0.0))
    last_frame_at = float(st.session_state.get(last_frame_key, 0.0))

    if now - last_sample_at < interval_seconds or frame_at <= last_frame_at:
        remaining = max(0, int(interval_seconds - (now - last_sample_at)))
        st.caption(f"自动识别运行中，距离下一次采样约 {remaining} 秒。")
        return

    st.session_state[last_sample_key] = now
    st.session_state[last_frame_key] = frame_at
    with st.spinner("自动识别学习状态..."):
        recognition = workflow.recognize_camera_snapshot(
            focus_session_id=focus_session_id,
            image_bytes=image_bytes,
            mime_type=mime_type,
            context=camera_context,
        )
    st.session_state.latest_supervision_recognition = recognition
    state_label = STATE_LABEL_ZH.get(recognition["state_type"], "无法判断")
    st.success(f"自动记录：{state_label}，置信度 {recognition['confidence']:.2f}")
    if recognition.get("generation_error"):
        st.caption(f"AI 识别不可用，已按 unknown 记录：{recognition['generation_error']}")


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
        if latest_report:
            st.subheader("最近督学报告")
            st.write(f"专注质量：{latest_report.get('focus_quality', '')}")
            st.write(f"有效专注：{latest_report.get('effective_focus_minutes', 0)} 分钟")
            st.write(latest_report.get("ai_summary", ""))
            st.write(f"问题线索：{latest_report.get('possible_problem_signal', '')}")
            st.write(f"建议行动：{latest_report.get('suggested_action', '')}")
        st.info("开始后可记录中断、状态和完成情况。")
        return

    st.markdown(f"**当前番茄钟 #{current_id}**")
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
    render_auto_camera_sampler(
        workflow=workflow,
        focus_session_id=int(current_id),
        camera_context=camera_context,
        interval_seconds=int(auto_interval),
    )

    latest_recognition = st.session_state.get("latest_supervision_recognition")
    if latest_recognition:
        state_label = STATE_LABEL_ZH.get(latest_recognition["state_type"], "无法判断")
        st.write(
            f"最近识别：{state_label} / "
            f"{latest_recognition['confidence']:.2f} / "
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
