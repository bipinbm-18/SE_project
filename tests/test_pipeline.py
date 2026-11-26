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
