from __future__ import annotations

from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.db.database import get_connection, json_dumps, json_loads, rows_to_dicts, utc_now


NODE_LABELS = {
    "raw_event": "RawEvent",
    "rawevent": "RawEvent",
    "memory": "Memory",
    "episodic_memory": "EpisodicMemory",
    "episodicmemory": "EpisodicMemory",
    "semantic_memory": "SemanticMemory",
    "semanticmemory": "SemanticMemory",
    "daily_memory_graph": "DailyMemoryGraph",
    "dailymemorygraph": "DailyMemoryGraph",
    "problem": "Problem",
    "mistake_card": "MistakeCard",
    "mistakecard": "MistakeCard",
    "study_task": "StudyTask",
    "studytask": "StudyTask",
    "focus_session": "FocusSession",
    "focussession": "FocusSession",
    "skill": "Skill",
    "action": "Action",
}

RELATION_TYPES = {
    "EVIDENCE_OF",
    "DERIVED_FROM",
    "RELATED_TO",
    "SUGGESTS",
    "CREATED_FROM",
    "UPDATED_BY",
    "CAUSED_BY",
    "PART_OF_DAILY_GRAPH",
}

RELATION_ALIASES = {
    "evidence_of": "EVIDENCE_OF",
    "derived_from": "DERIVED_FROM",
    "related_to": "RELATED_TO",
    "relates_to": "RELATED_TO",
    "supports": "RELATED_TO",
    "suggests": "SUGGESTS",
    "created_from": "CREATED_FROM",
    "updated_by": "UPDATED_BY",
    "caused_by": "CAUSED_BY",
    "part_of_daily_graph": "PART_OF_DAILY_GRAPH",
    "part_of": "PART_OF_DAILY_GRAPH",
}


class SQLiteGraphStore:
    """Compatibility graph table backend for tests and local fallback only."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def upsert_node(
        self,
        *,
        node_key: str,
        node_type: str,
        ref_type: str = "",
        ref_id: Optional[int] = None,
        title: str = "",
        content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        if not node_key:
            return {"status": "skipped", "reason": "missing node_key"}
        now = utc_now()
        with closing(get_connection()) as connection:
            connection.execute(
                """
                INSERT INTO graph_nodes (
                    node_key,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_key) DO UPDATE SET
                    node_type = excluded.node_type,
                    ref_type = excluded.ref_type,
                    ref_id = excluded.ref_id,
                    title = excluded.title,
                    content = excluded.content,
                    metadata_json = excluded.metadata_json,
                    embedding_json = excluded.embedding_json,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    node_key,
                    node_type,
                    ref_type,
                    ref_id,
                    title,
                    content,
                    json_dumps(metadata or {}, {}),
                    json_dumps(embedding or [], []),
                    status,
                    now,
                    now,
                ),
            )
            connection.commit()
        return {"status": "success", "node_key": node_key}

    def upsert_edge(
        self,
        *,
        source_node_key: str,
        target_node_key: str,
        relation_type: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        edge_key: str = "",
    ) -> Dict[str, Any]:
        if not source_node_key or not target_node_key:
            return {"status": "skipped", "reason": "missing source or target"}
        edge_key = edge_key or self.edge_key(source_node_key, target_node_key, relation_type)
        now = utc_now()
        with closing(get_connection()) as connection:
            connection.execute(
                """
                INSERT INTO graph_edges (
                    edge_key,
                    source_node_key,
                    target_node_key,
                    relation_type,
                    weight,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(edge_key) DO UPDATE SET
                    weight = excluded.weight,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    edge_key,
                    source_node_key,
                    target_node_key,
                    relation_type,
                    float(weight),
                    json_dumps(metadata or {}, {}),
                    now,
                    now,
                ),
            )
            connection.commit()
        return {"status": "success", "edge_key": edge_key}

    def get_neighbors(self, node_key: str, depth: int = 1) -> Dict[str, Any]:
        if not node_key:
            return {"nodes": [], "edges": [], "status": self.get_status()}
        with closing(get_connection()) as connection:
            edge_rows = connection.execute(
                """
                SELECT *
                FROM graph_edges
                WHERE source_node_key = ? OR target_node_key = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 80
                """,
                (node_key, node_key),
            ).fetchall()
            edges = rows_to_dicts(edge_rows)
            neighbor_keys = {node_key}
            for edge in edges:
                neighbor_keys.add(str(edge.get("source_node_key") or ""))
                neighbor_keys.add(str(edge.get("target_node_key") or ""))
            keys = [key for key in neighbor_keys if key]
            if keys:
                placeholders = ",".join("?" for _ in keys)
                node_rows = connection.execute(
                    f"SELECT * FROM graph_nodes WHERE node_key IN ({placeholders})",
                    tuple(keys),
                ).fetchall()
            else:
                node_rows = []
        nodes = rows_to_dicts(node_rows)
        for node in nodes:
            node["metadata"] = json_loads(node.get("metadata_json", "{}"), {})
        for edge in edges:
            edge["metadata"] = json_loads(edge.get("metadata_json", "{}"), {})
        return {"nodes": nodes, "edges": edges, "status": self.get_status(), "depth": depth}

    def get_status(self) -> Dict[str, Any]:
        try:
            with closing(get_connection()) as connection:
                node_count = int(connection.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0])
                edge_count = int(connection.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0])
            return {
                "backend": "sqlite_graph",
                "enabled": True,
                "available": True,
                "connected": True,
                "node_count": node_count,
                "edge_count": edge_count,
                "node_labels": [],
                "relationship_types": [],
                "error": "",
            }
        except Exception as exc:
            return {
                "backend": "sqlite_graph",
                "enabled": True,
                "available": False,
                "connected": False,
                "node_count": 0,
                "edge_count": 0,
                "node_labels": [],
                "relationship_types": [],
                "error": str(exc),
            }

    @staticmethod
    def node_key(ref_type: str, ref_id: int) -> str:
        return f"{ref_type}:{ref_id}"

    @staticmethod
    def edge_key(source_node_key: str, target_node_key: str, relation_type: str) -> str:
        return f"{source_node_key}->{relation_type}->{target_node_key}"


class Neo4jGraphStore:
    """Neo4j graph backend for raw_event/memory/problem/action relations."""

    def __init__(self, settings: Optional[Settings] = None, driver: Any = None):
        self.settings = settings or get_settings()
        self._driver = driver
        self._last_error = ""

    def upsert_node(
        self,
        *,
        node_key: str,
        node_type: str,
        ref_type: str = "",
        ref_id: Optional[int] = None,
        title: str = "",
        content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        if not node_key:
            return {"status": "skipped", "reason": "missing node_key"}
        driver = self.get_driver()
        if driver is None:
            return {"status": "unavailable", "error": self._last_error}

        label = self.node_label(node_type)
        now = utc_now()
        try:
            safe_ref_id = int(ref_id) if ref_id not in (None, "") else None
        except (TypeError, ValueError):
            safe_ref_id = None
        properties = {
            "key": node_key,
            "node_key": node_key,
            "node_type": node_type,
            "ref_type": ref_type,
            "ref_id": safe_ref_id,
            "title": title or "",
            "content": content or "",
            "status": status or "active",
            "metadata_json": json_dumps(metadata or {}, {}),
            "embedding_json": json_dumps(embedding or [], []),
            "updated_at": now,
        }
        try:
            with driver.session() as session:
                session.run(
                    f"""
                    MERGE (n:GraphNode:{label} {{key: $node_key}})
                    ON CREATE SET n.created_at = $now
                    SET n += $properties
                    """,
                    node_key=node_key,
                    now=now,
                    properties=properties,
                ).consume()
            return {"status": "success", "node_key": node_key, "backend": "neo4j"}
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": "failed", "error": str(exc)}

    def upsert_edge(
        self,
        *,
        source_node_key: str,
        target_node_key: str,
        relation_type: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        edge_key: str = "",
    ) -> Dict[str, Any]:
        if not source_node_key or not target_node_key:
            return {"status": "skipped", "reason": "missing source or target"}
        driver = self.get_driver()
        if driver is None:
            return {"status": "unavailable", "error": self._last_error}

        relation = self.relation_type(relation_type)
        edge_key = edge_key or self.edge_key(source_node_key, target_node_key, relation)
        now = utc_now()
        try:
            with driver.session() as session:
                session.run(
                    f"""
                    MERGE (s:GraphNode {{key: $source_node_key}})
                    ON CREATE SET
                        s.node_key = $source_node_key,
                        s.node_type = 'unknown',
                        s.created_at = $now,
                        s.updated_at = $now
                    MERGE (t:GraphNode {{key: $target_node_key}})
                    ON CREATE SET
                        t.node_key = $target_node_key,
                        t.node_type = 'unknown',
                        t.created_at = $now,
                        t.updated_at = $now
                    MERGE (s)-[r:{relation} {{edge_key: $edge_key}}]->(t)
                    ON CREATE SET r.created_at = $now
                    SET
                        r.weight = $weight,
                        r.metadata_json = $metadata_json,
                        r.updated_at = $now
                    """,
                    source_node_key=source_node_key,
                    target_node_key=target_node_key,
                    edge_key=edge_key,
                    weight=float(weight),
                    metadata_json=json_dumps(metadata or {}, {}),
                    now=now,
                ).consume()
            return {"status": "success", "edge_key": edge_key, "backend": "neo4j"}
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": "failed", "error": str(exc)}

    def get_neighbors(self, node_key: str, depth: int = 1) -> Dict[str, Any]:
        if not node_key:
            return {"nodes": [], "edges": [], "status": self.get_status(), "depth": depth}
        driver = self.get_driver()
        if driver is None:
            return {"nodes": [], "edges": [], "status": self.get_status(), "depth": depth}

        depth = max(1, min(2, int(depth or 1)))
        try:
            with driver.session() as session:
                records = session.run(
                    f"""
                    MATCH (n:GraphNode {{key: $node_key}})-[r*1..{depth}]-(m:GraphNode)
                    WITH n, m, r
                    UNWIND r AS rel
                    RETURN DISTINCT m AS node, rel AS edge,
                           startNode(rel).key AS source_key,
                           endNode(rel).key AS target_key,
                           type(rel) AS relation_type
                    LIMIT 80
                    """,
                    node_key=node_key,
                )
                nodes: Dict[str, Dict[str, Any]] = {}
                edges: List[Dict[str, Any]] = []
                for record in records:
                    node = record.get("node")
                    edge = record.get("edge")
                    node_data = dict(node) if node is not None else {}
                    node_key_value = str(node_data.get("key") or node_data.get("node_key") or "")
                    if node_key_value:
                        node_data["labels"] = sorted(list(getattr(node, "labels", [])))
                        nodes[node_key_value] = node_data
                    edge_data = dict(edge) if edge is not None else {}
                    edge_data.update(
                        {
                            "source_node_key": record.get("source_key"),
                            "target_node_key": record.get("target_key"),
                            "relation_type": record.get("relation_type"),
                        }
                    )
                    edges.append(edge_data)
            return {
                "nodes": list(nodes.values()),
                "edges": edges,
                "status": self.get_status(),
                "depth": depth,
            }
        except Exception as exc:
            self._last_error = str(exc)
            return {"nodes": [], "edges": [], "status": self.get_status(), "depth": depth, "error": str(exc)}

    def get_status(self) -> Dict[str, Any]:
        status = {
            "backend": "neo4j",
            "enabled": True,
            "available": False,
            "connected": False,
            "uri": self.settings.neo4j_uri,
            "username": self.settings.neo4j_username,
            "node_count": 0,
            "edge_count": 0,
            "node_labels": [],
            "relationship_types": [],
            "sample_nodes": [],
            "sample_edges": [],
            "error": "",
        }
        driver = self.get_driver()
        if driver is None:
            status["error"] = self._last_error or "Neo4j driver unavailable"
            return status
        try:
            with driver.session() as session:
                status["node_count"] = int(session.run("MATCH (n) RETURN count(n) AS count").single()["count"])
                status["edge_count"] = int(session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"])
                status["node_labels"] = self._list_values(session, "CALL db.labels() YIELD label RETURN label")
                status["relationship_types"] = self._list_values(
                    session,
                    "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType",
                )
                status["sample_nodes"] = [
                    dict(record["node"])
                    for record in session.run(
                        "MATCH (n:GraphNode) RETURN n AS node ORDER BY n.updated_at DESC LIMIT 10"
                    )
                ]
                status["sample_edges"] = [
                    {
                        **dict(record["edge"]),
                        "source_node_key": record["source_key"],
                        "target_node_key": record["target_key"],
                        "relation_type": record["relation_type"],
                    }
                    for record in session.run(
                        """
                        MATCH (s:GraphNode)-[r]->(t:GraphNode)
                        RETURN r AS edge, s.key AS source_key, t.key AS target_key, type(r) AS relation_type
                        LIMIT 20
                        """
                    )
                ]
            status["available"] = True
            status["connected"] = True
            return status
        except Exception as exc:
            self._last_error = str(exc)
            status["error"] = str(exc)
            return status

    def get_driver(self) -> Any:
        if self._driver is not None:
            return self._driver
        if not self.settings.neo4j_uri:
            self._last_error = "NEO4J_URI is not configured"
            return None
        if not self.settings.neo4j_username:
            self._last_error = "NEO4J_USERNAME is not configured"
            return None
        if not self.settings.neo4j_password:
            self._last_error = "NEO4J_PASSWORD is not configured"
            return None
        try:
            from neo4j import GraphDatabase
        except ModuleNotFoundError:
            self._last_error = "neo4j package is not installed"
            return None
        try:
            driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_username, self.settings.neo4j_password),
            )
            try:
                driver.verify_connectivity()
            except Exception:
                driver.close()
                raise
            self._driver = driver
            self._last_error = ""
            return self._driver
        except Exception as exc:
            self._last_error = str(exc)
            return None

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    @staticmethod
    def node_key(ref_type: str, ref_id: int) -> str:
        return f"{ref_type}:{ref_id}"

    @staticmethod
    def edge_key(source_node_key: str, target_node_key: str, relation_type: str) -> str:
        return f"{source_node_key}->{relation_type}->{target_node_key}"

    @staticmethod
    def node_label(node_type: str) -> str:
        normalized = (node_type or "").replace("-", "_").replace(" ", "_").lower()
        return NODE_LABELS.get(normalized, "Action")

    @staticmethod
    def relation_type(relation_type: str) -> str:
        normalized = (relation_type or "RELATED_TO").strip()
        alias = RELATION_ALIASES.get(normalized.lower(), normalized.upper())
        return alias if alias in RELATION_TYPES else "RELATED_TO"

    @staticmethod
    def _list_values(session: Any, query: str) -> List[str]:
        try:
            values: List[str] = []
            for record in session.run(query):
                value = record.values()[0]
                values.append(str(value))
            return sorted(set(values))
        except Exception:
            return []


class GraphStore:
    """Compatibility wrapper that selects the configured graph backend."""

    def __init__(self, settings: Optional[Settings] = None, driver: Any = None):
        self.settings = settings or get_settings()
        backend = (self.settings.graph_backend or "none").lower()
        if backend == "neo4j":
            self._store: Any = Neo4jGraphStore(self.settings, driver=driver)
        elif backend == "sqlite_graph":
            self._store = SQLiteGraphStore(self.settings)
        else:
            self._store = None

    def upsert_node(self, **kwargs: Any) -> Dict[str, Any]:
        if self._store is None:
            return {"status": "unavailable", "error": "GRAPH_BACKEND is disabled"}
        return self._store.upsert_node(**kwargs)

    def upsert_edge(self, **kwargs: Any) -> Dict[str, Any]:
        if self._store is None:
            return {"status": "unavailable", "error": "GRAPH_BACKEND is disabled"}
        return self._store.upsert_edge(**kwargs)

    def get_neighbors(self, node_key: str, depth: int = 1) -> Dict[str, Any]:
        if self._store is None:
            return {"nodes": [], "edges": [], "status": self.get_status(), "depth": depth}
        return self._store.get_neighbors(node_key, depth=depth)

    def get_status(self) -> Dict[str, Any]:
        if self._store is None:
            return {
                "backend": self.settings.graph_backend or "none",
                "enabled": False,
                "available": False,
                "connected": False,
                "uri": self.settings.neo4j_uri,
                "node_count": 0,
                "edge_count": 0,
                "node_labels": [],
                "relationship_types": [],
                "error": "GRAPH_BACKEND is disabled",
            }
        return self._store.get_status()

    @staticmethod
    def node_key(ref_type: str, ref_id: int) -> str:
        return f"{ref_type}:{ref_id}"

    @staticmethod
    def edge_key(source_node_key: str, target_node_key: str, relation_type: str) -> str:
        return f"{source_node_key}->{relation_type}->{target_node_key}"
