from __future__ import annotations

import sqlite3

import pytest

import agents.workflow as workflow
from agents.requirement_extraction import extract_requirements
from database.sqlite_manager import SQLiteManager
from exporters.markdown import build_artifacts
from rag.retriever import retrieve_evidence
from sample_inputs.presets import PRESETS, get_preset


def test_mock_extraction_flags_vague_language_and_keeps_source():
    results = extract_requirements(
        "The service should verify a customer's identity quickly and securely.",
        provider="mock",
    )
    assert results[0]["requirement_id"] == "FR-001"
    assert results[0]["source_excerpt"].startswith("The service")
    assert "quickly" in results[0]["ambiguity_flags"]


def test_gemini_without_key_fails_explicitly(monkeypatch):
    import agents.requirement_extraction as extraction

    monkeypatch.setattr(extraction, "GEMINI_API_KEY", None)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        extraction.extract_requirements("A long enough stakeholder requirement.", provider="gemini")


def test_local_retrieval_returns_citable_seed_evidence():
    results = retrieve_evidence("customer identity retention security")
    assert results
    assert results[0]["citation"].startswith("KB-FINANCIAL_SYSTEM_CONTROLS-")


def test_starter_presets_cover_general_cases_and_each_sdlc_model():
    assert get_preset("general_payments")["scenario"] == "Payments"
    assert get_preset("missing") is None
    assert {
        preset["sdlc_focus"]
        for preset in PRESETS.values()
        if preset["sdlc_focus"]
    } == {"Agile", "V-Model", "Spiral", "Incremental"}
    assert all(preset["source_text"].strip() for preset in PRESETS.values())


def test_artifacts_include_traceable_requirement_and_review_notice():
    artifacts = build_artifacts(
        {
            "project_name": "Test Project",
            "scenario": "Onboarding",
            "requirements": [
                {
                    "requirement_id": "FR-001",
                    "statement": "The system must log access to customer identity documents.",
                    "category": "Security",
                    "priority": "High",
                    "risk_level": "High",
                    "risk_notes": ["Review access logging."],
                    "ambiguity_flags": [],
                    "acceptance_criteria": [],
                    "citations": ["KB-TEST-01"],
                    "compliance_notes": [],
                    "security_controls": [],
                }
            ],
            "conflicts": [],
            "validation_issues": ["FR-001 has no measurable acceptance criteria."],
            "sdlc_recommendation": {
                "recommended": "V-Model",
                "confidence": 0.8,
                "preset_focus": "V-Model",
                "gates": [],
            },
        }
    )
    assert "FR-001" in artifacts["srs.md"]
    assert "KB-TEST-01" in artifacts["rtm.md"]
    assert "not a legal interpretation" in artifacts["compliance_matrix.md"]
    assert "**Starter-case focus:** V-Model" in artifacts["sdlc_plan.md"]


def test_sqlite_analysis_and_decision_persist(tmp_path):
    manager = SQLiteManager(tmp_path / "test.db")
    project = {
        "project_id": "p1",
        "name": "Onboarding",
        "scenario": "Digital onboarding",
        "source_name": "notes.txt",
    }
    requirement = {
        "requirement_id": "FR-001",
        "statement": "The system must log privileged access.",
        "citations": ["KB-TEST-01"],
        "acceptance_criteria": ["A test can verify the audit event."],
    }
    manager.save_analysis(
        project,
        [requirement],
        [],
        analysis={
            "evidence": [{"citation": "KB-TEST-01", "excerpt": "Audit controls."}],
            "sdlc_recommendation": {"recommended": "V-Model"},
            "artifacts": {"srs.md": "# SRS"},
            "validation_issues": ["Confirm owner."],
        },
    )
    manager.record_approval("p1", "Compliance Lead", "changes_requested", "Confirm retention.")
    saved = manager.get_project("p1")
    assert saved is not None
    assert saved["requirements"][0]["requirement_id"] == "FR-001"
    assert saved["status"] == "changes_requested"
    assert saved["approvals"][0]["approver"] == "Compliance Lead"
    assert saved["sdlc_recommendation"]["recommended"] == "V-Model"
    assert saved["artifacts"]["srs.md"] == "# SRS"
    with manager.connect() as connection:
        links = connection.execute(
            "SELECT target_type, target_id FROM traceability_links WHERE project_id = 'p1'"
        ).fetchall()
    assert {tuple(row) for row in links} == {
        ("evidence", "KB-TEST-01"),
        ("acceptance_criterion", "FR-001-AC01"),
    }


def test_invalid_approval_is_rejected(tmp_path):
    manager = SQLiteManager(tmp_path / "test.db")
    manager.save_analysis({"project_id": "p2", "name": "P", "scenario": "S"}, [], [])
    with pytest.raises(ValueError, match="Invalid approval"):
        manager.record_approval("p2", "Reviewer", "maybe")


def test_langgraph_workflow_checkpoints_analysis_without_raw_source(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "ARTIFACT_PATH", tmp_path / "artifacts")
    database_path = tmp_path / "workflow.db"
    result = workflow.run_workflow(
        {
            "project_id": "workflow-test",
            "project_name": "Workflow test",
            "scenario": "Payments",
            "stakeholder_role": "Engineering",
            "source_name": "notes.md",
            "source_text": (
                "# PRIVATE_MARKER_NOT_CHECKPOINTED\n"
                "The system must log all payment reversals for review."
            ),
            "provider": "mock",
            "preset_name": "SDLC · V-Model",
            "sdlc_focus": "V-Model",
        },
        database_path=database_path,
    )
    assert result["status"] == "review_required"
    assert result["requirements"][0]["requirement_id"] == "FR-001"
    assert "srs.md" in result["artifacts"]
    assert result["sdlc_recommendation"]["preset_focus"] == "V-Model"
    assert "source_text" not in result
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT checkpoint FROM checkpoints WHERE thread_id = 'workflow-test'"
        ).fetchall()
    assert rows
    assert all(b"PRIVATE_MARKER_NOT_CHECKPOINTED" not in row[0] for row in rows)


def test_hybrid_sdlc_extracts_13_factors_mcda_and_custom_workflow(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "ARTIFACT_PATH", tmp_path / "artifacts")
    preset = get_preset("sdlc_v_model")
    assert preset is not None
    result = workflow.run_workflow(
        {
            "project_id": "hybrid-vmodel",
            "project_name": preset["project_name"],
            "scenario": preset["scenario"],
            "stakeholder_role": preset["stakeholder_role"],
            "source_name": "preset",
            "source_text": preset["source_text"],
            "provider": "mock",
            "preset_name": preset["label"],
            "sdlc_focus": preset["sdlc_focus"],
        },
        database_path=tmp_path / "hybrid.db",
    )
    sdlc = result["sdlc_recommendation"]
    assert len(sdlc["decision_factors"]) == 13
    models = {item["model"] for item in sdlc["ranking"]}
    assert {
        "Waterfall",
        "V-Model",
        "Spiral",
        "Agile",
        "Incremental",
        "DevSecOps",
        "Agile–V-Model Hybrid",
        "Agile–DevSecOps Hybrid",
    } == models
    assert sdlc["recommended"] in {"V-Model", "Agile–V-Model Hybrid"}
    assert len(sdlc["custom_workflow"]) == 5
    first_phase = sdlc["custom_workflow"][0]
    for required_key in (
        "phase",
        "activities",
        "responsible_roles",
        "deliverables",
        "security_activities",
        "testing_requirements",
        "compliance_checkpoints",
        "entry_criteria",
        "exit_criteria",
        "human_approval_gate",
        "traceability_requirements",
    ):
        assert required_key in first_phase
    assert "13 Decision Factors" in result["artifacts"]["sdlc_plan.md"]
    assert "Project-Specific SDLC Workflow" in result["artifacts"]["sdlc_plan.md"]


def test_hybrid_sdlc_uses_gemini_rationale_and_falls_back_on_error(monkeypatch):
    import agents.sdlc_selector as selector

    base_state = {
        "project_name": "Payments",
        "scenario": "Payments",
        "stakeholder_role": "Security",
        "provider": "gemini",
        "requirements": [
            {
                "requirement_id": "FR-001",
                "statement": "The payment service must encrypt cardholder data and log access.",
                "category": "Security",
                "risk_level": "High",
                "ambiguity_flags": [],
                "acceptance_criteria": ["AES-256 verified"],
            }
        ],
        "conflicts": [],
        "evidence": [{"citation": "KB-TEST-01", "excerpt": "Encrypt payment data."}],
    }
    monkeypatch.setattr(selector, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        selector,
        "call_gemini_json",
        lambda prompt: {
            "rationale": "Custom Gemini rationale referencing FR-001.",
            "custom_workflow": [
                {
                    "phase": "1. Secure Design",
                    "activities": ["Threat model FR-001"],
                    "responsible_roles": ["Architect", "Security Team"],
                    "deliverables": ["Threat Model"],
                    "security_activities": ["Key rotation review"],
                    "testing_requirements": ["Penetration test"],
                    "compliance_checkpoints": ["KB-TEST-01 audit"],
                    "entry_criteria": ["FR-001 baselined"],
                    "exit_criteria": ["Zero critical threats"],
                    "human_approval_gate": "Security Team sign-off",
                    "traceability_requirements": "FR-001 -> Threat Model",
                }
            ],
        },
    )
    gemini_result = selector.select_sdlc(base_state)
    assert gemini_result["rationale_source"] == "gemini"
    assert "FR-001" in gemini_result["rationale"]
    assert gemini_result["custom_workflow"][0]["phase"] == "1. Secure Design"

    def _boom(prompt):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(selector, "call_gemini_json", _boom)
    fallback_result = selector.select_sdlc(base_state)
    assert fallback_result["rationale_source"] == "deterministic_fallback"
    assert "503" not in fallback_result["rationale"]
    assert "RuntimeError" in fallback_result["llm_fallback_note"]
    assert len(fallback_result["custom_workflow"]) == 5


def test_multi_stakeholder_approval_gate_requires_all_four_roles(tmp_path):
    manager = SQLiteManager(tmp_path / "approvals.db")
    manager.save_analysis({"project_id": "p-multi", "name": "Multi", "scenario": "Payments"}, [], [])

    status_1 = manager.record_approval("p-multi", "Alice", "approved", "Scope ok", role="Project Manager")
    status_2 = manager.record_approval("p-multi", "Bob", "approved", "Design ok", role="Architect")
    assert status_1 == "pending_stakeholder_signoff"
    assert status_2 == "pending_stakeholder_signoff"

    status_3 = manager.record_approval("p-multi", "Carol", "changes_requested", "Add SAST", role="Security Team")
    assert status_3 == "changes_requested"

    manager.record_approval("p-multi", "Carol", "approved", "SAST added", role="Security Team")
    status_4 = manager.record_approval("p-multi", "Dave", "approved", "Controls verified", role="Compliance Officer")
    assert status_4 == "approved"

    saved = manager.get_project("p-multi")
    assert saved is not None
    assert saved["status"] == "approved"
    assert all(entry["status"] == "approved" for entry in saved["signoff_summary"].values())
