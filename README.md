# FinSpec AI

FinSpec AI is an evidence-oriented requirements and SDLC workbench for financial systems. It adapts the architecture of the linked SDLC recommendation project to financial-system engineering: stakeholder input becomes traceable candidate requirements, ambiguity and potential conflicts are surfaced, local control evidence is retrieved, and a project-specific lifecycle recommendation and review artefacts are generated.

## What is included

- Streamlit workbench for pasted material and `.txt`, `.md`, and `.docx` uploads.
- A LangGraph workflow with coordinator, stakeholder context, extraction, clarification, classification, conflict detection, compliance, security/privacy, risk, governance merge, SDLC selection, documentation, validation, and human-approval stages.
- Gemini requirement extraction when configured, with a deterministic offline mode for local development.
- SQLite persistence for projects, requirements, conflicts, evidence/acceptance-criteria traceability, approvals, and audit events. LangGraph checkpoints are stored in the same SQLite database.
- Local Markdown knowledge retrieval with stable citation identifiers. Seed text is illustrative design guidance, not regulatory source material.
- Markdown deliverables: SRS, user stories, RTM, compliance matrix, risk register, SDLC plan, and open issues. Downloads are available individually or as a ZIP; generated Markdown is persisted under `artifacts/<project-id>/`.
- A named approval/rejection/changes-requested decision gate.

## Run locally

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

By default, the app uses offline mock extraction and makes no model calls. To enable Gemini, set the following in `.env`:

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
LLM_MODEL=gemini-2.5-flash
```

Never commit `.env` or paste an API key into source code. The app warns that source material is sent to Google Gemini when Gemini mode is selected; do not send confidential or personal data unless approved by your organization. Use `LLM_PROVIDER=mock` for offline analysis.

Optional paths can be set with `DATABASE_PATH`, `KB_PATH`, and `ARTIFACT_PATH`. For example:

```dotenv
DATABASE_PATH=data/finspec.db
KB_PATH=kb_docs
ARTIFACT_PATH=artifacts
```

## Use

1. Run the app and choose a starter case from the dashboard, or enter a project name, scenario, stakeholder role, and source material manually. Presets cover digital onboarding, payments, lending, fraud monitoring, and Agile, V-Model, Spiral, and Incremental SDLC-focused cases.
2. Select **Analyze requirements**. Review candidate requirements, source excerpts, ambiguity, possible conflicts, and retrieved evidence.
3. Review the heuristic SDLC ranking and generated artefacts. Add institutional knowledge documents to `kb_docs/` to retrieve local evidence.
4. Record a named human decision in the approval tab. Re-check saved work from the sidebar.

## Safety and limitations

FinSpec AI is a prototype and does not provide legal advice, regulatory interpretation, compliance certification, automated credit decisions, or production release authorization. The included knowledge text is illustrative only. Confirm jurisdiction-specific requirements with current primary sources and the institution's legal, compliance, security, privacy, and risk owners.

Uploaded or pasted source text is held in memory during the workflow and is not included in LangGraph checkpoints or the project database. The source filename, extracted requirement statements/source excerpts, evidence references, and generated outputs are persisted locally. When Gemini is enabled, source text is sent to Gemini for extraction. Avoid using real customer information in this prototype. Production use requires privacy review, PII handling, access controls, retention policy, model governance, and independent validation.

The offline extractor and conflict detector use simple heuristics. The SDLC ranking is a transparent screening rule, not a validated quantitative model. Human review is required for all generated outputs.

## Tests

```bash
pytest -q
```
