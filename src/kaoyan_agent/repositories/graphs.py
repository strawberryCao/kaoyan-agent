from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import get_connection, json_dumps, utc_now


class DailyMemoryGraphRepository:
    def create(
        self,
        graph_date: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        summary: str = "",
        source_event_ids: Optional[List[int]] = None,
        review_id: Optional[int] = None,
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
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    graph_date,
                    json_dumps(nodes, []),
                    json_dumps(edges, []),
                    summary,
                    json_dumps(source_event_ids or [], []),
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

