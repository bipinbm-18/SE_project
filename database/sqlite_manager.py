"""Small SQLite persistence layer for project outputs and human decisions."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.sdlc_selector import REQUIRED_APPROVAL_ROLES


class SQLiteManager:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    scenario TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'review_required',
                    source_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    analysis_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS requirements (
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    requirement_id TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (project_id, requirement_id)
                );
                CREATE TABLE IF NOT EXISTS conflicts (
                    conflict_id TEXT NOT NULL,
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (project_id, conflict_id)
                );
                CREATE TABLE IF NOT EXISTS traceability_links (
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    requirement_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    PRIMARY KEY (project_id, requirement_id, target_type, target_id)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    approver TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'General Reviewer',
                    decision TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            project_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(projects)")
            }
            if "analysis_json" not in project_columns:
                connection.execute(
                    "ALTER TABLE projects ADD COLUMN analysis_json TEXT NOT NULL DEFAULT '{}'"
                )
            approval_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(approvals)")
            }
            if "role" not in approval_columns:
                connection.execute(
                    "ALTER TABLE approvals ADD COLUMN role TEXT NOT NULL DEFAULT 'General Reviewer'"
                )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_analysis(
        self,
        project: dict[str, Any],
        requirements: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
        analysis: dict[str, Any] | None = None,
    ) -> None:
        now = self._now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO projects
                   (project_id, name, scenario, status, source_name, created_at, analysis_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id) DO UPDATE SET name=excluded.name,
                   scenario=excluded.scenario, status=excluded.status,
                   source_name=excluded.source_name, analysis_json=excluded.analysis_json""",
                (
                    project["project_id"],
                    project["name"],
                    project["scenario"],
                    project.get("status", "review_required"),
                    project.get("source_name", ""),
                    now,
                    json.dumps(analysis or {}, ensure_ascii=False),
                ),
            )
            connection.execute(
                "DELETE FROM requirements WHERE project_id = ?", (project["project_id"],)
            )
            connection.execute(
                "DELETE FROM conflicts WHERE project_id = ?", (project["project_id"],)
            )
            connection.execute(
                "DELETE FROM traceability_links WHERE project_id = ?", (project["project_id"],)
            )
            for requirement in requirements:
                connection.execute(
                    "INSERT INTO requirements(project_id, requirement_id, data_json) VALUES (?, ?, ?)",
                    (
                        project["project_id"],
                        requirement["requirement_id"],
                        json.dumps(requirement, ensure_ascii=False),
                    ),
                )
                for citation in requirement.get("citations", []):
                    connection.execute(
                        """INSERT OR IGNORE INTO traceability_links
                           (project_id, requirement_id, target_type, target_id) VALUES (?, ?, ?, ?)""",
                        (project["project_id"], requirement["requirement_id"], "evidence", citation),
                    )
                for criterion_index, _ in enumerate(
                    requirement.get("acceptance_criteria", []), start=1
                ):
                    connection.execute(
                        """INSERT OR IGNORE INTO traceability_links
                           (project_id, requirement_id, target_type, target_id) VALUES (?, ?, ?, ?)""",
                        (
                            project["project_id"],
                            requirement["requirement_id"],
                            "acceptance_criterion",
                            f"{requirement['requirement_id']}-AC{criterion_index:02d}",
                        ),
                    )
            for conflict in conflicts:
                connection.execute(
                    "INSERT INTO conflicts(project_id, conflict_id, data_json) VALUES (?, ?, ?)",
                    (
                        project["project_id"],
                        conflict["conflict_id"],
                        json.dumps(conflict, ensure_ascii=False),
                    ),
                )
            connection.execute(
                """INSERT INTO audit_events(project_id, event_type, details_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    project["project_id"],
                    "analysis_completed",
                    json.dumps({"requirement_count": len(requirements), "conflict_count": len(conflicts)}),
                    now,
                ),
            )

    @staticmethod
    def summarize_signoffs(approvals: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
        summary = {
            role: {"status": "pending", "approver": "", "notes": "", "created_at": ""}
            for role in REQUIRED_APPROVAL_ROLES
        }
        # Approvals are ordered newest-first; keep the latest decision per required role.
        for item in approvals:
            role = item.get("role")
            if role in summary and summary[role]["status"] == "pending":
                summary[role] = {
                    "status": item.get("decision", "pending"),
                    "approver": item.get("approver", ""),
                    "notes": item.get("notes", ""),
                    "created_at": item.get("created_at", ""),
                }
        return summary

    def record_approval(
        self,
        project_id: str,
        approver: str,
        decision: str,
        notes: str = "",
        role: str = "General Reviewer",
    ) -> str:
        if decision not in {"approved", "rejected", "changes_requested"}:
            raise ValueError(f"Invalid approval decision: {decision}")
        if not approver.strip():
            raise ValueError("Approver name is required.")
        clean_role = role.strip() or "General Reviewer"
        now = self._now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO approvals(project_id, approver, role, decision, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project_id, approver.strip(), clean_role, decision, notes.strip(), now),
            )
            if clean_role in REQUIRED_APPROVAL_ROLES:
                rows = connection.execute(
                    "SELECT approver, role, decision, notes, created_at FROM approvals "
                    "WHERE project_id = ? ORDER BY approval_id DESC",
                    (project_id,),
                ).fetchall()
                summary = self.summarize_signoffs([dict(item) for item in rows])
                statuses = [entry["status"] for entry in summary.values()]
                if "rejected" in statuses:
                    project_status = "rejected"
                elif "changes_requested" in statuses:
                    project_status = "changes_requested"
                elif all(state == "approved" for state in statuses):
                    project_status = "approved"
                else:
                    project_status = "pending_stakeholder_signoff"
            else:
                project_status = decision
            connection.execute(
                "UPDATE projects SET status = ? WHERE project_id = ?", (project_status, project_id)
            )
            connection.execute(
                """INSERT INTO audit_events(project_id, event_type, details_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    project_id,
                    "human_decision",
                    json.dumps(
                        {"approver": approver.strip(), "role": clean_role, "decision": decision}
                    ),
                    now,
                ),
            )
        return project_status

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT project_id, name, scenario, status, source_name, created_at "
                "FROM projects ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if row is None:
                return None
            project = dict(row)
            project.update(json.loads(project.pop("analysis_json") or "{}"))
            project["requirements"] = [
                json.loads(item["data_json"])
                for item in connection.execute(
                    "SELECT data_json FROM requirements WHERE project_id = ? ORDER BY requirement_id",
                    (project_id,),
                ).fetchall()
            ]
            project["conflicts"] = [
                json.loads(item["data_json"])
                for item in connection.execute(
                    "SELECT data_json FROM conflicts WHERE project_id = ? ORDER BY conflict_id",
                    (project_id,),
                ).fetchall()
            ]
            project["approvals"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT approver, role, decision, notes, created_at FROM approvals "
                    "WHERE project_id = ? ORDER BY approval_id DESC",
                    (project_id,),
                ).fetchall()
            ]
            project["signoff_summary"] = self.summarize_signoffs(project["approvals"])
            project["audit_events"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT event_type, details_json, created_at FROM audit_events "
                    "WHERE project_id = ? ORDER BY event_id DESC",
                    (project_id,),
                ).fetchall()
            ]
        return project
