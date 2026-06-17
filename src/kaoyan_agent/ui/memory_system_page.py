from contextlib import closing

import streamlit as st

from kaoyan_agent.db.database import get_connection, json_loads, rows_to_dicts
from kaoyan_agent.memory.retriever import MemoryRetriever
from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.nightly_review_repository import NightlyReviewRepository
from kaoyan_agent.schemas.contracts import RouterDecision
from kaoyan_agent.services.memory_backend_audit import (
    MemoryBackendAudit,
    NO_GRAPH_MESSAGE,
    NO_VECTOR_MESSAGE,
)
from kaoyan_agent.ui.components.common import (
    inject_global_styles,
    render_card,
    render_json_debug_expander,
    render_metric_card,
    render_page_header,
    render_status_badge,
)


def render_memory_system_page() -> None:
    inject_global_styles()
    render_page_header(
        "记忆系统",
        "审计原始证据、长期记忆、问题看板、向量检索和图谱数据库落地状态。",
        badge="Agent 诊断",
    )

    with st.spinner("审计记忆系统..."):
        audit = MemoryBackendAudit().run()
        tabs = st.tabs(["总览", "长期记忆", "向量检索", "图谱", "原始事件", "夜间回顾"])
        with tabs[0]:
            render_overview(audit)
        with tabs[1]:
            render_long_term_memories()
        with tabs[2]:
            render_vector_tab(audit)
        with tabs[3]:
            render_graph_tab(audit)
        with tabs[4]:
            render_raw_events_tab()
        with tabs[5]:
            render_nightly_tab()


def render_overview(audit: dict) -> None:
    counts = audit.get("counts") or {}
    vector = audit.get("vector") or {}
    graph = audit.get("graph") or {}
    sql = audit.get("sql") or {}

    cols = st.columns(4)
    cols[0].metric("原始事件", counts.get("raw_events", 0))
    cols[1].metric("长期记忆", counts.get("memories", 0))
    cols[2].metric("问题看板", counts.get("problem_board", 0))
    cols[3].metric("错题卡", counts.get("mistake_cards", 0))

    render_metric_card(
        "SQLite 主库",
        sql.get("backend", "sqlite"),
        helper=f"表数：{sql.get('database_tables', 0)}",
    )
    render_metric_card(
        "Chroma 向量库",
        "可用" if vector.get("available") else "错误",
        helper=f"collections: {vector.get('collections', {})} \n docs: {vector.get('documents_count', 0)}",
    )
    render_metric_card(
        "Neo4j 图数据库",
        "已连接" if graph.get("connected") else "错误",
        helper=f"nodes: {graph.get('node_count', 0)} \n edges: {graph.get('edge_count', 0)}",
    )
    render_metric_card("Retriever", audit.get("retriever_type", "keyword_overlap"))

    latest = audit.get("latest_nightly_review") or {}
    if latest:
        render_card(
            "最近夜间回顾",
            f"{latest.get('review_date')} \n {render_status_badge(latest.get('parse_status', ''))}",
            footer=latest.get("created_at", ""),
        )
    render_json_debug_expander("开发调试信息", audit)


def render_long_term_memories() -> None:
    memories = MemoryRepository().list(limit=80)
    if not memories:
        st.info("暂无长期记忆。夜间回顾通过 Memory Gate 后才会写入。")
        return
    memory_type = st.selectbox(
        "记忆类型",
        ["全部"]
        + sorted({str(memory.get("memory_type") or "strategy") for memory in memories}),
    )
    for memory in memories:
        if memory_type != "全部" and memory.get("memory_type") != memory_type:
            continue
        render_card(
            f"{memory.get('memory_type') or '记忆'} · {render_status_badge(memory.get('status', ''))}",
            str(memory.get("content") or ""),
            footer=(
                f"置信度 {float(memory.get('confidence') or 0):.2f} \n "
                f"有效性 {float(memory.get('effectiveness_score') or 0):.2f} \n "
                f"merge_key: {memory.get('merge_key') or '-'}"
            ),
        )


def render_vector_tab(audit: dict) -> None:
    vector = audit.get("vector") or {}
    embedding = audit.get("embedding") or {}

    if not audit.get("vector_backend_available"):
        st.warning(audit.get("vector_message") or NO_VECTOR_MESSAGE)

    cols = st.columns(3)
    cols[0].metric("Chroma 可用性", str(bool(vector.get("available"))))
    cols[1].metric(
        "文档数量", vector.get("documents_count", vector.get("collection_count", 0))
    )
    cols[2].metric(
        "嵌入模型配置", "configured" if embedding.get("configured") else "missing key"
    )

    render_card(
        "Chroma 状态",
        (
            f"backend: {vector.get('backend', 'none')} \n "
            f"persist_dir: {vector.get('persist_dir', '')} \n "
            f"embedding_model: {vector.get('embedding_model', '')}"
        ),
        footer=f"collections: {vector.get('collection_names', [])} \n counts: {vector.get('collections', {})}",
    )
    if vector.get("error"):
        st.warning(f"Chroma error: {vector.get('error')}")
    if embedding.get("last_error"):
        st.info(f"Embedding status: {embedding.get('last_error')}")

    st.caption(audit.get("retriever_formula", ""))
    query = st.text_input("模拟检索输入", value="数学积分换元总是不会")
    if not st.button("运行向量检索", key="memory_vector_demo"):
        return

    decision = RouterDecision(
        route="chat",
        need_memory=True,
        retrieval_weights={
            "matching_score": 0.55,
            "time_score": 0.2,
            "effectiveness_score": 0.2,
            "heat_score": 0.05,
        },
    )
    items = MemoryRetriever().retrieve(query, decision=decision, limit=8)
    if not items:
        st.info("当前检索没有命中可用记忆或开放问题。")
        return

    for item in items:
        metadata = item.metadata or {}
        render_card(
            f"{item.source_type}:{item.source_id or '-'} · final_score {item.score}",
            item.content[:260],
            footer=(
                f"backend {metadata.get('retrieval_backend', '-')} \n "
                f"vector_similarity {float(metadata.get('vector_similarity') or 0):.3f} \n "
                f"time {float(metadata.get('time_score') or 0):.3f} \n "
                f"effectiveness {float(metadata.get('effectiveness_score') or 0):.3f} \n "
                f"heat {float(metadata.get('heat_score') or 0):.3f} \n "
                f"graph_boost {float(metadata.get('graph_boost') or 0):.3f}"
            ),
        )
        if metadata.get("fallback_reason"):
            st.caption(f"fallback_reason: {metadata.get('fallback_reason')}")


def render_graph_tab(audit: dict) -> None:
    graph = audit.get("graph") or {}
    connected = bool(graph.get("connected"))
    counts = audit.get("counts") or {}

    cols = st.columns(3)
    cols[0].metric("Neo4j 连接状态", "已连接" if connected else "错误")
    cols[1].metric("节点数", graph.get("node_count", 0))
    cols[2].metric("边数", graph.get("edge_count", 0))

    render_card(
        "Neo4j 状态",
        f"backend: {graph.get('backend', 'none')} \n uri: {graph.get('uri', '')}",
        footer=(
            f"labels: {graph.get('node_labels', [])} \n "
            f"relationship types: {graph.get('relationship_types', [])}"
        ),
    )

    render_card(
        "SQLite 每日图谱",
        (
            f"daily_graphs: {counts.get('daily_memory_graphs', 0)} \n "
            f"nodes: {counts.get('daily_graph_nodes', 0)} \n "
            f"edges: {counts.get('daily_graph_edges', 0)}"
        ),
        footer=(
            f"global_graph_nodes: {counts.get('global_graph_nodes', 0)} \n "
            f"global_graph_edges: {counts.get('global_graph_edges', 0)}"
        ),
    )
    render_daily_graph_acceptance_section()

    if not connected:
        st.warning(
            f"{NO_GRAPH_MESSAGE} 失败原因：{graph.get('error') or 'Neo4j 未连接'}"
        )
        return

    nodes = graph.get("sample_nodes") or []
    edges = graph.get("sample_edges") or []
    if not nodes:
        st.info(
            "Neo4j 已连接，但当前暂无节点数据。请运行 scripts / backfill_memory_indexes.py --graph。"
        )
        return

    graph_lines = ["digraph G {", "rankdir=LR;"]
    aliases = {}
    for index, node in enumerate(nodes, start=1):
        node_key = str(node.get("key") or node.get("node_key") or f"node-{index}")
        aliases[node_key] = f"n{index}"
        label = str(node.get("title") or node.get("node_type") or node_key).replace(
            '"', "'"
        )
        graph_lines.append(f'{aliases[node_key]} [label="{label}"];')
    for edge in edges:
        source = str(edge.get("source_node_key") or "")
        target = str(edge.get("target_node_key") or "")
        if source in aliases and target in aliases:
            relation = str(edge.get("relation_type") or "").replace('"', "'")
            graph_lines.append(
                f'{aliases[source]} -> {aliases[target]} [label="{relation}"];'
            )
    graph_lines.append("}")
    st.graphviz_chart("\n".join(graph_lines))

    with st.expander("节点与边列表", expanded=False):
        for node in nodes[:10]:
            st.write(
                f"{node.get('node_type')} · {node.get('key') or node.get('node_key')} · {node.get('title') or ''}"
            )
        for edge in edges[:20]:
            st.write(
                f"{edge.get('source_node_key')} -[{edge.get('relation_type')}]-> "
                f"{edge.get('target_node_key')}"
            )


def render_daily_graph_acceptance_section() -> None:
    graphs = list_recent_daily_graphs(limit=10)
    if not graphs:
        st.info("No Daily Graph records yet. Run a successful Nightly Review first.")
        return

    selected = st.selectbox(
        "Daily Graph",
        graphs,
        format_func=lambda item: (
            f"{item.get('graph_date')} \n review {item.get('review_id')} \n "
            f"nodes {item.get('node_count')} \n edges {item.get('edge_count')}"
        ),
    )
    if not selected:
        return

    nodes = list_daily_graph_nodes(int(selected["id"]), limit=30)
    edges = list_daily_graph_edges(int(selected["id"]), limit=30)
    memories = list_review_memories(int(selected.get("review_id") or 0), limit=20)

    cols = st.columns(4)
    cols[0].metric("daily nodes", len(nodes))
    cols[1].metric("daily edges", len(edges))
    cols[2].metric(
        "episodic",
        len([item for item in memories if item.get("memory_type") == "episodic"]),
    )
    cols[3].metric(
        "semantic",
        len([item for item in memories if item.get("memory_type") == "semantic"]),
    )

    with st.expander("Daily Graph nodes / edges", expanded=False):
        for node in nodes[:20]:
            st.write(
                f"{node.get('node_type')} \n {node.get('node_key')} \n "
                f"{node.get('title') or node.get('content') or ''}"
            )
        for edge in edges[:20]:
            st.write(
                f"{edge.get('source_node_key')} -[{edge.get('relation_type')}]-> "
                f"{edge.get('target_node_key')}"
            )

    with st.expander("Episodic / Semantic memories for this review", expanded=False):
        for memory in memories:
            render_card(
                f"{memory.get('memory_type')} \n memory:{memory.get('id')}",
                str(memory.get("content") or "")[:240],
                footer=f"merge_key: {memory.get('merge_key') or ''}",
            )


def render_raw_events_tab() -> None:
    events = list_recent_raw_events(limit=80)
    if not events:
        st.info("暂无原始事件。")
        return
    source_filter = st.selectbox(
        "来源过滤",
        ["全部"]
        + sorted({str(event.get("source_type") or "manual") for event in events}),
    )
    for event in events:
        if source_filter != "全部" and event.get("source_type") != source_filter:
            continue
        metadata = event.get("metadata") or {}
        render_card(
            f"{event.get('role') or 'system'} · {event.get('source_type') or 'manual'}",
            str(event.get("content") or "")[:180],
            footer=f"{event.get('created_at')} \n session {event.get('session_id') or '-'}",
        )
        render_json_debug_expander("metadata", metadata)


def render_nightly_tab() -> None:
    reviews = NightlyReviewRepository().list_latest(limit=20)
    if not reviews:
        st.info("暂无夜间回顾记录。")
        return
    for review in reviews:
        render_card(
            f"{review.get('review_date')} · {render_status_badge(review.get('parse_status', ''))}",
            str(review.get("daily_summary") or "无摘要"),
            footer=review.get("created_at", ""),
        )
        render_json_debug_expander(
            "结构化摘要",
            {
                "key_events_count": len(review.get("key_events") or []),
                "problems_count": len(review.get("discovered_problems") or []),
                "memory_updates_count": len(review.get("memory_updates") or []),
                "inserted_counts": review.get("inserted_counts") or {},
                "vector_sync_status": (review.get("index_sync_status") or {})
                .get("vector", {})
                .get("status", ""),
                "graph_sync_status": (review.get("index_sync_status") or {})
                .get("graph", {})
                .get("status", ""),
                "error_message": review.get("error_message") or "",
            },
        )


def list_recent_raw_events(limit: int = 80) -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, project_id, session_id, role, source_type, source_id, content, metadata_json, created_at
            FROM raw_events
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    events = rows_to_dicts(rows)
    for event in events:
        event["metadata"] = json_loads(event.get("metadata_json", "{}"), {})
    return events


def list_recent_daily_graphs(limit: int = 10) -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, review_id, graph_date, summary, node_count, edge_count, created_at
            FROM daily_memory_graphs
            ORDER BY graph_date DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_daily_graph_nodes(daily_graph_id: int, limit: int = 30) -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT node_key, node_type, ref_type, ref_id, title, content, confidence
            FROM daily_graph_nodes
            WHERE daily_graph_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (daily_graph_id, limit),
        ).fetchall()
    return rows_to_dicts(rows)


def list_daily_graph_edges(daily_graph_id: int, limit: int = 30) -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT source_node_key, target_node_key, relation_type, weight
            FROM daily_graph_edges
            WHERE daily_graph_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (daily_graph_id, limit),
        ).fetchall()
    return rows_to_dicts(rows)


def list_review_memories(review_id: int, limit: int = 20) -> list[dict]:
    if not review_id:
        return []
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, memory_type, content, confidence, merge_key
            FROM memories
            WHERE review_id = ?
            AND memory_type IN ('episodic', 'semantic')
            ORDER BY id ASC
            LIMIT ?
            """,
            (review_id, limit),
        ).fetchall()
    return rows_to_dicts(rows)
