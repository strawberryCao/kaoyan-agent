import sqlite3

import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.services.local_yolo_focus_recognizer import (
    LocalYoloFocusRecognizer,
    diagnose_camera_access,
    find_yolo_weight_candidates,
)
from kaoyan_agent.ui.components.common import (
    render_json_debug_expander,
    render_metric_card,
    render_page_header,
)
from kaoyan_agent.ui.components.memory_panel import render_memory_panel
from kaoyan_agent.workflows.settings_workflow import SettingsWorkflow


def render_settings_page(settings: Settings) -> None:
    render_page_header(
        "设置",
        "只显示演示和排查真正需要的状态；敏感配置不明文展示。",
    )

    with st.spinner("加载设置状态..."):
        data = SettingsWorkflow().load_settings(settings=settings, memory_limit=1)
        candidates = find_yolo_weight_candidates(settings.yolo_focus_weights_path)
        recognizer = LocalYoloFocusRecognizer(
            candidates[0] if candidates else settings.yolo_focus_weights_path,
            confidence_threshold=settings.yolo_focus_confidence_threshold,
            person_weights_path=settings.yolo_person_weights_path,
            person_confidence_threshold=settings.yolo_person_confidence_threshold,
            phone_confidence_threshold=settings.focus_phone_confidence_threshold,
            visual_evidence_threshold=settings.focus_visual_evidence_threshold,
            presence_focus_confidence_threshold=settings.focus_presence_focus_confidence_threshold,
            camera_id=settings.yolo_focus_camera_id,
            check_camera=False,
        )
        camera = diagnose_camera_access(settings.yolo_focus_camera_id)

        col_model, col_key, col_db = st.columns(3)
        with col_model:
            render_metric_card("当前模型", data["model"])
        with col_key:
            render_metric_card(
                "API Key", "已配置" if settings.llm_api_key else "未配置"
            )
        with col_db:
            render_metric_card(
                "数据库", "可连接" if database_available(settings) else "不可连接"
            )

        col_yolo, col_camera, col_fps = st.columns(3)
        with col_yolo:
            render_metric_card(
                "视觉证据模型",
                "完整可用" if recognizer.is_fully_available() else "降级" if recognizer.is_available() else "不可用",
                recognizer.status_message() or f"候选权重 {len(candidates)} 个",
            )
        with col_camera:
            render_metric_card(
                "摄像头",
                "可打开" if camera.get("can_open") else "不可打开",
                f"camera_id={settings.yolo_focus_camera_id}",
            )
        with col_fps:
            render_metric_card("识别 FPS", settings.yolo_focus_inference_fps)

        col_phone, col_visual, col_presence = st.columns(3)
        with col_phone:
            render_metric_card("手机阈值", settings.focus_phone_confidence_threshold)
        with col_visual:
            render_metric_card("视觉证据阈值", settings.focus_visual_evidence_threshold)
        with col_presence:
            render_metric_card("人在场专注阈值", settings.focus_presence_focus_confidence_threshold)

        col_legacy, _, _ = st.columns(3)
        with col_legacy:
            render_metric_card("旧行为模型", "仅诊断", f"候选 {len(candidates)} 个")

        with st.expander("详细路径与诊断", expanded=False):
            st.markdown("**Base URL**")
            st.caption(settings.llm_base_url or "使用默认服务地址")
            st.markdown("**数据库路径**")
            st.caption(str(settings.database_path))
            render_json_debug_expander(
                "YOLO 诊断",
                {
                    "weights_candidates": [str(path) for path in candidates],
                    "recognizer": recognizer.debug,
                    "camera": camera,
                },
            )

        render_memory_panel(settings)


def database_available(settings: Settings) -> bool:
    try:
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
