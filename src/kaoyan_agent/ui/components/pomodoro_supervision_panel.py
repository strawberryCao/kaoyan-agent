from __future__ import annotations

import html
import threading
import time
from datetime import datetime, timezone
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
        self._last_recognition_at = 0.0
        self._recognizing = False
        self._latest_recognition = None
        self._latest_error = ""
        self._focus_session_id = 0
        self._inference_interval_seconds = 1.0
        self._workflow: Optional[FocusWorkflow] = None
        self._recognizer: Optional[LocalYoloFocusRecognizer] = None

    def configure(
        self,
        workflow: FocusWorkflow,
        focus_session_id: int,
        recognizer: LocalYoloFocusRecognizer,
        inference_fps: int,
    ) -> None:
        with self._lock:
            self._workflow = workflow
            self._focus_session_id = int(focus_session_id)
            self._recognizer = recognizer
            fps = max(1, min(5, int(inference_fps or 1)))
            self._inference_interval_seconds = 1.0 / fps

    def recv(self, frame):
        try:
            frame_array = frame.to_ndarray(format="bgr24")
        except Exception:
            frame_array = None
        if frame_array is not None:
            inference_frame = self._resize_for_inference(frame_array)
            with self._lock:
                self._latest_frame = inference_frame
                self._latest_frame_at = time.time()
            self._maybe_start_recognition(inference_frame, self._latest_frame_at)
        return frame

    def latest_frame(self):
        with self._lock:
            return self._latest_frame, self._latest_frame_at

    def latest_status(self) -> dict:
        with self._lock:
            return {
                "latest_frame": self._latest_frame,
                "latest_frame_at": self._latest_frame_at,
                "last_recognition_at": self._last_recognition_at,
                "recognizing": self._recognizing,
                "latest_recognition": self._latest_recognition,
                "latest_error": self._latest_error,
                "interval_seconds": self._inference_interval_seconds,
            }

    def _maybe_start_recognition(self, frame_array, now: float) -> None:
        with self._lock:
            if not self._workflow or not self._recognizer or not self._focus_session_id:
                return
            if not self._recognizer.is_available() or self._recognizing:
                return
            if now - self._last_recognition_at < self._inference_interval_seconds:
                return
            self._recognizing = True
            self._last_recognition_at = now
            workflow = self._workflow
            recognizer = self._recognizer
            focus_session_id = self._focus_session_id

        thread = threading.Thread(
            target=self._recognize_frame,
            args=(workflow, recognizer, focus_session_id, frame_array.copy()),
            daemon=True,
        )
        thread.start()

    def _recognize_frame(
        self,
        workflow: FocusWorkflow,
        recognizer: LocalYoloFocusRecognizer,
        focus_session_id: int,
        frame_array,
    ) -> None:
        try:
            result = recognizer.predict_frame(frame_array)
            focus_score = workflow.default_focus_score(result.label, result.confidence)
            record_result = workflow.record_focus_state(
                focus_session_id=focus_session_id,
                state_type=result.label,
                confidence=result.confidence,
                focus_score=focus_score,
                explanation=f"本地 YOLO 识别：{result.label_text}",
                metadata={"recognition_source": "local_yolo", "debug": result.debug},
                force=False,
                min_log_interval_seconds=10,
            )
            recognition = {
                **result.to_dict(),
                "focus_score": focus_score,
                "record_result": record_result,
                "recognized_at": time.strftime("%H:%M:%S"),
            }
            with self._lock:
                self._latest_recognition = recognition
                self._latest_error = ""
        except Exception as exc:
            with self._lock:
                self._latest_error = str(exc)
        finally:
            with self._lock:
                self._recognizing = False

    @staticmethod
    def _resize_for_inference(frame_array):
        try:
            height, width = frame_array.shape[:2]
            max_side = max(height, width)
            if max_side <= 640:
                return frame_array
            import cv2

            scale = 640 / max_side
            return cv2.resize(
                frame_array,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        except Exception:
            return frame_array


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


def render_auto_camera_sampler(
    workflow: FocusWorkflow,
    focus_session_id: int,
    recognizer: LocalYoloFocusRecognizer,
    inference_fps: int,
):
    try:
        from streamlit_webrtc import WebRtcMode, webrtc_streamer
    except ModuleNotFoundError:
        st.warning("streamlit-webrtc 未安装，无法打开浏览器摄像头。")
        return None

    st.caption("摄像头画面只进入本地 YOLO 推理，不发送给 DeepSeek。")
    context = webrtc_streamer(
        key=f"supervision_yolo_camera_{focus_session_id}",
        mode=WebRtcMode.SENDRECV,
        media_stream_constraints={"video": True, "audio": False},
        video_processor_factory=AutoFocusFrameProcessor,
        async_processing=True,
    )
    if not context.video_processor:
        st.info("等待浏览器摄像头授权或视频帧输入。")
        return context

    context.video_processor.configure(
        workflow=workflow,
        focus_session_id=focus_session_id,
        recognizer=recognizer,
        inference_fps=inference_fps,
    )
    return context


@fragment_compat(run_every="2s")
def render_auto_camera_status(context) -> None:
    if not context or not context.video_processor:
        return

    status = context.video_processor.latest_status()
    latest_frame = status.get("latest_frame")
    if latest_frame is not None:
        st.session_state.latest_supervision_frame = latest_frame

    if not status.get("latest_frame_at"):
        st.info("摄像头已请求开启，但还没有收到视频帧。请确认浏览器已授权摄像头。")
        return

    recognition = status.get("latest_recognition")
    if recognition:
        st.session_state.latest_supervision_recognition = recognition
        st.caption(
            f"本地 YOLO 自动识别：{recognition.get('label_text') or LABEL_TEXT['unknown']} / "
            f"置信度 {float(recognition.get('confidence') or 0.0):.2f} / "
            f"专注度 {int(recognition.get('focus_score') or 0)}/100 / "
            f"{recognition.get('recognized_at') or ''}"
        )
    elif status.get("recognizing"):
        with st.spinner("本地 YOLO 正在识别学习状态..."):
            st.empty()
    else:
        st.caption("摄像头已开启，等待下一帧进入本地 YOLO 识别。")

    if status.get("latest_error"):
        st.caption(f"本地 YOLO 识别暂不可用：{status['latest_error']}")


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
        if not latest_report:
            reports = workflow.list_focus_reports(limit=1)
            latest_report = reports[0] if reports else None
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
    html_content = '<div class="kaoyan-card">'
    html_content += '<div class="kaoyan-card-title">番茄钟</div>'
    html_content += '</div>'
    st.html(html_content)
    if "start" in controls:
        render_start_controls(workflow)
        return

    if not current_id:
        st.warning("未找到活动中的番茄钟，请重新开始。")
        workflow.reset_timer(st.session_state)
        return

    render_live_focus_timer(timer_state.model_dump())
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
    with st.spinner("加载本地 YOLO 模型..."):
        recognizer = get_cached_recognizer(
            selected_weights,
            settings.yolo_focus_confidence_threshold,
            settings.yolo_focus_camera_id,
        )
    latest = st.session_state.get("latest_supervision_recognition") or {}

    available = recognizer.is_available()
    html_content = '<div class="kaoyan-card">'
    html_content += '<div class="kaoyan-card-title">实时视觉督学</div>'
    html_content += f'<span class="kaoyan-badge">本地 YOLO：{"可用" if available else "不可用"}</span>'
    html_content += f'<span class="kaoyan-badge">摄像头：{settings.yolo_focus_camera_id}</span>'
    html_content += f'<span class="kaoyan-badge">FPS：{settings.yolo_focus_inference_fps}</span>'
    html_content += '</div>'
    st.html(html_content)
    st.caption(f"权重路径：{selected_weights or '未找到 .pt'}")
    col_label, col_conf, col_score = st.columns(3)
    col_label.metric("当前识别", latest.get("label_text") or LABEL_TEXT["unknown"])
    col_conf.metric("置信度", f"{float(latest.get('confidence') or 0.0):.2f}")
    col_score.metric("专注度", f"{int(latest.get('focus_score') or 0)}/100")
    st.caption(f"最近识别：{latest.get('recognized_at') or '暂无'}")

    camera_enabled = st.toggle("开启摄像头督学", value=False, key="supervision_camera_enabled")
    if camera_enabled and not current_id:
        st.info("请先开始番茄钟，再记录视觉督学状态。")
    elif camera_enabled and not available:
        st.warning(recognizer.status_message() or "本地 YOLO 不可用。")
    elif camera_enabled:
        camera_context = render_auto_camera_sampler(
            workflow=workflow,
            focus_session_id=int(current_id),
            recognizer=recognizer,
            inference_fps=settings.yolo_focus_inference_fps,
        )
        render_auto_camera_status(camera_context)

    latest_frame = st.session_state.get("latest_supervision_frame")
    if latest_frame is not None:
        st.image(latest_frame, channels="BGR", caption="最近帧", use_container_width=True)
    else:
        st.caption("最近帧：暂无")

    camera_diagnostic = st.session_state.get("latest_supervision_camera_diagnostic") or {}
    if st.button("检查本机摄像头", key="supervision_camera_diagnostic"):
        with st.spinner("检查本机摄像头状态..."):
            camera_diagnostic = get_camera_diagnostic(settings.yolo_focus_camera_id)
            st.session_state.latest_supervision_camera_diagnostic = camera_diagnostic
    if camera_diagnostic and not camera_diagnostic.get("can_open"):
        st.info(camera_diagnostic.get("error") or "摄像头无法打开。浏览器摄像头仍可能需要单独授权。")
    render_json_debug_expander(
        "最近错误 / YOLO 诊断",
        {
            "recognizer": recognizer.debug,
            "camera": camera_diagnostic or {"status": "not_checked"},
            "latest": latest,
        },
    )


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
        state_label = html.escape(STATE_LABEL_ZH.get(event.get("state_type"), "未知"))
        explanation = html.escape(str(event.get("explanation") or ""))
        created_at = html.escape(str(event.get("created_at") or ""))
        confidence = float(event.get("confidence") or 0)
        html_content = '<div class="kaoyan-card">'
        html_content += (
            f'<div class="kaoyan-card-title">{state_label} / 置信度 {confidence:.2f}</div>'
        )
        html_content += f'<div class="kaoyan-muted">{created_at} / {explanation}</div>'
        html_content += '</div>'
        st.html(html_content)


def render_focus_report(report: dict) -> None:
    render_section_title("最近督学报告")
    html_content = '<div class="kaoyan-card">'
    html_content += f'<div class="kaoyan-card-title">专注度：{int(report.get("focus_score") or 0)}/100</div>'
    html_content += f'<div>专注质量：{html.escape(str(report.get("focus_quality") or ""))}</div>'
    html_content += f'<div>有效专注：{int(report.get("effective_focus_minutes") or 0)} 分钟</div>'
    html_content += f'<div>总结：{html.escape(str(report.get("ai_summary") or ""))}</div>'
    html_content += f'<div>问题线索：{html.escape(str(report.get("possible_problem_signal") or ""))}</div>'
    html_content += f'<div>建议行动：{html.escape(str(report.get("suggested_action") or ""))}</div>'
    html_content += '</div>'
    st.html(html_content)


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes:02d}:{remaining_seconds:02d}"


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def timer_elapsed_seconds_from_state(timer_state: FocusTimerState) -> int:
    elapsed = int(timer_state.accumulated_seconds or 0)
    if timer_state.status != FocusTimerStatus.RUNNING:
        return max(0, elapsed)
    segment_started_at = parse_iso_datetime(str(timer_state.segment_started_at or ""))
    if not segment_started_at:
        return max(0, elapsed)
    now = datetime.now(segment_started_at.tzinfo or timezone.utc)
    return max(0, elapsed + int((now - segment_started_at).total_seconds()))


@fragment_compat(run_every="1s")
def render_live_focus_timer(timer_state_payload: dict) -> None:
    timer_state = FocusTimerState.model_validate(timer_state_payload)
    elapsed_seconds = timer_elapsed_seconds_from_state(timer_state)
    remaining_seconds = max(timer_state.planned_minutes * 60 - elapsed_seconds, 0)
    col_elapsed, col_remaining, col_pauses = st.columns(3)
    col_elapsed.metric("已专注", format_duration(elapsed_seconds))
    col_remaining.metric("剩余", format_duration(remaining_seconds))
    col_pauses.metric("暂停", timer_state.pause_count)


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
                title = html.escape(str(session.get("task_title") or "临时专注任务"))
                subject = html.escape(str(session.get("subject") or "未指定"))
                status = html.escape(render_status_badge(session.get("completion_status", "")))
                planned = int(session.get("planned_minutes") or 0)
                actual = round(int(session.get("actual_seconds") or 0) / 60, 1)
                html_content = '<div class="kaoyan-card">'
                html_content += f'<div class="kaoyan-card-title">{title} / {subject}</div>'
                html_content += (
                    f'<div class="kaoyan-muted">计划 {planned} 分钟 / '
                    f'实际 {actual} 分钟 / 状态：{status}</div>'
                )
                html_content += '</div>'
                st.html(html_content)
