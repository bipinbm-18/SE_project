"""LangGraph SDLC workflow and domain analysis stages."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from agents.requirement_extraction import extract_requirements
from config import ARTIFACT_PATH, DATABASE_PATH, KB_PATH
from exporters.markdown import build_artifacts, persist_artifacts
from rag.retriever import retrieve_evidence


class WorkflowState(TypedDict, total=False):
    project_id: str
    project_name: str
    scenario: str
    stakeholder_role: str
    source_name: str
    source_text: str
    provider: str
    preset_name: str
    sdlc_focus: str | None
    requirements: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    clarification_questions: list[str]
    evidence: list[dict[str, str]]
    sdlc_recommendation: dict[str, Any]
    artifacts: dict[str, str]
    validation_issues: list[str]
    status: str


def _coordinator(state: WorkflowState) -> dict[str, Any]:
    if not state.get("project_id"):
        raise ValueError("A project ID is required.")
    return {"status": "analysis_in_progress", "conflicts": [], "evidence": []}


def _stakeholder_context(state: WorkflowState) -> dict[str, Any]:
    return {
        "stakeholder_context": {
            "role": state.get("stakeholder_role", "Product owner"),
            "scenario": state.get("scenario", "Financial system"),
        }
    }


def _clarify(state: WorkflowState) -> dict[str, Any]:
    questions = []
    for requirement in state.get("requirements", []):
        for flag in requirement.get("ambiguity_flags", []):
            questions.append(
                f"{requirement['requirement_id']}: Please clarify '{flag}' "
                f"for: {requirement['statement'][:180]}"
            )
    return {"clarification_questions": questions}


def _classify(state: WorkflowState) -> dict[str, Any]:
    categories = {
        "Security": ("security", "encrypt", "authentication", "authorization", "access control"),
        "Privacy": ("personal data", "privacy", "consent", "retention", "delete data", "pii"),
        "Compliance": ("regulation", "regulatory", "compliance", "audit", "kyc", "aml", "sanction"),
        "Performance": ("latency", "response time", "throughput", "concurrent", "performance"),
        "Availability": ("availability", "recovery", "uptime", "resilience", "disaster recovery"),
    }
    classified = []
    for original in state.get("requirements", []):
        requirement = dict(original)
        lowered = requirement["statement"].lower()
        requirement["category"] = next(
            (category for category, terms in categories.items() if any(term in lowered for term in terms)),
            "Functional",
        )
        if re.search(r"\b(must|shall|required|mandatory)\b", lowered):
            requirement["priority"] = "High"
        elif requirement["category"] in {"Security", "Privacy", "Compliance"}:
            requirement["priority"] = "High"
        classified.append(requirement)
    return {"requirements": classified}


def _find_conflicts(state: WorkflowState) -> dict[str, Any]:
    requirements = state.get("requirements", [])
    conflicts = []
    for index, left in enumerate(requirements):
        left_text = left["statement"].lower()
        for right in requirements[index + 1 :]:
            right_text = right["statement"].lower()
            left_tokens = set(re.findall(r"[a-z0-9]{4,}", left_text))
            right_tokens = set(re.findall(r"[a-z0-9]{4,}", right_text))
            overlap = left_tokens & right_tokens
            if len(overlap) < 2:
                continue
            left_negative = bool(re.search(r"\b(no|not|never|must not|shall not|cannot)\b", left_text))
            right_negative = bool(re.search(r"\b(no|not|never|must not|shall not|cannot)\b", right_text))
            if left_negative != right_negative:
                conflicts.append(
                    {
                        "conflict_id": f"CF-{len(conflicts) + 1:03d}",
                        "requirement_ids": [left["requirement_id"], right["requirement_id"]],
                        "description": "Potentially conflicting positive and negative statements "
                        f"share terms: {', '.join(sorted(overlap)[:5])}.",
                        "status": "Needs stakeholder review",
                    }
                )
    return {"conflicts": conflicts}


def _compliance(state: WorkflowState) -> dict[str, Any]:
    evidence: list[dict[str, str]] = []
    updated = []
    for original in state.get("requirements", []):
        requirement = dict(original)
        results = retrieve_evidence(requirement["statement"], kb_path=KB_PATH)
        relevant = results if requirement["category"] in {"Compliance", "Privacy", "Security"} else []
        requirement["citations"] = [item["citation"] for item in relevant]
        if requirement["category"] in {"Compliance", "Privacy"}:
            requirement["compliance_notes"] = [
                "Requires accountable compliance/legal review; retrieved material is illustrative, not legal advice."
            ]
            if not relevant:
                requirement["compliance_notes"].append(
                    "No matching local evidence was found. Confirm applicable jurisdiction and primary sources."
                )
        evidence.extend(relevant)
        updated.append(requirement)
    deduplicated = {item["citation"]: item for item in evidence}
    return {"requirements": updated, "evidence": list(deduplicated.values())}


def _security_privacy(state: WorkflowState) -> dict[str, Any]:
    updated = []
    for original in state.get("requirements", []):
        requirement = dict(original)
        statement = requirement["statement"].lower()
        controls = []
        if requirement["category"] in {"Security", "Privacy", "Compliance"}:
            controls.extend(["Define least-privilege access and an auditable control owner"])
        if any(term in statement for term in ("personal data", "customer", "identity", "kyc", "pii")):
            controls.extend(
                [
                    "Document data minimization, purpose, retention, and deletion rules",
                    "Assess encryption and access logging for sensitive data",
                ]
            )
        requirement["security_controls"] = sorted(set(controls))
        updated.append(requirement)
    return {"requirements": updated}


def _risk_analysis(state: WorkflowState) -> dict[str, Any]:
    updated = []
    for original in state.get("requirements", []):
        requirement = dict(original)
        high_impact = requirement["category"] in {"Security", "Privacy", "Compliance", "Availability"}
        requirement["risk_level"] = "High" if high_impact else "Medium"
        requirement["risk_notes"] = (
            ["Failure may expose customers or the institution to control, fraud, privacy, or service risk."]
            if high_impact
            else ["Impact and likelihood need confirmation by the accountable project team."]
        )
        updated.append(requirement)
    return {"requirements": updated}


def _merge_governance(state: WorkflowState) -> dict[str, Any]:
    return {"requirements": state.get("requirements", [])}


def _select_sdlc(state: WorkflowState) -> dict[str, Any]:
    requirements = state.get("requirements", [])
    high_risk = sum(item.get("risk_level") == "High" for item in requirements)
    unstable = sum(bool(item.get("ambiguity_flags")) for item in requirements)
    if high_risk >= max(2, len(requirements) // 2):
        ranked = [("V-Model", 0.88), ("Incremental", 0.78), ("Agile", 0.64), ("Spiral", 0.62)]
        rationale = "The requirement set has significant control or failure impact; explicit verification and evidence gates are prioritized."
    elif unstable:
        ranked = [("Spiral", 0.84), ("Agile", 0.80), ("Incremental", 0.74), ("V-Model", 0.62)]
        rationale = "Unresolved ambiguity favors iterative risk discovery and stakeholder feedback before baselining."
    else:
        ranked = [("Agile", 0.84), ("Incremental", 0.79), ("V-Model", 0.72), ("Spiral", 0.65)]
        rationale = "The current inputs support iterative delivery; retain formal control and acceptance checkpoints."
    ranked.sort(key=lambda item: (-item[1], item[0]))
    preferred = state.get("sdlc_focus")
    if preferred not in {None, "Agile", "V-Model", "Spiral", "Incremental"}:
        raise ValueError(f"Unsupported SDLC preset focus: {preferred!r}")
    if preferred:
        rationale += (
            f" The selected starter case is tailored to {preferred}; "
            "the ranking remains based on the extracted requirements."
        )
    return {
        "sdlc_recommendation": {
            "recommended": ranked[0][0],
            "confidence": ranked[0][1],
            "rationale": rationale,
            "preset_focus": preferred,
            "ranking": [{"model": name, "score": score} for name, score in ranked],
            "gates": [
                "Requirements baseline and named business owner",
                "Security, privacy, and compliance design review",
                "Test evidence and traceability review",
                "Operational readiness and accountable release approval",
            ],
        }
    }


def _documentation(state: WorkflowState) -> dict[str, Any]:
    artifacts = build_artifacts(state)
    persist_artifacts(state["project_id"], artifacts, ARTIFACT_PATH)
    return {"artifacts": artifacts}


def _validation(state: WorkflowState) -> dict[str, Any]:
    issues = []
    for requirement in state.get("requirements", []):
        if not requirement.get("acceptance_criteria"):
            issues.append(f"{requirement['requirement_id']} has no measurable acceptance criteria.")
        if requirement.get("ambiguity_flags"):
            issues.append(f"{requirement['requirement_id']} needs clarification.")
    if state.get("conflicts"):
        issues.append(f"{len(state['conflicts'])} potential conflict(s) need stakeholder review.")
    return {"validation_issues": issues}


def _human_approval(state: WorkflowState) -> dict[str, Any]:
    return {"status": "review_required"}


def create_workflow(database_path: Path | str = DATABASE_PATH, source_text: str = ""):
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph

    if not source_text.strip():
        raise ValueError("Source material is empty.")

    def extract_node(state: WorkflowState) -> dict[str, Any]:
        return {
            "requirements": extract_requirements(
                source_text, provider=state.get("provider", "mock")
            )
        }

    builder = StateGraph(WorkflowState)
    nodes = (
        ("coordinator", _coordinator),
        ("stakeholder_context", _stakeholder_context),
        ("requirement_extraction", extract_node),
        ("clarification", _clarify),
        ("classification", _classify),
        ("conflict_detection", _find_conflicts),
        ("compliance", _compliance),
        ("security_privacy", _security_privacy),
        ("risk_analysis", _risk_analysis),
        ("merge_governance", _merge_governance),
        ("sdlc_selection", _select_sdlc),
        ("documentation", _documentation),
        ("validation", _validation),
        ("human_approval", _human_approval),
    )
    for name, function in nodes:
        builder.add_node(name, function)
    builder.add_edge(START, "coordinator")
    for before, after in zip(
        [name for name, _ in nodes[:-1]],
        [name for name, _ in nodes[1:]],
    ):
        builder.add_edge(before, after)
    builder.add_edge("human_approval", END)

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    return builder.compile(checkpointer=saver)


def run_workflow(input_state: WorkflowState, database_path: Path | str = DATABASE_PATH) -> WorkflowState:
    source_text = input_state.get("source_text", "")
    graph = create_workflow(database_path, source_text=source_text)
    checkpoint_state = {key: value for key, value in input_state.items() if key != "source_text"}
    result = graph.invoke(
        checkpoint_state,
        config={"configurable": {"thread_id": input_state["project_id"]}},
    )
    return result
