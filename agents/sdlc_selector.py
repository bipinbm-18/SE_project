"""Hybrid SDLC selection engine combining 13 decision factors, MCDA, and LLM rationale."""
from __future__ import annotations

import json
import re
from typing import Any

from agents.requirement_extraction import call_gemini_json
from config import GEMINI_API_KEY

ALLOWED_SDLC_MODELS = (
    "Waterfall",
    "V-Model",
    "Spiral",
    "Agile",
    "Incremental",
    "DevSecOps",
    "Agile–V-Model Hybrid",
    "Agile–DevSecOps Hybrid",
)

LEGACY_PRESET_FOCUSES = {None, "Agile", "V-Model", "Spiral", "Incremental"}

REQUIRED_APPROVAL_ROLES = (
    "Project Manager",
    "Architect",
    "Security Team",
    "Compliance Officer",
)

FACTOR_LABELS: dict[str, str] = {
    "requirement_stability": "Requirement stability",
    "change_frequency": "Frequency of expected changes",
    "regulatory_criticality": "Regulatory criticality",
    "security_risk": "Security risk",
    "project_complexity": "Project complexity",
    "system_size": "System size",
    "legacy_system_dependence": "Legacy-system dependence",
    "continuous_delivery_need": "Need for continuous delivery",
    "formal_verification_need": "Need for formal verification",
    "stakeholder_availability": "Availability of stakeholders",
    "schedule_budget_constraints": "Budget & schedule constraints",
    "testing_documentation_needs": "Testing & documentation needs",
    "failure_consequences": "Consequences of failure",
}

# Ideal target score (0.0-1.0) and importance weight per model across the 13 factors.
# Higher alignment with a factor (1 - |factor_score - ideal|) weighted by importance produces
# a deterministic 0-100% MCDA suitability score for every candidate model.
_MODEL_PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    "Waterfall": {
        "requirement_stability": (0.95, 1.4),
        "change_frequency": (0.05, 1.4),
        "regulatory_criticality": (0.35, 1.0),
        "security_risk": (0.20, 1.0),
        "project_complexity": (0.25, 1.0),
        "system_size": (0.35, 0.8),
        "legacy_system_dependence": (0.30, 0.8),
        "continuous_delivery_need": (0.05, 1.4),
        "formal_verification_need": (0.35, 1.0),
        "stakeholder_availability": (0.25, 0.9),
        "schedule_budget_constraints": (0.50, 0.7),
        "testing_documentation_needs": (0.50, 0.9),
        "failure_consequences": (0.25, 1.1),
    },
    "V-Model": {
        "requirement_stability": (0.85, 1.2),
        "change_frequency": (0.20, 1.1),
        "regulatory_criticality": (0.90, 1.7),
        "security_risk": (0.65, 1.1),
        "project_complexity": (0.55, 0.9),
        "system_size": (0.55, 0.8),
        "legacy_system_dependence": (0.45, 0.7),
        "continuous_delivery_need": (0.15, 1.2),
        "formal_verification_need": (0.90, 1.8),
        "stakeholder_availability": (0.45, 0.7),
        "schedule_budget_constraints": (0.45, 0.7),
        "testing_documentation_needs": (0.95, 1.7),
        "failure_consequences": (0.85, 1.5),
    },
    "Spiral": {
        "requirement_stability": (0.30, 1.5),
        "change_frequency": (0.65, 1.2),
        "regulatory_criticality": (0.60, 0.9),
        "security_risk": (0.75, 1.3),
        "project_complexity": (0.75, 1.3),
        "system_size": (0.65, 0.9),
        "legacy_system_dependence": (0.40, 0.7),
        "continuous_delivery_need": (0.35, 0.8),
        "formal_verification_need": (0.55, 0.8),
        "stakeholder_availability": (0.65, 1.0),
        "schedule_budget_constraints": (0.55, 0.8),
        "testing_documentation_needs": (0.70, 0.9),
        "failure_consequences": (0.85, 1.5),
    },
    "Agile": {
        "requirement_stability": (0.45, 1.0),
        "change_frequency": (0.85, 1.6),
        "regulatory_criticality": (0.25, 1.2),
        "security_risk": (0.25, 1.1),
        "project_complexity": (0.45, 0.8),
        "system_size": (0.45, 0.8),
        "legacy_system_dependence": (0.25, 0.9),
        "continuous_delivery_need": (0.90, 1.7),
        "formal_verification_need": (0.20, 1.2),
        "stakeholder_availability": (0.85, 1.4),
        "schedule_budget_constraints": (0.70, 1.0),
        "testing_documentation_needs": (0.40, 1.0),
        "failure_consequences": (0.30, 1.1),
    },
    "Incremental": {
        "requirement_stability": (0.75, 1.0),
        "change_frequency": (0.40, 0.9),
        "regulatory_criticality": (0.50, 0.8),
        "security_risk": (0.45, 0.8),
        "project_complexity": (0.55, 0.9),
        "system_size": (0.65, 1.1),
        "legacy_system_dependence": (0.90, 1.8),
        "continuous_delivery_need": (0.55, 1.0),
        "formal_verification_need": (0.55, 0.9),
        "stakeholder_availability": (0.60, 0.8),
        "schedule_budget_constraints": (0.85, 1.4),
        "testing_documentation_needs": (0.70, 1.0),
        "failure_consequences": (0.55, 0.9),
    },
    "DevSecOps": {
        "requirement_stability": (0.60, 0.9),
        "change_frequency": (0.65, 1.1),
        "regulatory_criticality": (0.60, 1.0),
        "security_risk": (0.90, 1.7),
        "project_complexity": (0.60, 1.0),
        "system_size": (0.60, 0.9),
        "legacy_system_dependence": (0.35, 0.8),
        "continuous_delivery_need": (0.85, 1.5),
        "formal_verification_need": (0.60, 1.0),
        "stakeholder_availability": (0.75, 1.0),
        "schedule_budget_constraints": (0.60, 0.8),
        "testing_documentation_needs": (0.75, 1.1),
        "failure_consequences": (0.75, 1.2),
    },
    "Agile–V-Model Hybrid": {
        "requirement_stability": (0.65, 1.0),
        "change_frequency": (0.55, 1.1),
        "regulatory_criticality": (0.85, 1.6),
        "security_risk": (0.70, 1.2),
        "project_complexity": (0.65, 1.0),
        "system_size": (0.60, 0.9),
        "legacy_system_dependence": (0.55, 1.0),
        "continuous_delivery_need": (0.55, 1.1),
        "formal_verification_need": (0.85, 1.5),
        "stakeholder_availability": (0.70, 1.0),
        "schedule_budget_constraints": (0.60, 0.9),
        "testing_documentation_needs": (0.85, 1.4),
        "failure_consequences": (0.75, 1.3),
    },
    "Agile–DevSecOps Hybrid": {
        "requirement_stability": (0.60, 0.9),
        "change_frequency": (0.70, 1.3),
        "regulatory_criticality": (0.65, 1.1),
        "security_risk": (0.85, 1.5),
        "project_complexity": (0.60, 1.0),
        "system_size": (0.55, 0.9),
        "legacy_system_dependence": (0.35, 0.8),
        "continuous_delivery_need": (0.80, 1.4),
        "formal_verification_need": (0.60, 1.0),
        "stakeholder_availability": (0.80, 1.2),
        "schedule_budget_constraints": (0.65, 0.9),
        "testing_documentation_needs": (0.75, 1.1),
        "failure_consequences": (0.70, 1.2),
    },
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _level(score: float) -> str:
    if score >= 0.67:
        return "High"
    if score >= 0.38:
        return "Medium"
    return "Low"


def _keyword_ratio(statements: list[str], terms: tuple[str, ...]) -> float:
    if not statements:
        return 0.0
    hits = sum(1 for text in statements if any(term in text for term in terms))
    return hits / len(statements)


def extract_decision_factors(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive all 13 Section-13 SDLC decision factors from analyzed requirements and context."""
    requirements = state.get("requirements", [])
    conflicts = state.get("conflicts", [])
    evidence = state.get("evidence", [])
    scenario = (state.get("scenario") or "").lower()
    stakeholder_role = (state.get("stakeholder_role") or "").lower()
    statements = [item.get("statement", "").lower() for item in requirements]
    total = max(len(requirements), 1)

    ambiguous_count = sum(bool(item.get("ambiguity_flags")) for item in requirements)
    missing_ac_count = sum(not item.get("acceptance_criteria") for item in requirements)
    high_risk_count = sum(item.get("risk_level") == "High" for item in requirements)
    compliance_count = sum(item.get("category") in {"Compliance", "Privacy"} for item in requirements)
    security_count = sum(item.get("category") == "Security" for item in requirements)
    availability_count = sum(item.get("category") == "Availability" for item in requirements)
    distinct_categories = len({item.get("category", "Functional") for item in requirements})

    ambiguous_ratio = ambiguous_count / total
    conflict_ratio = min(len(conflicts) / total, 1.0)
    compliance_ratio = compliance_count / total
    security_ratio = security_count / total
    high_risk_ratio = high_risk_count / total
    missing_ac_ratio = missing_ac_count / total

    change_terms = (
        "increment", "iteration", "backlog", "feedback", "evolve", "evolving",
        "change", "uncertain", "emerging", "prototype", "pilot", "sprint", "adjust",
    )
    uncertainty_terms = (
        "uncertain", "prototype", "pilot", "emerging", "false-positive",
        "rollback", "risk owner", "unknown", "explore",
    )
    reg_terms = (
        "kyc", "aml", "regulat", "compliance", "audit", "disclosure",
        "retention", "jurisdiction", "policy", "sanction", "approval", "sign-off",
        "control mapping", "baseline",
    )
    sec_terms = (
        "security", "encrypt", "auth", "fraud", "access", "identity",
        "pii", "personal data", "privileged", "alert", "suspicious", "privacy",
    )
    legacy_terms = (
        "migration", "migrate", "legacy", "core banking", "reconcil", "batch",
        "source and destination", "settlement", "cut-off", "integration", "external",
    )
    cd_terms = (
        "increment", "sprint", "continuous", "frequent release", "rapid release",
        "ci/cd", "devops", "agile", "customer-visible", "capability slices", "backlog",
    )
    verify_terms = (
        "verif", "validat", "test case", "test evidence", "trace", "audit",
        "reconcil", "confirm", "threshold", "approve", "rule", "reject",
        "baseline", "actor", "timestamp",
    )
    impact_terms = (
        "payment", "settlement", "fraud", "identity", "reconcil", "rollback",
        "escalat", "threshold", "suspicious", "reject", "balance",
    )
    stakeholder_terms = (
        "product owner", "reviewer", "analyst", "operations", "compliance",
        "feedback", "risk owner", "business owner", "review",
    )
    constraint_terms = (
        "phased", "batch", "cut-off", "first release", "later release",
        "budget", "schedule", "deadline", "cost", "milestone", "rollback",
    )

    change_hits = _keyword_ratio(statements, change_terms)
    uncertainty_hits = _keyword_ratio(statements, uncertainty_terms)
    reg_hits = _keyword_ratio(statements, reg_terms)
    sec_hits = _keyword_ratio(statements, sec_terms)
    legacy_hits = _keyword_ratio(statements, legacy_terms)
    cd_hits = _keyword_ratio(statements, cd_terms)
    verify_hits = _keyword_ratio(statements, verify_terms)
    impact_hits = _keyword_ratio(statements, impact_terms)
    stakeholder_hits = _keyword_ratio(statements, stakeholder_terms)
    constraint_hits = _keyword_ratio(statements, constraint_terms)

    regulated_scenario = any(
        key in scenario for key in ("onboarding", "kyc", "payment", "lending", "core banking", "fraud")
    )

    scores: dict[str, tuple[float, str]] = {
        "requirement_stability": (
            _clamp(1.0 - (0.50 * ambiguous_ratio + 0.35 * conflict_ratio + 0.30 * change_hits + 0.35 * uncertainty_hits)),
            f"{ambiguous_count}/{len(requirements)} ambiguous item(s), {len(conflicts)} conflict(s).",
        ),
        "change_frequency": (
            _clamp(0.15 + 0.45 * change_hits + 0.30 * uncertainty_hits + 0.30 * ambiguous_ratio + 0.20 * conflict_ratio),
            f"Iterative/change signals in {round(change_hits * 100)}% of statements; {ambiguous_count} unclear item(s).",
        ),
        "regulatory_criticality": (
            _clamp(0.35 * compliance_ratio + 0.45 * reg_hits + (0.20 if regulated_scenario else 0.0) + (0.10 if evidence else 0.0)),
            f"{compliance_count} compliance/privacy req(s), {len(evidence)} KB citation(s), scenario='{state.get('scenario', '')}'.",
        ),
        "security_risk": (
            _clamp(0.45 * security_ratio + 0.45 * sec_hits + (0.15 if "security" in stakeholder_role or "fraud" in scenario else 0.0)),
            f"{security_count} security-classified req(s); security/PII/fraud keywords in {round(sec_hits * 100)}% of reqs.",
        ),
        "project_complexity": (
            _clamp(0.25 * min(len(requirements) / 8.0, 1.0) + 0.35 * min(distinct_categories / 4.0, 1.0) + 0.25 * conflict_ratio + 0.20 * high_risk_ratio),
            f"{len(requirements)} requirement(s) across {distinct_categories} category/ies and {len(conflicts)} conflict(s).",
        ),
        "system_size": (
            _clamp(0.60 * min(len(requirements) / 10.0, 1.0) + 0.40 * min(distinct_categories / 5.0, 1.0)),
            f"{len(requirements)} extracted requirement(s) spanning {distinct_categories} functional/NFR domain(s).",
        ),
        "legacy_system_dependence": (
            _clamp(0.70 * legacy_hits + (0.25 if "core banking" in scenario or "payment" in scenario else 0.05)),
            f"Migration/reconciliation/integration signals in {round(legacy_hits * 100)}% of requirements.",
        ),
        "continuous_delivery_need": (
            _clamp(0.10 + 0.70 * cd_hits + (0.15 if "product owner" in stakeholder_role else 0.0)),
            f"Incremental/continuous delivery indicators in {round(cd_hits * 100)}% of requirements.",
        ),
        "formal_verification_need": (
            _clamp(0.45 * verify_hits + 0.30 * compliance_ratio + 0.25 * high_risk_ratio),
            f"Verification/audit indicators in {round(verify_hits * 100)}% of statements; {high_risk_count} high-risk item(s).",
        ),
        "stakeholder_availability": (
            _clamp(0.35 + 0.55 * stakeholder_hits),
            f"Active review/owner participation referenced in {round(stakeholder_hits * 100)}% of requirements.",
        ),
        "schedule_budget_constraints": (
            _clamp(0.30 + 0.60 * constraint_hits + (0.10 if len(requirements) >= 5 else 0.0)),
            f"Phased/cut-off/constraint cues in {round(constraint_hits * 100)}% of requirements.",
        ),
        "testing_documentation_needs": (
            _clamp(0.25 + 0.30 * missing_ac_ratio + 0.30 * verify_hits + 0.25 * (compliance_ratio + security_ratio) / 2.0),
            f"{missing_ac_count}/{len(requirements)} missing acceptance criteria; audit/test signals at {round(verify_hits * 100)}%.",
        ),
        "failure_consequences": (
            _clamp(0.35 * high_risk_ratio + 0.35 * impact_hits + 0.20 * uncertainty_hits + 0.15 * (availability_count / total) + (0.15 if regulated_scenario else 0.0)),
            f"{high_risk_count}/{len(requirements)} high-risk requirement(s); domain impact cues at {round(impact_hits * 100)}%.",
        ),
    }

    factors: list[dict[str, Any]] = []
    for key, label in FACTOR_LABELS.items():
        score, detail = scores[key]
        rounded = round(score, 2)
        factors.append(
            {
                "key": key,
                "name": label,
                "score": rounded,
                "percentage": round(rounded * 100),
                "level": _level(rounded),
                "evidence": detail,
            }
        )
    return factors


def score_sdlc_models(factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute deterministic MCDA suitability scores across all 8 SDLC models."""
    factor_map = {item["key"]: float(item["score"]) for item in factors}
    ranked: list[dict[str, Any]] = []

    for model_name, profile in _MODEL_PROFILES.items():
        weighted_sum = 0.0
        total_weight = 0.0
        for factor_key, (ideal, weight) in profile.items():
            actual = factor_map[factor_key]
            alignment = 1.0 - abs(actual - ideal)
            weighted_sum += alignment * weight
            total_weight += weight
        base_score = weighted_sum / total_weight if total_weight else 0.5

        # Deterministic domain rules reinforcing critical financial-system constraints
        rule_adj = 0.0
        reg = factor_map["regulatory_criticality"]
        sec = factor_map["security_risk"]
        ver = factor_map["formal_verification_need"]
        cd = factor_map["continuous_delivery_need"]
        chg = factor_map["change_frequency"]
        stab = factor_map["requirement_stability"]
        leg = factor_map["legacy_system_dependence"]
        fail = factor_map["failure_consequences"]

        if model_name == "V-Model" and reg >= 0.50 and ver >= 0.50 and cd < 0.40:
            rule_adj += 0.12
        elif model_name == "Spiral" and stab <= 0.60 and fail >= 0.45 and chg >= 0.40:
            rule_adj += 0.12
        elif model_name == "Agile" and chg >= 0.50 and cd >= 0.45 and reg < 0.50:
            rule_adj += 0.10
        elif model_name == "Incremental" and leg >= 0.55:
            rule_adj += 0.10
        elif model_name == "DevSecOps" and sec >= 0.50 and cd >= 0.40:
            rule_adj += 0.09
        elif model_name == "Agile–DevSecOps Hybrid" and sec >= 0.45 and cd >= 0.30 and reg >= 0.40:
            rule_adj += 0.09
        elif model_name == "Agile–V-Model Hybrid" and reg >= 0.45 and ver >= 0.40:
            rule_adj += 0.08
        elif model_name == "Waterfall":
            if stab >= 0.85 and chg <= 0.20 and cd <= 0.20 and reg < 0.45 and sec < 0.35 and leg < 0.50:
                rule_adj += 0.05
            if leg >= 0.55 or sec >= 0.45 or reg >= 0.50:
                rule_adj -= 0.08

        final_score = round(_clamp(base_score + rule_adj, 0.0, 0.99), 2)
        ranked.append(
            {
                "model": model_name,
                "score": final_score,
                "percentage": round(final_score * 100),
            }
        )

    ranked.sort(key=lambda item: (-item["score"], item["model"]))
    return ranked


def _build_deterministic_rationale(
    recommended: str,
    factors: list[dict[str, Any]],
    ranking: list[dict[str, Any]],
    preferred: str | None,
) -> str:
    top_factors = sorted(factors, key=lambda item: item["score"], reverse=True)[:3]
    top_summary = ", ".join(f"{item['name']} ({item['percentage']}%)" for item in top_factors)
    runner_up = ranking[1] if len(ranking) > 1 else None
    runner_text = (
        f" Runner-up is {runner_up['model']} ({runner_up['percentage']}%)."
        if runner_up
        else ""
    )
    rationale = (
        f"MCDA weighted scoring across all 13 decision factors ranks {recommended} "
        f"({ranking[0]['percentage']}%) highest, driven primarily by {top_summary}.{runner_text}"
    )
    if preferred:
        rationale += (
            f" The selected starter case is tailored to {preferred}; "
            "the ranking remains based on the extracted requirements."
        )
    return rationale


def _build_deterministic_workflow(
    recommended: str,
    state: dict[str, Any],
    factors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requirements = state.get("requirements", [])
    evidence = state.get("evidence", [])
    req_ids = [item["requirement_id"] for item in requirements[:5]]
    req_span = f"{req_ids[0]}–{req_ids[-1]}" if len(req_ids) > 1 else (req_ids[0] if req_ids else "FR-001")
    citation_note = (
        ", ".join(item["citation"] for item in evidence[:3])
        if evidence
        else "Applicable internal security and regulatory standards"
    )
    factor_map = {item["key"]: item["score"] for item in factors}
    high_sec = factor_map.get("security_risk", 0.0) >= 0.5
    high_reg = factor_map.get("regulatory_criticality", 0.0) >= 0.5
    has_legacy = factor_map.get("legacy_system_dependence", 0.0) >= 0.45

    design_activities = [
        f"Translate {req_span} into domain architecture and data-flow specifications",
        "Define control boundaries, audit logging schemas, and failure-handling paths",
    ]
    if has_legacy:
        design_activities.append("Design legacy-system integration contracts and batch reconciliation checkpoints")

    impl_security = [
        "Run SAST, secret scanning, and dependency vulnerability checks in CI",
        "Enforce least-privilege RBAC and encrypted transport/storage for sensitive data",
    ]
    if high_sec:
        impl_security.append("Verify input validation, rate limiting, and anomaly/fraud telemetry hooks")

    test_reqs = [
        f"Execute traceable functional and negative tests mapped to {req_span}",
        "Verify transaction-integrity, idempotency, and audit-trail completeness",
    ]
    if has_legacy:
        test_reqs.append("Run end-to-end data reconciliation and rollback drills against legacy interfaces")

    compliance_checks = [
        f"Cross-check controls against {citation_note}",
        "Confirm unresolved ambiguity flags and potential conflicts are dispositioned",
    ]
    if high_reg:
        compliance_checks.append("Obtain Compliance Officer sign-off on KYC/AML/privacy disclosures and retention")

    delivery_mode = (
        "Iterative Sprints with Controlled Gates"
        if any(tag in recommended for tag in ("Agile", "DevSecOps", "Incremental", "Spiral"))
        else "Baselined Stage-Gate Execution"
    )

    return [
        {
            "phase": "1. Elicitation, Clarification & Scope Baseline",
            "activities": [
                f"Baseline stakeholder requirements ({req_span}) and resolve flagged ambiguities",
                "Confirm conflict dispositions and measurable acceptance criteria with owners",
            ],
            "responsible_roles": ["Project Manager", "Product Owner", "Business Analyst"],
            "deliverables": ["srs.md", "open_issues.md", "Clarification & Conflict Log"],
            "security_activities": ["Classify PII, credential, and financial-transaction data sensitivity"],
            "testing_requirements": ["Review every requirement for testable acceptance criteria"],
            "compliance_checkpoints": compliance_checks[:1],
            "entry_criteria": ["Stakeholder source material ingested and requirements extracted"],
            "exit_criteria": ["All high-priority requirements have named owners and acceptance criteria"],
            "human_approval_gate": "Project Manager & Product Owner scope sign-off",
            "traceability_requirements": f"Assign unique IDs ({req_span}) linked to verbatim source excerpts in rtm.md",
        },
        {
            "phase": "2. Architecture, Threat Modeling & Control Design",
            "activities": design_activities,
            "responsible_roles": ["Architect", "Security Team", "Compliance Officer"],
            "deliverables": ["Architecture & Data-Flow Spec", "Threat Model", "compliance_matrix.md"],
            "security_activities": [
                "Conduct STRIDE threat modeling and privilege-boundary review",
                "Specify encryption, key management, and tamper-evident audit logging",
            ],
            "testing_requirements": ["Define verification strategy, security test cases, and NFR benchmarks"],
            "compliance_checkpoints": compliance_checks,
            "entry_criteria": ["Baselined requirements and preliminary risk register approved"],
            "exit_criteria": ["Zero unmitigated critical design threats; control mappings approved"],
            "human_approval_gate": "Architect, Security Team & Compliance Officer design review",
            "traceability_requirements": "Link security/compliance controls and KB citations to design components",
        },
        {
            "phase": f"3. Build & Continuous Verification ({delivery_mode})",
            "activities": [
                "Implement capabilities with peer code review and automated CI verification",
                "Instrument structured audit events, operational metrics, and alerting",
            ],
            "responsible_roles": ["Engineering Lead", "Security Team", "QA Lead"],
            "deliverables": ["Tested Build Artifacts", "SAST/DAST Reports", "Updated rtm.md"],
            "security_activities": impl_security,
            "testing_requirements": ["Unit, integration, contract, and security regression suites (>= target coverage)"],
            "compliance_checkpoints": ["Verify audit-event fields (actor, timestamp, outcome) in code review"],
            "entry_criteria": ["Approved architecture, threat model, and test plan"],
            "exit_criteria": ["All automated quality/security gates green; zero open high-severity findings"],
            "human_approval_gate": "Engineering & Security Team build readiness check",
            "traceability_requirements": "Map commits, pull requests, and automated tests to FR IDs",
        },
        {
            "phase": "4. System Validation, UAT & Transaction-Integrity Testing",
            "activities": [
                "Execute end-to-end validation, failure-recovery, and UAT scenarios",
                "Compile test evidence package and reconcile open validation issues",
            ],
            "responsible_roles": ["QA Lead", "Operations", "Compliance Officer"],
            "deliverables": ["UAT Sign-off Report", "Evidence Package", "risk_register.md"],
            "security_activities": ["Validate access controls, session/token handling, and penetration-test fixes"],
            "testing_requirements": test_reqs,
            "compliance_checkpoints": ["Confirm retained test evidence satisfies internal audit and regulatory controls"],
            "entry_criteria": ["Feature-complete build deployed to staging environment"],
            "exit_criteria": ["100% critical/high acceptance criteria passed with retained evidence"],
            "human_approval_gate": "QA, Operations & Compliance Officer validation gate",
            "traceability_requirements": "Complete 100% RTM linkage from FR ID -> AC ID -> Test Evidence -> KB Citation",
        },
        {
            "phase": "5. Multi-Stakeholder Release Gate & Operational Handover",
            "activities": [
                "Review rollback plan, monitoring runbooks, and incident escalation paths",
                "Record final multi-stakeholder sign-off across all 4 governance roles",
            ],
            "responsible_roles": list(REQUIRED_APPROVAL_ROLES),
            "deliverables": ["sdlc_plan.md", "Release Readiness Checklist", "Audit Approval Record"],
            "security_activities": ["Verify production secrets isolation, alerting thresholds, and access recertification"],
            "testing_requirements": ["Execute post-deployment smoke tests and synthetic transaction checks"],
            "compliance_checkpoints": ["Archive immutable approval log and compliance disposition before production cutover"],
            "entry_criteria": ["Validation gate passed and operational runbooks complete"],
            "exit_criteria": ["All 4 required stakeholder roles (PM, Architect, Security, Compliance) recorded 'approved'"],
            "human_approval_gate": "Multi-stakeholder final release approval (PM, Architect, Security, Compliance)",
            "traceability_requirements": "Lock immutable baseline linking requirements, evidence, test results, and sign-offs",
        },
    ]


def _enrich_with_gemini(
    state: dict[str, Any],
    factors: list[dict[str, Any]],
    ranking: list[dict[str, Any]],
    preferred: str | None,
) -> tuple[str, list[dict[str, Any]]] | None:
    if not GEMINI_API_KEY:
        return None
    requirements = state.get("requirements", [])
    req_brief = [
        {
            "id": item.get("requirement_id"),
            "category": item.get("category"),
            "risk_level": item.get("risk_level"),
            "statement": item.get("statement", "")[:200],
            "ambiguity_flags": item.get("ambiguity_flags", []),
        }
        for item in requirements[:12]
    ]
    schema_hint = {
        "rationale": "2-4 sentence tailored explanation referencing specific requirement IDs, project risks, and why the top MCDA model fits best.",
        "custom_workflow": [
            {
                "phase": "Phase name",
                "activities": ["..."],
                "responsible_roles": ["..."],
                "deliverables": ["..."],
                "security_activities": ["..."],
                "testing_requirements": ["..."],
                "compliance_checkpoints": ["..."],
                "entry_criteria": ["..."],
                "exit_criteria": ["..."],
                "human_approval_gate": "...",
                "traceability_requirements": "...",
            }
        ],
    }
    prompt = (
        "You are an SDLC governance architect for financial systems. "
        "Given the deterministic 13 decision factors and MCDA ranking below, write:\n"
        "1) A concise, project-specific rationale explaining why the top-ranked model fits "
        "(do NOT change the ranking).\n"
        "2) A 5-phase custom_workflow tailored to this project's actual requirements, risks, and controls.\n"
        f"Project: {state.get('project_name', '')} | Scenario: {state.get('scenario', '')} | "
        f"Starter focus: {preferred or 'None'}\n"
        f"Top MCDA model: {ranking[0]['model']} ({ranking[0]['percentage']}%)\n"
        f"MCDA ranking: {json.dumps(ranking)}\n"
        f"13 Decision factors: {json.dumps(factors)}\n"
        f"Extracted requirements: {json.dumps(req_brief)}\n\n"
        f"Return JSON only matching this shape:\n{json.dumps(schema_hint)}"
    )
    payload = call_gemini_json(prompt)
    if not isinstance(payload, dict):
        return None
    rationale = str(payload.get("rationale", "")).strip()
    workflow_phases = payload.get("custom_workflow")
    if not rationale or not isinstance(workflow_phases, list) or not workflow_phases:
        return None
    normalized_phases: list[dict[str, Any]] = []
    list_fields = (
        "activities",
        "responsible_roles",
        "deliverables",
        "security_activities",
        "testing_requirements",
        "compliance_checkpoints",
        "entry_criteria",
        "exit_criteria",
    )
    for idx, phase in enumerate(workflow_phases, start=1):
        if not isinstance(phase, dict) or not phase.get("phase"):
            continue
        item: dict[str, Any] = {"phase": str(phase["phase"])}
        for field in list_fields:
            raw_val = phase.get(field, [])
            if isinstance(raw_val, list):
                item[field] = [str(entry) for entry in raw_val if str(entry).strip()]
            elif raw_val:
                item[field] = [str(raw_val)]
            else:
                item[field] = []
        item["human_approval_gate"] = str(
            phase.get("human_approval_gate") or f"Phase {idx} governance sign-off"
        )
        item["traceability_requirements"] = str(
            phase.get("traceability_requirements") or "Maintain FR-to-test-to-evidence traceability in RTM"
        )
        normalized_phases.append(item)
    if not normalized_phases:
        return None
    return rationale, normalized_phases


def select_sdlc(state: dict[str, Any]) -> dict[str, Any]:
    """Run hybrid SDLC selection: 13 factors -> deterministic MCDA -> LLM/fallback workflow."""
    preferred = state.get("sdlc_focus")
    if preferred not in LEGACY_PRESET_FOCUSES and preferred not in ALLOWED_SDLC_MODELS:
        raise ValueError(f"Unsupported SDLC preset focus: {preferred!r}")

    factors = extract_decision_factors(state)
    ranking = score_sdlc_models(factors)
    recommended = ranking[0]["model"]
    confidence = ranking[0]["score"]

    rationale = _build_deterministic_rationale(recommended, factors, ranking, preferred)
    custom_workflow = _build_deterministic_workflow(recommended, state, factors)
    rationale_source = "deterministic"
    llm_fallback_note = ""

    if state.get("provider") == "gemini":
        try:
            enriched = _enrich_with_gemini(state, factors, ranking, preferred)
            if enriched is not None:
                rationale, custom_workflow = enriched
                rationale_source = "gemini"
        except Exception as exc:
            rationale_source = "deterministic_fallback"
            llm_fallback_note = f"Gemini rationale generation unavailable ({type(exc).__name__}); used deterministic fallback."

    gates = [f"{phase['phase']}: {phase['human_approval_gate']}" for phase in custom_workflow]

    return {
        "recommended": recommended,
        "confidence": confidence,
        "percentage": ranking[0]["percentage"],
        "rationale": rationale,
        "rationale_source": rationale_source,
        "llm_fallback_note": llm_fallback_note,
        "preset_focus": preferred,
        "decision_factors": factors,
        "ranking": ranking,
        "custom_workflow": custom_workflow,
        "required_approvers": list(REQUIRED_APPROVAL_ROLES),
        "gates": gates,
    }
