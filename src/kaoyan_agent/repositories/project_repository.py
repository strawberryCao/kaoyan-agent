from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    DEFAULT_PROJECT_NAME,
    ensure_default_project_id,
    get_connection,
    json_dumps,
    json_loads,
    rows_to_dicts,
    utc_now,
)


class ProjectRepository:
    def ensure_default_project(self) -> Dict[str, Any]:
        with closing(get_connection()) as connection:
            project_id = ensure_default_project_id(connection)
            connection.commit()
        project = self.get_project(project_id)
        if project is None:
            raise RuntimeError("default project could not be loaded")
        return project

    def get_default_project(self) -> Dict[str, Any]:
        return self.ensure_default_project()

    def create_project(
        self,
        name: str,
        description: str = "",
        exam_year: str = "",
        target_school: str = "",
        target_major: str = "",
        subjects: Optional[List[str]] = None,
    ) -> int:
        name = name.strip() or DEFAULT_PROJECT_NAME
        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects (
                    name,
                    description,
                    exam_year,
                    target_school,
                    target_major,
                    subjects_json,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    name,
                    description.strip(),
                    exam_year.strip(),
                    target_school.strip(),
                    target_major.strip(),
                    json_dumps(subjects or [], []),
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_projects(self, include_archived: bool = False) -> List[Dict[str, Any]]:
        where_clause = "" if include_archived else "WHERE status = 'active'"
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    name,
                    description,
                    exam_year,
                    target_school,
                    target_major,
                    subjects_json,
                    status,
                    created_at,
                    updated_at
                FROM projects
                {where_clause}
                ORDER BY updated_at DESC, id ASC
                """
            ).fetchall()
        return [self._normalize_project(row) for row in rows_to_dicts(rows)]

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    description,
                    exam_year,
                    target_school,
                    target_major,
                    subjects_json,
                    status,
                    created_at,
                    updated_at
                FROM projects
                WHERE id = ?
                """,
                (project_id,),
            ).fetchone()
        return self._normalize_project(dict(row)) if row else None

    def update_project(
        self,
        project_id: int,
        name: str,
        description: str = "",
        exam_year: str = "",
        target_school: str = "",
        target_major: str = "",
        subjects: Optional[List[str]] = None,
    ) -> bool:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET
                    name = ?,
                    description = ?,
                    exam_year = ?,
                    target_school = ?,
                    target_major = ?,
                    subjects_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    name.strip() or DEFAULT_PROJECT_NAME,
                    description.strip(),
                    exam_year.strip(),
                    target_school.strip(),
                    target_major.strip(),
                    json_dumps(subjects or [], []),
                    utc_now(),
                    project_id,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    def _normalize_project(self, project: Dict[str, Any]) -> Dict[str, Any]:
        project["subjects"] = json_loads(project.get("subjects_json", "[]"), [])
        return project

