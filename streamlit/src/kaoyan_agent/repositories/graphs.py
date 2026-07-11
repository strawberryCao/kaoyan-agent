from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    get_connection,
    json_dumps,
    json_loads,
    rows_to_dicts,
    utc_now,
)


class DailyMemoryGraphRepository:
    def create(
        self,
        graph_date: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        summary: str = "",
        source_event_ids: Optional[List[int]] = None,
        review_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO daily_memory_graphs (
                    review_id,
                    graph_date,
                    nodes_json,
                    edges_json,
                    summary,
                    source_event_ids_json,
                    node_count,
                    edge_count,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    graph_date,
                    json_dumps(nodes, []),
                    json_dumps(edges, []),
                    summary,
                    json_dumps(source_event_ids or [], []),
                    len(nodes),
                    len(edges),
                    json_dumps(metadata or {}, {}),
                    utc_now(),
                ),
            )
            daily_graph_id = int(cursor.lastrowid)
            self._insert_nodes(connection, daily_graph_id, nodes)
            self._insert_edges(connection, daily_graph_id, edges)
            connection.commit()
            return daily_graph_id

    def list_recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    review_id,
                    graph_date,
                    nodes_json,
                    edges_json,
                    summary,
                    source_event_ids_json,
                    node_count,
                    edge_count,
                    metadata_json,
                    created_at
                FROM daily_memory_graphs
                ORDER BY graph_date DESC, id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        return [self._hydrate_graph(row) for row in rows_to_dicts(rows)]

    def list_by_date(self, graph_date: str) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM daily_memory_graphs
                WHERE graph_date = ?
                ORDER BY id DESC
                """,
                (graph_date,),
            ).fetchall()
        return [self._hydrate_graph(row) for row in rows_to_dicts(rows)]

    def get(self, daily_graph_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                "SELECT * FROM daily_memory_graphs WHERE id = ?",
                (daily_graph_id,),
            ).fetchone()
        return self._hydrate_graph(dict(row)) if row else None

    def get_by_review_id(self, review_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM daily_memory_graphs
                WHERE review_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (review_id,),
            ).fetchone()
        return self._hydrate_graph(dict(row)) if row else None

    def list_nodes(self, daily_graph_id: int) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM daily_graph_nodes
                WHERE daily_graph_id = ?
                ORDER BY id ASC
                """,
                (daily_graph_id,),
            ).fetchall()
        nodes = rows_to_dicts(rows)
        for node in nodes:
            node["metadata"] = json_loads(node.get("metadata_json", "{}"), {})
        return nodes

    def list_edges(self, daily_graph_id: int) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM daily_graph_edges
                WHERE daily_graph_id = ?
                ORDER BY id ASC
                """,
                (daily_graph_id,),
            ).fetchall()
        edges = rows_to_dicts(rows)
        for edge in edges:
            edge["metadata"] = json_loads(edge.get("metadata_json", "{}"), {})
            edge["evidence_event_ids"] = json_loads(edge.get("evidence_json", "[]"), [])
        return edges

    def _hydrate_graph(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        graph["nodes"] = json_loads(graph.get("nodes_json", "[]"), [])
        graph["edges"] = json_loads(graph.get("edges_json", "[]"), [])
        graph["source_event_ids"] = json_loads(graph.get("source_event_ids_json", "[]"), [])
        graph["metadata"] = json_loads(graph.get("metadata_json", "{}"), {})
        return graph

    def _insert_nodes(
        self,
        connection,
        daily_graph_id: int,
        nodes: List[Dict[str, Any]],
    ) -> None:
        for node in nodes:
            connection.execute(
                """
                INSERT INTO daily_graph_nodes (
                    daily_graph_id,
                    node_key,
                    node_type,
                    ref_type,
                    ref_id,
                    title,
                    content,
                    confidence,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    daily_graph_id,
                    str(node.get("node_key") or node.get("node_id") or ""),
                    str(node.get("node_type") or ""),
                    str(node.get("ref_type") or ""),
                    node.get("ref_id"),
                    str(node.get("title") or ""),
                    str(node.get("content") or ""),
                    float(node.get("confidence") or 0.0),
                    json_dumps(node.get("metadata") or {}, {}),
                ),
            )

    def _insert_edges(
        self,
        connection,
        daily_graph_id: int,
        edges: List[Dict[str, Any]],
    ) -> None:
        for edge in edges:
            evidence = edge.get("evidence_event_ids")
            if evidence is None:
                evidence = edge.get("evidence") or []
            connection.execute(
                """
                INSERT INTO daily_graph_edges (
                    daily_graph_id,
                    source_node_key,
                    target_node_key,
                    relation_type,
                    weight,
                    evidence_json,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    daily_graph_id,
                    str(edge.get("source_node_key") or edge.get("source") or ""),
                    str(edge.get("target_node_key") or edge.get("target") or ""),
                    str(edge.get("relation_type") or ""),
                    float(edge.get("weight") or 1.0),
                    json_dumps(evidence, []),
                    json_dumps(edge.get("metadata") or {}, {}),
                ),
            )


class GlobalGraphRepository:
    def upsert_node(
        self,
        *,
        node_key: str,
        node_type: str,
        ref_type: str = "",
        ref_id: Optional[int] = None,
        title: str = "",
        content: str = "",
        status: str = "active",
        confidence: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        now = utc_now()
        with closing(get_connection()) as connection:
            row = connection.execute(
                "SELECT id FROM global_graph_nodes WHERE node_key = ?",
                (node_key,),
            ).fetchone()
            if row:
                node_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE global_graph_nodes
                    SET
                        node_type = ?,
                        ref_type = ?,
                        ref_id = ?,
                        title = ?,
                        content = ?,
                        status = ?,
                        confidence = ?,
                        updated_at = ?,
                        metadata_json = ?
                    WHERE id = ?
                    """,
                    (
                        node_type,
                        ref_type,
                        ref_id,
                        title,
                        content,
                        status,
                        float(confidence),
                        now,
                        json_dumps(metadata or {}, {}),
                        node_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO global_graph_nodes (
                        node_key,
                        node_type,
                        ref_type,
                        ref_id,
                        title,
                        content,
                        status,
                        confidence,
                        updated_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_key,
                        node_type,
                        ref_type,
                        ref_id,
                        title,
                        content,
                        status,
                        float(confidence),
                        now,
                        json_dumps(metadata or {}, {}),
                    ),
                )
                node_id = int(cursor.lastrowid)
            connection.commit()
            return node_id

    def upsert_edge(
        self,
        *,
        source_node_key: str,
        target_node_key: str,
        relation_type: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        edge_key: str = "",
    ) -> int:
        edge_key = edge_key or f"{source_node_key}->{relation_type}->{target_node_key}"
        now = utc_now()
        with closing(get_connection()) as connection:
            row = connection.execute(
                "SELECT id FROM global_graph_edges WHERE edge_key = ?",
                (edge_key,),
            ).fetchone()
            if row:
                edge_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE global_graph_edges
                    SET
                        source_node_key = ?,
                        target_node_key = ?,
                        relation_type = ?,
                        weight = ?,
                        updated_at = ?,
                        metadata_json = ?
                    WHERE id = ?
                    """,
                    (
                        source_node_key,
                        target_node_key,
                        relation_type,
                        float(weight),
                        now,
                        json_dumps(metadata or {}, {}),
                        edge_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO global_graph_edges (
                        edge_key,
                        source_node_key,
                        target_node_key,
                        relation_type,
                        weight,
                        updated_at,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge_key,
                        source_node_key,
                        target_node_key,
                        relation_type,
                        float(weight),
                        now,
                        json_dumps(metadata or {}, {}),
                    ),
                )
                edge_id = int(cursor.lastrowid)
            connection.commit()
            return edge_id

    def list_nodes(self, limit: int = 100) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM global_graph_nodes
                WHERE status = 'active'
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        nodes = rows_to_dicts(rows)
        for node in nodes:
            node["metadata"] = json_loads(node.get("metadata_json", "{}"), {})
        return nodes

    def list_edges(self, limit: int = 200) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM global_graph_edges
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        edges = rows_to_dicts(rows)
        for edge in edges:
            edge["metadata"] = json_loads(edge.get("metadata_json", "{}"), {})
        return edges

    def get_neighbors(self, node_key: str, limit: int = 80) -> Dict[str, Any]:
        with closing(get_connection()) as connection:
            edge_rows = connection.execute(
                """
                SELECT *
                FROM global_graph_edges
                WHERE source_node_key = ? OR target_node_key = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (node_key, node_key, max(1, limit)),
            ).fetchall()
            edges = rows_to_dicts(edge_rows)
            keys = {node_key}
            for edge in edges:
                keys.add(str(edge.get("source_node_key") or ""))
                keys.add(str(edge.get("target_node_key") or ""))
            keys = {key for key in keys if key}
            if keys:
                placeholders = ",".join("?" for _ in keys)
                node_rows = connection.execute(
                    f"SELECT * FROM global_graph_nodes WHERE node_key IN ({placeholders})",
                    tuple(keys),
                ).fetchall()
            else:
                node_rows = []
        nodes = rows_to_dicts(node_rows)
        for node in nodes:
            node["metadata"] = json_loads(node.get("metadata_json", "{}"), {})
        for edge in edges:
            edge["metadata"] = json_loads(edge.get("metadata_json", "{}"), {})
        return {"nodes": nodes, "edges": edges}


class GlobalMemoryGraphRepository:
    """Compatibility repository for the legacy global_memory_* tables."""

    def list_nodes(self, limit: int = 100) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    node_type,
                    ref_type,
                    ref_id,
                    title,
                    content,
                    metadata_json,
                    embedding_json,
                    status,
                    created_at,
                    updated_at
                FROM global_memory_nodes
                WHERE status = 'active'
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        nodes = rows_to_dicts(rows)
        for node in nodes:
            node["metadata"] = json_loads(node.get("metadata_json", "{}"), {})
            node["embedding"] = json_loads(node.get("embedding_json", "[]"), [])
        return nodes

    def upsert_ref_node(
        self,
        node_type: str,
        ref_type: str,
        ref_id: int,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
    ) -> int:
        now = utc_now()
        metadata = metadata or {}
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT id
                FROM global_memory_nodes
                WHERE ref_type = ? AND ref_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (ref_type, ref_id),
            ).fetchone()
            if row:
                node_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE global_memory_nodes
                    SET
                        node_type = ?,
                        title = ?,
                        content = ?,
                        metadata_json = ?,
                        embedding_json = COALESCE(NULLIF(?, '[]'), embedding_json),
                        status = 'active',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        node_type,
                        title,
                        content,
                        json_dumps(metadata, {}),
                        json_dumps(embedding, []),
                        now,
                        node_id,
                    ),
                )
                connection.commit()
                return node_id

            cursor = connection.execute(
                """
                INSERT INTO global_memory_nodes (
                    node_type,
                    ref_type,
                    ref_id,
                    title,
                    content,
                    metadata_json,
                    embedding_json,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    node_type,
                    ref_type,
                    ref_id,
                    title,
                    content,
                    json_dumps(metadata, {}),
                    json_dumps(embedding, []),
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def create_edge(
        self,
        source_node_id: int,
        target_node_id: int,
        relation_type: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        metadata = metadata or {}
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT id
                FROM global_memory_edges
                WHERE source_node_id = ?
                AND target_node_id = ?
                AND relation_type = ?
                LIMIT 1
                """,
                (source_node_id, target_node_id, relation_type),
            ).fetchone()
            if row:
                edge_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE global_memory_edges
                    SET weight = ?, metadata_json = ?
                    WHERE id = ?
                    """,
                    (weight, json_dumps(metadata, {}), edge_id),
                )
                connection.commit()
                return edge_id

            cursor = connection.execute(
                """
                INSERT INTO global_memory_edges (
                    source_node_id,
                    target_node_id,
                    relation_type,
                    weight,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    source_node_id,
                    target_node_id,
                    relation_type,
                    weight,
                    json_dumps(metadata, {}),
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

