import streamlit as st
import sqlite3

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow
from kaoyan_agent.db.database import get_connection


TASK_STATUS_LABELS = {
    "todo": "待办",
    "doing": "进行中",
    "done": "已完成",
    "skipped": "跳过",
    "delayed": "延期",
}

SORT_OPTIONS = {
    "priority": "按优先级排序",
    "time_asc": "按时间升序",
    "time_desc": "按时间降序",
    "subject": "按科目排序",
}

PRIORITY_LEVELS = {
    "高": 3,
    "中": 2,
    "低": 1,
}
PRIORITY_REVERSE = {3: "高", 2: "中", 1: "低"}


def render_task_panel(settings: Settings) -> None:
    today = local_today()
    workspace = WorkspaceWorkflow()
    workflow = PlanningWorkflow(settings)
    
    # 直接从数据库获取任务，确保有 review_priority
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, title, subject, estimated_minutes, status, 
                      review_priority, created_at, updated_at
               FROM study_tasks 
               WHERE scheduled_date = ? OR scheduled_date IS NULL
               ORDER BY 
                   CASE status WHEN 'doing' THEN 1 WHEN 'todo' THEN 2 ELSE 3 END,
                   review_priority DESC,
                   created_at DESC""",
            (today,)
        ).fetchall()
        tasks = [dict(row) for row in rows]
    
    # 添加优先级显示
    for task in tasks:
        priority_val = task.get('review_priority', 2)
        task['priority_display'] = PRIORITY_REVERSE.get(priority_val, "中")
    
    # 统计
    done_count = sum(1 for task in tasks if task.get("status") == "done")
    total_count = len(tasks)
    completion_rate = 0 if total_count == 0 else round(done_count / total_count * 100, 1)
    
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("📊 完成率", f"{completion_rate}%")
    col_b.metric("✅ 已完成", done_count)
    col_c.metric("📋 未完成", total_count - done_count)
    
    # 显示任务表格
    if tasks:
        display_tasks = []
        for task in tasks:
            display_tasks.append({
                "ID": task.get("id"),
                "优先级": task.get('priority_display', '中'),
                "任务": task.get("title", "")[:40],
                "科目": task.get("subject", ""),
                "预计(分钟)": task.get("estimated_minutes", 0),
                "状态": TASK_STATUS_LABELS.get(task.get("status", "todo"), task.get("status")),
            })
        st.dataframe(display_tasks, use_container_width=True)
    else:
        st.info("📭 今天还没有任务")
    
    # ========== 添加任务表单 ==========
    st.markdown("---")
    st.markdown("### ➕ 添加新任务")
    
    with st.form(key="add_task_form", clear_on_submit=True):
        title = st.text_input("任务标题", key="new_task_title")
        subject = st.text_input("科目", key="new_task_subject")
        col1, col2 = st.columns(2)
        with col1:
            estimated_minutes = st.number_input("预计分钟数", min_value=0, max_value=300, value=25, step=5, key="new_task_minutes")
        with col2:
            priority = st.selectbox("优先级", ["高", "中", "低"], index=1, key="new_task_priority")
        
        submitted = st.form_submit_button("✅ 创建任务", use_container_width=True)
        
        if submitted and title.strip():
            priority_value = PRIORITY_LEVELS.get(priority, 2)
            workflow.create_task(
                title=title.strip(),
                subject=subject.strip(),
                estimated_minutes=int(estimated_minutes),
                source="manual",
                scheduled_date=today,
            )
            # 直接更新 review_priority
            with get_connection() as conn:
                conn.execute(
                    "UPDATE study_tasks SET review_priority = ? WHERE title = ? AND created_at = (SELECT MAX(created_at) FROM study_tasks WHERE title = ?)",
                    (priority_value, title.strip(), title.strip())
                )
                conn.commit()
            st.success(f"✅ 任务「{title}」已创建")
            st.rerun()
    
    # ========== 编辑任务 ==========
    if tasks:
        st.markdown("---")
        st.markdown("### ✏️ 编辑任务")
        
        task_options = {f"#{t['id']} {t.get('title', '')[:35]}": t for t in tasks}
        selected_key = st.selectbox("选择要编辑的任务", list(task_options.keys()), key="task_edit_select")
        selected_task = task_options[selected_key]
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_title = st.text_input("新标题", value=selected_task.get('title', ''), key="edit_title")
            new_subject = st.text_input("新科目", value=selected_task.get('subject', ''), key="edit_subject")
            new_minutes = st.number_input("新预计分钟数", value=selected_task.get('estimated_minutes', 25), min_value=5, max_value=300, step=5, key="edit_minutes")
        
        with col2:
            current_priority = selected_task.get('priority_display', '中')
            current_idx = ["高", "中", "低"].index(current_priority) if current_priority in ["高", "中", "低"] else 1
            new_priority = st.selectbox("新优先级", ["高", "中", "低"], index=current_idx, key="edit_priority")
            new_status = st.selectbox("新状态", list(TASK_STATUS_LABELS.values()), 
                                      index=list(TASK_STATUS_LABELS.values()).index(TASK_STATUS_LABELS.get(selected_task.get('status', 'todo'), '待办')),
                                      key="edit_status")
        
        if st.button("💾 保存修改", key="save_edit"):
            priority_value = PRIORITY_LEVELS.get(new_priority, 2)
            status_value = {v: k for k, v in TASK_STATUS_LABELS.items()}.get(new_status, 'todo')
            with get_connection() as conn:
                conn.execute(
                    """UPDATE study_tasks 
                       SET title = ?, subject = ?, estimated_minutes = ?, 
                           review_priority = ?, status = ?, updated_at = ? 
                       WHERE id = ?""",
                    (new_title, new_subject, new_minutes, priority_value, status_value, today, selected_task['id'])
                )
                conn.commit()
            st.success("✅ 任务已更新")
            st.rerun()
        
        # ========== 删除任务 ==========
        st.markdown("---")
        st.markdown("### 🗑️ 删除任务")
        
        delete_options = {f"#{t['id']} {t.get('title', '')[:35]}": t['id'] for t in tasks}
        task_to_delete = st.selectbox("选择要删除的任务", list(delete_options.keys()), key="delete_select")
        
        if st.button("❌ 永久删除", key="delete_task"):
            with get_connection() as conn:
                conn.execute("DELETE FROM study_tasks WHERE id = ?", (delete_options[task_to_delete],))
                conn.commit()
            st.success("✅ 任务已删除")
            st.rerun()
