"""Streamlit interface for the FinSpec AI requirements workbench."""
from __future__ import annotations

import io
import uuid
import zipfile
from pathlib import Path

import streamlit as st
from docx import Document

from agents.workflow import run_workflow
from config import DATABASE_PATH, LLM_PROVIDER, GEMINI_API_KEY
from database.sqlite_manager import SQLiteManager
from sample_inputs.presets import PRESETS

st.set_page_config(page_title="FinSpec AI", page_icon="◈", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: #f5f7fb; }
    [data-testid="stSidebar"] { background: #101b31; }
    [data-testid="stSidebar"] * { color: #e8eefb; }
    .hero { padding: 1.4rem 1.6rem; border-radius: 16px; color: white;
      background: linear-gradient(115deg, #10213d, #175b72); margin-bottom: 1rem; }
    .hero h1 { margin: 0; font-size: 2rem; }
    .hero p { margin: .45rem 0 0 0; color: #d3e6ee; }
    .notice { padding: .8rem 1rem; border-left: 4px solid #d59a28;
      background: #fff5dc; border-radius: 4px; color: #3a3425; }
    </style>
    """,
    unsafe_allow_html=True,
)

manager = SQLiteManager(DATABASE_PATH)


def _read_upload(uploaded_file) -> str:
    raw = uploaded_file.getvalue()
    if len(raw) > 2_000_000:
        raise ValueError("Uploaded file exceeds the 2 MB prototype limit.")
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".docx":
        document = Document(io.BytesIO(raw))
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
    return raw.decode("utf-8", errors="replace")


def _archive(artifacts: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in artifacts.items():
            archive.writestr(filename, content)
    return output.getvalue()


def _apply_preset() -> None:
    preset = PRESETS.get(st.session_state.get("preset_selector", ""))
    if preset:
        st.session_state["project_name"] = preset["project_name"]
        st.session_state["scenario"] = preset["scenario"]
        st.session_state["stakeholder_role"] = preset["stakeholder_role"]
        st.session_state["pasted_text"] = preset["source_text"]


st.sidebar.markdown("## ◈ FinSpec AI")
st.sidebar.caption("Financial requirements & SDLC engineering")
st.sidebar.markdown("---")
st.sidebar.markdown("### Starter cases")
st.sidebar.selectbox(
    "Choose a preset to prefill the analysis form",
    options=[""] + list(PRESETS),
    format_func=lambda preset_id: (
        "Choose a starter case..." if not preset_id else PRESETS[preset_id]["label"]
    ),
    key="preset_selector",
    on_change=_apply_preset,
)
selected_preset = PRESETS.get(st.session_state.get("preset_selector", ""))
if selected_preset:
    st.sidebar.caption(selected_preset["description"])
    if selected_preset["sdlc_focus"]:
        st.sidebar.caption(
            f"SDLC focus: {selected_preset['sdlc_focus']}. The workflow still computes its "
            "own recommendation for comparison."
        )
st.sidebar.markdown("---")
st.sidebar.markdown("### Previous analyses")
projects = manager.list_projects()
if projects:
    selected_id = st.sidebar.selectbox(
        "Open saved project",
        options=[item["project_id"] for item in projects],
        format_func=lambda project_id: next(
            f"{item['name']} · {item['created_at'][:10]}"
            for item in projects
            if item["project_id"] == project_id
        ),
    )
    if st.sidebar.button("Load selected project", use_container_width=True):
        st.session_state["active_project"] = manager.get_project(selected_id)
else:
    st.sidebar.caption("Your saved work will appear here.")

active = st.session_state.get("active_project")
st.markdown(
    '<div class="hero"><h1>FinSpec AI</h1><p>Turn financial-system stakeholder material '
    "into traceable, reviewable engineering artefacts.</p></div>",
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="notice"><b>Governance notice:</b> AI-generated requirements, risk ratings, '
    "and SDLC recommendations are decision support only. They are not legal advice, "
    "compliance attestations, or production approvals. Obtain accountable business, "
    "security, privacy, and compliance review.</div>",
    unsafe_allow_html=True,
)

if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
    st.warning(
        "Gemini mode is configured. Source text submitted for analysis will be sent to Google "
        "Gemini. Do not upload secrets or personal/customer data unless permitted by your "
        "organization's data handling policy."
    )
elif LLM_PROVIDER == "gemini":
    st.error("Gemini mode is selected but GEMINI_API_KEY is missing. Set it in .env to run analysis.")
else:
    st.info("Offline mock mode is active. No source material is sent to an external model.")

with st.sidebar.form("analysis_form"):
    st.markdown("### New analysis")
    project_name = st.text_input(
        "Project name", placeholder="Digital customer onboarding", key="project_name"
    )
    scenario = st.selectbox(
        "Financial-system scenario",
        [
            "Digital onboarding / KYC",
            "Digital lending",
            "Payments",
            "Fraud monitoring",
            "Core banking",
            "Other",
        ],
        key="scenario",
    )
    stakeholder_role = st.selectbox(
        "Stakeholder role",
        ["Product owner", "Compliance", "Security", "Operations", "Engineering", "Customer support"],
        key="stakeholder_role",
    )
    source_file = st.file_uploader("Upload source", type=["txt", "md", "docx"])
    pasted_text = st.text_area(
        "Or paste stakeholder notes",
        height=160,
        placeholder="Paste requirements, interview notes, policy excerpts, or project scope...",
        key="pasted_text",
    )
    use_sample = st.checkbox("Use included digital onboarding example")
    run_clicked = st.form_submit_button("Analyze requirements", type="primary", use_container_width=True)

if run_clicked:
    source_text = pasted_text.strip()
    source_name = "Pasted notes"
    if source_file is not None:
        uploaded_text = _read_upload(source_file)
        source_text = f"{source_text}\n\n{uploaded_text}".strip() if source_text else uploaded_text
        source_name = source_file.name
    elif use_sample and not source_text:
        sample_path = Path(__file__).parent / "sample_inputs" / "digital_onboarding.md"
        source_text = sample_path.read_text(encoding="utf-8")
        source_name = sample_path.name
    if not project_name.strip():
        st.error("Enter a project name before starting an analysis.")
    elif not source_text:
        st.error("Upload or paste source material, or select the sample input.")
    elif LLM_PROVIDER not in {"mock", "gemini"}:
        st.error("LLM_PROVIDER must be either 'mock' or 'gemini'.")
    else:
        project_id = str(uuid.uuid4())
        input_state = {
            "project_id": project_id,
            "project_name": project_name.strip(),
            "scenario": scenario,
            "stakeholder_role": stakeholder_role,
            "source_name": source_name,
            "source_text": source_text,
            "provider": LLM_PROVIDER,
            "preset_name": selected_preset["label"] if selected_preset else "",
            "sdlc_focus": selected_preset["sdlc_focus"] if selected_preset else None,
        }
        with st.spinner("Running the requirements and SDLC workflow..."):
            result = run_workflow(input_state, database_path=DATABASE_PATH)
        project_record = {
            "project_id": project_id,
            "name": project_name.strip(),
            "scenario": scenario,
            "source_name": source_name,
            "status": result.get("status", "review_required"),
        }
        manager.save_analysis(
            project_record,
            result.get("requirements", []),
            result.get("conflicts", []),
            analysis={
                key: result.get(key)
                for key in (
                    "evidence",
                    "sdlc_recommendation",
                    "artifacts",
                    "validation_issues",
                    "preset_name",
                )
            },
        )
        result.update(project_record)
        result["approvals"] = []
        result["audit_events"] = []
        st.session_state["active_project"] = result
        st.rerun()

active = st.session_state.get("active_project")
if active:
    st.markdown(f"## {active['name']}")
    st.caption(
        f"{active.get('scenario', '')} · {active.get('source_name', '')} · "
        f"Status: **{active.get('status', 'review_required').replace('_', ' ').title()}**"
    )
    requirements = active.get("requirements", [])
    conflicts = active.get("conflicts", [])
    st_metrics = st.columns(4)
    st_metrics[0].metric("Requirements", len(requirements))
    st_metrics[1].metric("Potential conflicts", len(conflicts))
    st_metrics[2].metric("Clarification flags", sum(bool(item.get("ambiguity_flags")) for item in requirements))
    st_metrics[3].metric("Validation issues", len(active.get("validation_issues", [])))

    tabs = st.tabs(["Requirements", "Evidence & controls", "SDLC recommendation", "Deliverables", "Approval"])
    with tabs[0]:
        for requirement in requirements:
            with st.expander(
                f"{requirement['requirement_id']} · {requirement.get('category', 'Unclassified')} · "
                f"{requirement.get('priority', 'Medium')}",
                expanded=bool(requirement.get("ambiguity_flags")),
            ):
                st.write(requirement["statement"])
                st.caption(f"Source: {requirement.get('source_excerpt') or 'Source excerpt unavailable'}")
                if requirement.get("ambiguity_flags"):
                    st.warning("Clarification needed: " + ", ".join(requirement["ambiguity_flags"]))
                st.write("**Acceptance criteria**")
                if requirement.get("acceptance_criteria"):
                    for criterion in requirement["acceptance_criteria"]:
                        st.markdown(f"- {criterion}")
                else:
                    st.caption("No measurable acceptance criteria extracted; confirm with the owner.")
        if conflicts:
            st.markdown("### Potential conflicts")
            for conflict in conflicts:
                st.warning(
                    f"{conflict['conflict_id']} · {', '.join(conflict['requirement_ids'])}: "
                    f"{conflict['description']}"
                )
    with tabs[1]:
        evidence = active.get("evidence", [])
        if not evidence:
            st.info("No local knowledge-base evidence matched the extracted controls.")
        for item in evidence:
            st.markdown(f"**{item['citation']}**")
            st.write(item["excerpt"])
        for requirement in requirements:
            controls = requirement.get("security_controls", [])
            notes = requirement.get("compliance_notes", [])
            if controls or notes:
                st.markdown(f"**{requirement['requirement_id']} — {requirement['category']}**")
                for control in controls + notes:
                    st.markdown(f"- {control}")
    with tabs[2]:
        recommendation = active.get("sdlc_recommendation", {})
        if active.get("preset_name"):
            st.caption(f"Starter case: {active['preset_name']}")
        if recommendation.get("preset_focus"):
            st.info(
                f"This case is tailored to **{recommendation['preset_focus']}**. "
                "The recommendation below is still computed from the requirements."
            )
        st.subheader(recommendation.get("recommended", "Not available"))
        st.write(recommendation.get("rationale", ""))
        st.caption(
            f"Heuristic screening score: {recommendation.get('confidence', 'N/A')} "
            "— not a statistical confidence."
        )
        ranking = recommendation.get("ranking", [])
        if ranking:
            st.dataframe(ranking, use_container_width=True, hide_index=True)
        st.markdown("**Suggested governance gates**")
        for gate in recommendation.get("gates", []):
            st.markdown(f"- {gate}")
    with tabs[3]:
        artifacts = active.get("artifacts", {})
        if artifacts:
            st.download_button(
                "Download all deliverables (.zip)",
                _archive(artifacts),
                file_name=f"{active['project_id']}-deliverables.zip",
                mime="application/zip",
                type="primary",
            )
            for filename, content in artifacts.items():
                with st.expander(filename):
                    st.download_button(
                        f"Download {filename}",
                        content,
                        file_name=filename,
                        mime="text/markdown",
                        key=f"download-{active['project_id']}-{filename}",
                    )
                    st.markdown(content)
        else:
            st.info("Load a project generated by this version to view its deliverables.")
    with tabs[4]:
        st.markdown("### Named human decision")
        st.caption(
            "Approval records are durable. A decision does not certify regulatory compliance "
            "or replace required institutional sign-off."
        )
        with st.form(f"approval-{active['project_id']}"):
            approver = st.text_input("Approver name")
            decision = st.selectbox(
                "Decision",
                ["approved", "changes_requested", "rejected"],
                format_func=lambda value: value.replace("_", " ").title(),
            )
            notes = st.text_area("Decision notes")
            submitted = st.form_submit_button("Record decision")
        if submitted:
            manager.record_approval(active["project_id"], approver, decision, notes)
            active["status"] = decision
            active.setdefault("approvals", []).insert(
                0,
                {
                    "approver": approver,
                    "decision": decision,
                    "notes": notes,
                    "created_at": "",
                },
            )
            st.session_state["active_project"] = active
            st.success(f"Decision recorded: {decision.replace('_', ' ')}.")
        approvals = active.get("approvals", [])
        if approvals:
            st.markdown("### Decision history")
            st.dataframe(approvals, use_container_width=True, hide_index=True)
        issues = active.get("validation_issues", [])
        if issues:
            st.markdown("### Open validation issues")
            for issue in issues:
                st.markdown(f"- {issue}")
else:
    st.markdown("## Start with stakeholder evidence")
    st.write(
        "Create an analysis from requirements, interview notes, or a project brief. "
        "FinSpec AI extracts candidate requirements, surfaces ambiguity, retrieves local "
        "evidence, recommends an SDLC approach, and prepares reviewable documents."
    )
    st.markdown(
        "- **Workflow:** elicitation context → extraction → clarification → classification → "
        "conflict and control analysis → SDLC selection → documentation → validation → approval\n"
        "- **Traceability:** requirement IDs connect to local evidence and acceptance criteria\n"
        "- **Persistence:** SQLite stores projects, requirement records, decisions, and audit events\n"
        "- **Knowledge base:** local Markdown retrieval works without embeddings or an external service"
    )
