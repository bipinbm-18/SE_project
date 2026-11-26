"""Generate traceable Markdown deliverables for project review."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def build_artifacts(state: dict[str, Any]) -> dict[str, str]:
    requirements = state.get("requirements", [])
    project = state.get("project_name", "FinSpec project")
    requirements_rows = [
        [
            item["requirement_id"],
            item["statement"],
            item.get("category", ""),
            item.get("priority", ""),
            ", ".join(item.get("ambiguity_flags", [])) or "None flagged",
        ]
        for item in requirements
    ]
    criteria_rows = [
        [item["requirement_id"], criterion]
        for item in requirements
        for criterion in item.get("acceptance_criteria", [])
    ]
    trace_rows = [
        [
            item["requirement_id"],
            ", ".join(item.get("citations", [])) or "No local evidence",
            ", ".join(
                f"{item['requirement_id']}-AC{index:02d}"
                for index, _ in enumerate(item.get("acceptance_criteria", []), start=1)
            ) or "Acceptance criteria needed",
        ]
        for item in requirements
    ]
    compliance_rows = [
        [item["requirement_id"], item["category"], ", ".join(item.get("citations", [])) or "No citation", "Requires human review"]
        for item in requirements
        if item.get("category") in {"Compliance", "Privacy", "Security"}
    ]
    risk_rows = [
        [item["requirement_id"], item.get("risk_level", ""), "; ".join(item.get("risk_notes", []))]
        for item in requirements
    ]
    conflicts = state.get("conflicts", [])
    issues = state.get("validation_issues", [])
    sdlc = state.get("sdlc_recommendation", {})
    artifacts = {
        "srs.md": f"# Software Requirements Specification: {project}\n\n"
        f"Scenario: {state.get('scenario', 'Not specified')}  \n"
        f"Stakeholder role: {state.get('stakeholder_role', 'Not specified')}  \n"
        f"Source: {state.get('source_name', 'Pasted input')}\n\n"
        "## Requirements\n\n"
        + _table(["ID", "Requirement", "Type", "Priority", "Ambiguity"], requirements_rows)
        + "\n\n## Acceptance criteria\n\n"
        + (_table(["Requirement", "Criterion"], criteria_rows) if criteria_rows else "Acceptance criteria require stakeholder confirmation.")
        + "\n\n## Review notice\n\nGenerated content is a draft. Confirm each requirement with its owner before baselining.\n",
        "user_stories.md": "# User stories\n\n"
        + "\n".join(
            f"## {item['requirement_id']}\n\nAs a **financial system stakeholder**, "
            f"I want **{item['statement']}** so that the business outcome can be achieved.\n\n"
            f"**Acceptance criteria:** {'; '.join(item.get('acceptance_criteria', [])) or 'To be defined with the owner.'}"
            for item in requirements
        ),
        "rtm.md": "# Requirements Traceability Matrix\n\n"
        + _table(["Requirement", "Evidence citations", "Acceptance criteria"], trace_rows)
        + "\n\nTrace links are suggestions; owners must confirm source and test coverage.\n",
        "compliance_matrix.md": "# Compliance and control review matrix\n\n"
        + (_table(["Requirement", "Area", "Local evidence", "Disposition"], compliance_rows)
           if compliance_rows else "No compliance, privacy, or security-classified requirements were detected.")
        + "\n\nThis matrix is not a legal interpretation or a compliance attestation. Validate jurisdiction-specific obligations against current primary sources and internal policy.\n",
        "risk_register.md": "# Risk register\n\n"
        + (_table(["Requirement", "Initial risk", "Risk note"], risk_rows) if risk_rows else "No requirements extracted.")
        + "\n\nRisk levels are preliminary screening indicators, not a quantitative assessment.\n",
        "sdlc_plan.md": f"# SDLC recommendation\n\n"
        f"**Recommended approach:** {sdlc.get('recommended', 'Needs review')}  \n"
        f"**Screening score:** {sdlc.get('confidence', 'N/A')}\n\n"
        + (
            f"**Starter-case focus:** {sdlc['preset_focus']} (does not force the recommendation)\n\n"
            if sdlc.get("preset_focus")
            else ""
        )
        + f"{sdlc.get('rationale', '')}\n\n## Suggested gates\n\n"
        + "\n".join(f"- {gate}" for gate in sdlc.get("gates", []))
        + "\n\nScores are heuristic decision support. Project leadership should select and tailor the lifecycle.\n",
        "open_issues.md": "# Open issues\n\n"
        + ("\n".join(f"- {issue}" for issue in issues) if issues else "- No automated validation issues were detected.")
        + ("\n\n## Potential conflicts\n\n" + "\n".join(
            f"- **{conflict['conflict_id']}** ({', '.join(conflict['requirement_ids'])}): {conflict['description']}"
            for conflict in conflicts
        ) if conflicts else "\n\nNo potential conflicts were detected by the basic heuristic.")
        + "\n",
    }
    return artifacts


def persist_artifacts(project_id: str, artifacts: dict[str, str], root: Path | str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", project_id)
    if not safe_id:
        raise ValueError("Project ID does not contain any safe filename characters.")
    destination = Path(root) / safe_id
    destination.mkdir(parents=True, exist_ok=True)
    for filename, content in artifacts.items():
        (destination / filename).write_text(content, encoding="utf-8")
    return destination
