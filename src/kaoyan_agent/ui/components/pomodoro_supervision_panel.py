from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

import streamlit as st

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.schemas.focus import FocusTimerState, FocusTimerStatus
from kaoyan_agent.services.local_yolo_focus_recognizer import (
    LABEL_TEXT,
    LocalYoloFocusRecognizer,
    diagnose_camera_access,
    find_yolo_weight_candidates,
)
from kaoyan_agent.ui.components.common import (
    install_card_styles,
    render_json_debug_expander,
    render_section_title,
    render_status_badge,
)
from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.workflows.focus import FOCUS_DB_SESSION_ID_KEY, FocusWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


STATE_LABELS = ["focused", "away", "distracted", "unknown"]
STATE_LABEL_ZH = {
    "focused": "专注",
    "away": "离开",
    "distracted": "分心",
    "blocked": "无法判断",
    "unknown": "未知",
}


class AutoFocusFrameProcessor:
    """Keep the latest camera frame in memory for local YOLO recognition."""

    def __init__(self):
        self._lock = threading.Lock()
        self._latest_frame = None
        self._latest_frame_at = 0.0

    def recv(self, frame):
        try:
            frame_array = frame.to_ndarray(format="bgr24")
        except Exception:
            frame_array = None
        if frame_array is not None:
            with self._lock:
                self._latest_frame = frame_array
                self._latest_frame_at = time.time()
        return frame

    def latest_frame(self):
        with self._lock:
            return self._latest_frame, self._latest_frame_at


def fragment_compat(run_every: str):
    if hasattr(st, "fragment"):
        return st.fragment(run_every=run_every)
    return lambda func: func


def get_visible_timer_controls(status: FocusTimerStatus | str) -> list[str]:
    value = status.value if isinstance(status, FocusTimerStatus) else str(status)
    if value == FocusTimerStatus.RUNNING.value:
        return ["pause", "end"]
    if value == FocusTimerStatus.PAUSED.value:
        return ["resume", "end"]
    return ["start"]


@st.cache_resource(show_spinner=False)
def get_cached_recognizer(
    weights_path: str,
    confidence_threshold: float,
    camera_id: int,
) -> LocalYoloFocusRecognizer:
    return LocalYoloFocusRecognizer(
        Path(weights_path) if weights_path else None,
        confidence_threshold=confidence_threshold,
        camera_id=camera_id,
        check_camera=False,
    )


@st.cache_data(ttl=10, show_spinner=False)
def get_camera_diagnostic(camera_id: int) -> dict:
    return diagnose_camera_access(camera_id)


def select_yolo_weights_path(settings: Settings) -> tuple[str, list[str]]:
    candidates = find_yolo_weight_candidates(settings.yolo_focus_weights_path)
    candidate_values = [str(path) for path in candidates]
    configured = str(settings.yolo_focus_weights_path or "")
    if configured and configured not in candidate_values:
        candidate_values.insert(0, configured)

    if not candidate_values:
        st.caption("未在 models/、weights/、runs/、src/ 或项目根目录找到 .pt 权重。")
        return "", []

    selected = st.selectbox(
        "YOLO 权重",
        candidate_values,
        index=0,
        key="supervision_yolo_weights",
    )
    return selected, candidate_values


@fragment_compat(run_every="200ms")
def render_auto_camera_sampler(
    workflow: FocusWorkflow,
    focus_session_id: int,
    recognizer: LocalYoloFocusRecognizer,
    inference_fps: int,
) -> None:
    try:
        from streamlit_webrtc import WebRtcMode, webrtc_streamer
    except ModuleNotFoundError:
        st.warning("streamlit-webrtc 未安装，无法打开浏览器摄像头。")
        return

    st.caption("摄像头画面只进入本地 YOLO 推理，不发送给 DeepSeek。")
    context = webrtc_streamer(
        key=f"supervision_yolo_camera_{focus_session_id}",
        mode=WebRtcMode.SENDONLY,
        media_stream_constraints={"video": True, "audio": False},
        video_processor_factory=AutoFocusFrameProcessor,
        async_processing=True,
    )
    if not context.video_processor:
        st.info("等待浏览器摄像头授权或视频帧输入。")
        return

    frame, frame_at = context.video_processor.latest_frame()
    if frame is None:
        st.info("摄像头已请求开启，但还没有收到视频帧。请确认浏览器已授权摄像头。")
        return

    st.session_state.latest_supervision_frame = frame
    min_interval = 1.0 / max(1, min(5, int(inference_fps or 1)))
    now = time.time()
    last_sample_key = f"supervision_last_yolo_sample_at_{focus_session_id}"
    last_frame_key = f"supervision_last_yolo_frame_at_{focus_session_id}"
    last_sample_at = float(st.session_state.get(last_sample_key, 0.0))
    last_frame_at = float(st.session_state.get(last_frame_key, 0.0))
    if now - last_sample_at < min_interval or frame_at <= last_frame_at:
        st.caption("本地 YOLO 识别运行中。")
        return

    st.session_state[last_sample_key] = now
    st.session_state[last_frame_key] = frame_at
    result = recognizer.predict_frame(frame)
    record_result = workflow.record_focus_state(
        focus_session_id=focus_session_id,
        state_type=result.label,
        confidence=result.confidence,
        explanation=f"本地 YOLO 识别：{result.label_text}",
        metadata={"recognition_source": "local_yolo", "debug": result.debug},
        force=False,
        min_log_interval_seconds=10,
    )
    st.session_state.latest_supervision_recognition = {
        **result.to_dict(),
        "record_result": record_result,
        "recognized_at": time.strftime("%H:%M:%S"),
    }


def render_pomodoro_supervision_panel() -> None:
    install_card_styles()
    settings = get_settings()
    workflow = FocusWorkflow()
    restored = workflow.restore_active_timer_to_state(st.session_state)
    timer_state = restored or workflow.get_timer_state(st.session_state)
    current_id = st.session_state.get(FOCUS_DB_SESSION_ID_KEY)
    controls = get_visible_timer_controls(timer_state.status)

    col_timer, col_camera = st.columns([1, 1], gap="large")
    with col_timer:
        render_timer_card(workflow, timer_state, current_id, controls)
    with col_camera:
        render_vision_supervision_card(workflow, current_id, settings)

    tab_timer, tab_visual, tab_report = st.tabs(["专注计时", "实时视觉", "专注报告"])
    with tab_timer:
        if current_id:
            render_state_timeline(workflow, int(current_id))
        render_focus_stats(workflow)
    with tab_visual:
        render_manual_state_controls(workflow, current_id)
        render_yolo_diagnostics(settings)
    with tab_report:
        latest_report = st.session_state.get("latest_supervision_report")
        if latest_report:
            render_focus_report(latest_report)
        else:
            st.info("结束一次番茄钟后会在这里显示专注报告。")


def render_timer_card(
    workflow: FocusWorkflow,
    timer_state: FocusTimerState,
    current_id,
    controls: list[str],
) -> None:
    st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
    st.markdown('<div class="kaoyan-card-title">番茄钟</div>', unsafe_allow_html=True)
    if "start" in controls:
        render_start_controls(workflow)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if not current_id:
        st.warning("未找到活动中的番茄钟，请重新开始。")
        workflow.reset_timer(st.session_state)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    elapsed_seconds = workflow.get_elapsed_seconds(timer_state)
    remaining_seconds = workflow.get_remaining_seconds(timer_state)
    col_elapsed, col_remaining, col_pauses = st.columns(3)
    col_elapsed.metric("已专注", format_duration(elapsed_seconds))
    col_remaining.metric("剩余", format_duration(remaining_seconds))
    col_pauses.metric("暂停", timer_state.pause_count)
    st.caption(
        f"状态：{render_status_badge(timer_state.status.value)} / "
        f"任务：{timer_state.task_title or '临时专注任务'}"
    )
    control_cols = st.columns(2)
    if "pause" in controls and control_cols[0].button("暂停", key="supervision_pause_timer"):
        show_timer_operation_result(workflow.safe_pause_timer(st.session_state))
        st.rerun()
    if "resume" in controls and control_cols[0].button("继续", key="supervision_resume_timer"):
        show_timer_operation_result(workflow.safe_resume_timer(st.session_state))
        st.rerun()
    with st.expander("结束时填写复盘备注", expanded=False):
        reflection = st.text_area("复盘备注", key="supervision_reflection")
    if "end" in controls and control_cols[1].button("结束", key="supervision_finish"):
        result = workflow.safe_end_timer(st.session_state, reflection=reflection)
        if result.get("ok"):
            report_id = result.get("result", {}).get("report_id")
            if report_id:
                st.session_state.latest_supervision_report = workflow.get_focus_report(report_id)
            st.success(result["message"])
        else:
            st.warning(result["message"])
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_start_controls(workflow: FocusWorkflow) -> None:
    tasks = WorkspaceWorkflow().list_tasks(today=local_today(), limit=100)
    task_options = {"不关联任务": None}
    for task in tasks:
        label = f"{task.get('title') or '未命名任务'}（{int(task.get('estimated_minutes') or 25)} 分钟）"
        task_options[label] = int(task["id"])

    selected_task = st.selectbox("关联任务", list(task_options.keys()), key="supervision_task")
    planned_minutes = st.number_input(
        "计划分钟",
        min_value=1,
        max_value=240,
        value=25,
        step=5,
        key="supervision_minutes",
    )
    if not st.button("开始番茄钟", type="primary", key="supervision_start"):
        return

    task_id = task_options[selected_task]
    try:
        if task_id is not None:
            timer_state = workflow.prepare_timer_from_task(st.session_state, task_id)
            timer_state.planned_minutes = int(planned_minutes)
        else:
            timer_state = FocusTimerState(
                task_title="临时专注任务",
                planned_minutes=int(planned_minutes),
                status=FocusTimerStatus.IDLE,
            )
        workflow.save_timer_state(st.session_state, timer_state)
        workflow.start_timer(st.session_state)
        st.success("番茄钟已开始。")
        st.rerun()
    except ValueError as exc:
        st.warning(str(exc))


def render_vision_supervision_card(workflow: FocusWorkflow, current_id, settings: Settings) -> None:
    selected_weights, _ = select_yolo_weights_path(settings)
    recognizer = get_cached_recognizer(
        selected_weights,
        settings.yolo_focus_confidence_threshold,
        settings.yolo_focus_camera_id,
    )
    camera_diagnostic = get_camera_diagnostic(settings.yolo_focus_camera_id)
    latest = st.session_state.get("latest_supervision_recognition") or {}

    st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
    st.markdown('<div class="kaoyan-card-title">实时视觉督学</div>', unsafe_allow_html=True)
    available = recognizer.is_available()
    st.markdown(
        f'<span class="kaoyan-badge">本地 YOLO：{"可用" if available else "不可用"}</span>'
        f'<span class="kaoyan-badge">摄像头：{settings.yolo_focus_camera_id}</span>'
        f'<span class="kaoyan-badge">FPS：{settings.yolo_focus_inference_fps}</span>',
        unsafe_allow_html=True,
    )
    st.caption(f"权重路径：{selected_weights or '未找到 .pt'}")
    col_label, col_conf = st.columns(2)
    col_label.metric("当前识别", latest.get("label_text") or LABEL_TEXT["unknown"])
    col_conf.metric("置信度", f"{float(latest.get('confidence') or 0.0):.2f}")
    st.caption(f"最近识别：{latest.get('recognized_at') or '暂无'}")

    camera_enabled = st.toggle("开启摄像头督学", value=False, key="supervision_camera_enabled")
    if camera_enabled and not current_id:
        st.info("请先开始番茄钟，再记录视觉督学状态。")
    elif camera_enabled and not available:
        st.warning(recognizer.status_message() or "本地 YOLO 不可用。")
    elif camera_enabled:
        render_auto_camera_sampler(
            workflow=workflow,
            focus_session_id=int(current_id),
            recognizer=recognizer,
            inference_fps=settings.yolo_focus_inference_fps,
        )

    latest_frame = st.session_state.get("latest_supervision_frame")
    if latest_frame is not None:
        st.image(latest_frame, channels="BGR", caption="最近帧", use_container_width=True)
    else:
        st.caption("最近帧：暂无")

    if camera_enabled and not camera_diagnostic.get("can_open"):
        st.info(camera_diagnostic.get("error") or "摄像头无法打开。浏览器摄像头仍可能需要单独授权。")
    render_json_debug_expander(
        "最近错误 / YOLO 诊断",
        {
            "recognizer": recognizer.debug,
            "camera": camera_diagnostic,
            "latest": latest,
        },
    )
    st.markdown("</div>", unsafe_allow_html=True)


def render_yolo_diagnostics(settings: Settings) -> None:
    selected_weights = st.session_state.get("supervision_yolo_weights") or ""
    recognizer = get_cached_recognizer(
        selected_weights,
        settings.yolo_focus_confidence_threshold,
        settings.yolo_focus_camera_id,
    )
    render_section_title("YOLO 诊断")
    status_cols = st.columns(4)
    status_cols[0].metric("权重", "找到" if recognizer.debug.get("weights_found") else "未找到")
    status_cols[1].metric("ultralytics", "可用" if recognizer.debug.get("ultralytics_importable") else "缺失")
    status_cols[2].metric("cv2", "可用" if recognizer.debug.get("cv2_importable") else "缺失")
    status_cols[3].metric("模型", "已加载" if recognizer.debug.get("model_loaded") else "未加载")
    render_json_debug_expander("完整诊断", recognizer.debug)


def render_manual_state_controls(workflow: FocusWorkflow, current_id) -> None:
    render_section_title("手动状态记录", "视觉不可用或需要纠正时使用。")
    selected_state = st.selectbox(
        "手动状态",
        STATE_LABELS,
        format_func=lambda state: STATE_LABEL_ZH.get(state, state),
        key="supervision_state",
    )
    confidence = st.slider(
        "手动置信度",
        min_value=0.0,
        max_value=1.0,
        value=0.7,
        key="supervision_confidence",
    )
    explanation = st.text_input("简短说明", key="supervision_explanation")
    if st.button("记录手动状态", key="supervision_record_state"):
        if not current_id:
            st.warning("请先开始番茄钟，再记录督学状态。")
            return
        workflow.record_focus_state(
            focus_session_id=int(current_id),
            state_type=selected_state,
            confidence=float(confidence),
            explanation=explanation or "手动记录",
            metadata={"recognition_source": "manual"},
            force=True,
        )
        st.success("状态已记录。")
        st.rerun()


def show_timer_operation_result(result: dict) -> None:
    if result.get("ok"):
        st.success(result.get("message", "操作已完成。"))
    else:
        st.warning(result.get("message", "当前状态不支持这个操作。"))


def render_state_timeline(workflow: FocusWorkflow, focus_session_id: int) -> None:
    events = workflow.focus_repository.list_state_events(focus_session_id)
    render_section_title("状态事件时间线")
    if not events:
        st.info("本次专注还没有视觉或手动状态记录。")
        return
    for event in events[-8:]:
        st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
        st.markdown(
            f"**{STATE_LABEL_ZH.get(event.get('state_type'), '未知')}** "
            f"/ 置信度 {float(event.get('confidence') or 0):.2f}"
        )
        st.caption(f"{event.get('created_at')} / {event.get('explanation') or ''}")
        st.markdown("</div>", unsafe_allow_html=True)


def render_focus_report(report: dict) -> None:
    render_section_title("最近督学报告")
    st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
    st.markdown(f"**专注质量：** {report.get('focus_quality', '')}")
    st.markdown(f"**有效专注：** {report.get('effective_focus_minutes', 0)} 分钟")
    st.markdown(f"**总结：** {report.get('ai_summary', '')}")
    st.markdown(f"**问题线索：** {report.get('possible_problem_signal', '')}")
    st.markdown(f"**建议行动：** {report.get('suggested_action', '')}")
    st.markdown("</div>", unsafe_allow_html=True)


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes:02d}:{remaining_seconds:02d}"


def render_focus_stats(workflow: FocusWorkflow) -> None:
    stats = workflow.get_stats()
    render_section_title("专注统计")
    col_today, col_week, col_rate = st.columns(3)
    col_today.metric("今日专注分钟", stats.get("today_focus_minutes", 0))
    col_week.metric("近 7 日专注分钟", stats.get("week_focus_minutes", 0))
    col_rate.metric("完成率", f"{stats.get('completion_rate', 0)}%")
    recent_sessions = workflow.list_recent_sessions(limit=8)
    if recent_sessions:
        with st.expander("最近专注记录", expanded=False):
            for session in recent_sessions:
                st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
                st.markdown(
                    f"**{session.get('task_title') or '临时专注任务'}** / "
                    f"{session.get('subject') or '未指定'}"
                )
                st.caption(
                    f"计划 {session.get('planned_minutes', 0)} 分钟 / "
                    f"实际 {round(int(session.get('actual_seconds') or 0) / 60, 1)} 分钟 / "
                    f"状态：{render_status_badge(session.get('completion_status', ''))}"
                )
                st.markdown("</div>", unsafe_allow_html=True)
