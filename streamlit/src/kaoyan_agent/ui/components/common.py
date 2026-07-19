from __future__ import annotations

import html
from typing import Any, Dict, Iterable

import streamlit as st

STATUS_LABELS = {
    "todo": "待开始",
    "doing": "进行中",
    "done": "已完成",
    "in_progress": "进行中",
    "skipped": "已跳过",
    "delayed": "已延期",
    "unmastered": "未掌握",
    "reviewing": "复习中",
    "mastered": "已掌握",
    "running": "进行中",
    "paused": "已暂停",
    "finished": "已结束",
    "ended": "已结束",
    "idle": "未开始",
    "open": "开放",
    "watching": "观察中",
    "resolved": "已解决",
    "ignored": "已忽略",
    "archived": "已归档",
    "unknown": "未识别",
    "pending_confirmation": "待确认",
    "confirmed": "已确认",
    "dismissed": "已取消",
    "completed": "已完成",
}

SOURCE_LABELS = {
    "manual": "手动",
    "chat": "聊天",
    "agent": "Agent",
    "daily_task": "Agent",
    "fortune_card": "幸运卡",
    "daily_sign": "每日签",
    "random_task": "随机小任务",
    "soothing_task": "安抚签",
    "Problem Board": "问题板",
}

SIGN_LEVEL_LABELS = {
    "top": "上上签",
    "good": "上吉",
    "steady": "稳定签",
    "small": "小吉",
    "calm": "平静签",
}

MISTAKE_REASON_LABELS_ZH = {
    "concept_gap": "概念漏洞",
    "method_gap": "方法迁移不足",
    "calculation_error": "计算错误",
    "careless_error": "审题或粗心",
    "memory_gap": "记忆不牢",
    "expression_gap": "表达不规范",
    "unknown": "待确认",
}


def inject_global_styles() -> None:
    st.html("""
        <style>
            .stAppDeployButton, .stMainMenu {
                display: none !important;
            }
        </style>
    """)
    return

    st.html("""
        <style>
        :root {
            --kaoyan-primary: #9f1239;
            --kaoyan-primary-soft: #fff1f2;
            --kaoyan-bg: #f8fafc;
            --kaoyan-border: #e2e8f0;
            --kaoyan-text-muted: #64748b;
        }
        .stApp {
            background: linear-gradient(180deg, #fff7f8 0%, var(--kaoyan-bg) 220px);
        }
        .main .block-container {
            padding-top: 1.35rem;
            padding-bottom: 2.5rem;
            max-width: 1120px;
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        .kaoyan-card {
            border: 1px solid var(--kaoyan-border);
            border-radius: 8px;
            padding: 14px 16px;
            margin: 8px 0 12px;
            background: rgba(255, 255, 255, 0.94);
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        }
        .kaoyan-card-title {
            font-weight: 700;
            font-size: 1.02rem;
            margin-bottom: 6px;
        }
        .kaoyan-muted {
            color: var(--kaoyan-text-muted);
            font-size: 0.9rem;
        }
        .kaoyan-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 2px 9px;
            margin-right: 6px;
            margin-bottom: 4px;
            background: var(--kaoyan-primary-soft);
            color: var(--kaoyan-primary);
            font-size: 0.84rem;
            line-height: 1.5;
            border: 1px solid #fecdd3;
        }
        .kaoyan-page-subtitle {
            color: #475569;
            margin-top: -0.35rem;
            margin-bottom: 1rem;
        }
        .kaoyan-card-footer {
            color: var(--kaoyan-text-muted);
            font-size: 0.88rem;
            margin-top: 8px;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid var(--kaoyan-border);
            border-radius: 8px;
            padding: 10px 12px;
        }
        div[data-testid="stExpander"] {
            border-color: var(--kaoyan-border);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.72);
        }
        div.stButton > button[kind="primary"] {
            background-color: var(--kaoyan-primary);
            border-color: var(--kaoyan-primary);
        }
        </style>
    """)


def install_card_styles() -> None:
    inject_global_styles()


def render_page_header(title: str, subtitle: str, badge: str | None = None) -> None:
    badge_html = (
        f'<span class="kaoyan-badge">{html.escape(badge)}</span>' if badge else ""
    )
    st.html(f"""
        <h1>{html.escape(title)} {badge_html}</h1>
        <div class="kaoyan-page-subtitle">{html.escape(subtitle)}</div>
    """)


def render_section_title(title: str, caption: str = "") -> None:
    st.subheader(title)
    if caption:
        st.caption(caption)


def render_status_badge(status: str) -> str:
    return STATUS_LABELS.get(str(status or ""), str(status or "未指定"))


def render_card(
    title: str,
    body: str | None = None,
    footer: str | None = None,
    badge: str | None = None,
) -> None:
    escaped_title = html.escape(title)
    escaped_body = html.escape(body) if body else ""
    escaped_footer = html.escape(footer) if footer else ""
    badge_html = (
        f'<span class="kaoyan-badge">{html.escape(badge)}</span>' if badge else ""
    )
    st.html(f"""
        <div class="kaoyan-card">
            {badge_html}
            <div class="kaoyan-card-title">{escaped_title}</div>
            {f'<div>{escaped_body}</div>' if body else ''}
            {f'<div class="kaoyan-card-footer">{escaped_footer}</div>' if footer else ''}
        </div>
    """)


def render_metric_card(label: str, value: Any, helper: str | None = None) -> None:
    escaped_label = html.escape(label)
    escaped_value = html.escape(str(value))
    escaped_helper = html.escape(helper) if helper else ""
    st.html(f"""
        <div class="kaoyan-card">
            <div style="font-size:0.85rem;color:var(--kaoyan-text-muted);">{escaped_label}</div>
            <div style="font-size:1.5rem;font-weight:600;margin:4px 0;">{escaped_value}</div>
            {f'<div style="font-size:0.85rem;color:var(--kaoyan-text-muted);">{escaped_helper}</div>' if helper else ''}
        </div>
    """)


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(str(source or ""), str(source or "手动"))


def sign_level_label(level: str) -> str:
    return SIGN_LEVEL_LABELS.get(str(level or ""), str(level or "平静签"))


def mistake_reason_label(reason: str) -> str:
    return MISTAKE_REASON_LABELS_ZH.get(str(reason or ""), str(reason or "待确认"))


def render_kv(items: Iterable[tuple[str, Any]]) -> None:
    for label, value in items:
        st.markdown(f"**{label}：** {value if value not in (None, '') else '未指定'}")


def render_task_card(task: Dict[str, Any], today: str = "") -> None:
    title = str(task.get("title") or task.get("display_title") or "未命名任务")
    subject = str(task.get("subject") or "未指定")
    minutes = int(task.get("minutes") or task.get("estimated_minutes") or 25)
    status = str(
        task.get("status_label")
        or render_status_badge(str(task.get("status") or "todo"))
    )
    source = str(
        task.get("source_label") or source_label(str(task.get("source") or "manual"))
    )
    escaped_title = html.escape(title)
    escaped_subject = html.escape(subject)
    escaped_status = html.escape(status)
    escaped_source = html.escape(source)
    escaped_today = html.escape(today) if today else ""
    st.html(f"""
        <div class="kaoyan-card">
            <div class="kaoyan-card-title">{escaped_title}</div>
            <span class="kaoyan-badge">{escaped_status}</span>
            <span class="kaoyan-badge">{escaped_subject}</span>
            <span class="kaoyan-badge">{minutes} 分钟</span>
            <span class="kaoyan-badge">{escaped_source}</span>
            {f'<div style="font-size:0.85rem;color:var(--kaoyan-text-muted);margin-top:6px;">日期：{escaped_today}</div>' if today else ''}
        </div>
    """)


def render_debug_expander(debug: Any, title: str = "开发调试信息") -> None:
    render_json_debug_expander(title, debug)


def render_json_debug_expander(title: str, payload: Any) -> None:
    if payload in (None, "", {}, []):
        return
    with st.expander(title, expanded=False):
        st.json(payload)


def render_empty_state(
    title: str, description: str, action_hint: str | None = None
) -> None:
    body = description
    if action_hint:
        body = f"{description}\n\n{action_hint}"
    render_card(title, body=body, badge="暂无数据")


def render_friendly_error(message: str, debug: Any = None) -> None:
    st.info(message)
    render_debug_expander(debug)


def render_error_hint(message: str, debug: Any = None) -> None:
    st.info(message)
    render_json_debug_expander("开发调试信息", debug)
