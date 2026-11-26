"""General financial-system and SDLC-focused starter cases."""

PRESETS = {
    "general_onboarding": {
        "label": "General · Digital onboarding / KYC",
        "project_name": "Digital Customer Onboarding",
        "scenario": "Digital onboarding / KYC",
        "stakeholder_role": "Product owner",
        "sdlc_focus": None,
        "description": "Identity verification, application review, and customer-data handling.",
        "source_text": (
            "The onboarding service must allow a customer to submit an identity document "
            "and complete a video verification session.\n"
            "The service should verify the customer's identity quickly and securely.\n"
            "Operations must be able to review flagged applications and record a decision reason.\n"
            "Customer identity documents should be retained for an appropriate period.\n"
            "The platform must record who accessed an application and when.\n"
            "Compliance must confirm applicable jurisdiction-specific KYC obligations before launch."
        ),
    },
    "general_payments": {
        "label": "General · Payments and settlement",
        "project_name": "Payment Processing Controls",
        "scenario": "Payments",
        "stakeholder_role": "Operations",
        "sdlc_focus": None,
        "description": "Payment validation, settlement status, exception handling, and audit records.",
        "source_text": (
            "The payment service must validate beneficiary and account details before submission.\n"
            "The system must prevent the same payment instruction from being settled more than once.\n"
            "Operations must be able to review failed payments and record a resolution reason.\n"
            "The system must retain an auditable record of payment state changes.\n"
            "The business owner must define the settlement cut-off and recovery objectives."
        ),
    },
    "general_lending": {
        "label": "General · Digital lending",
        "project_name": "Digital Lending Application",
        "scenario": "Digital lending",
        "stakeholder_role": "Product owner",
        "sdlc_focus": None,
        "description": "Loan applications, decision explanations, disclosures, and review workflows.",
        "source_text": (
            "Applicants must be able to submit a digital loan application and supporting documents.\n"
            "The system must show applicants the status of their application.\n"
            "A reviewer must be able to record the rationale for a manual application decision.\n"
            "The institution must define required applicant disclosures before submission.\n"
            "Access to applicant financial information must be restricted to authorized roles."
        ),
    },
    "general_fraud": {
        "label": "General · Fraud monitoring",
        "project_name": "Transaction Fraud Monitoring",
        "scenario": "Fraud monitoring",
        "stakeholder_role": "Security",
        "sdlc_focus": None,
        "description": "Alert handling, analyst review, escalation, and evidence retention.",
        "source_text": (
            "The monitoring service must create an alert when a transaction meets an approved rule.\n"
            "An analyst must be able to assign, investigate, and disposition an alert.\n"
            "The system must record the analyst, timestamps, evidence, and disposition for each alert.\n"
            "High-priority alerts must be escalated to the on-call operations team.\n"
            "The risk owner must approve alert thresholds before production use."
        ),
    },
    "sdlc_agile": {
        "label": "SDLC · Agile (iterative feature delivery)",
        "project_name": "Agile Payments Experience",
        "scenario": "Payments",
        "stakeholder_role": "Product owner",
        "sdlc_focus": "Agile",
        "description": "Small increments, frequent user feedback, and evolving payment features.",
        "source_text": (
            "The payments team will deliver customer-visible capabilities in small increments.\n"
            "Product owners must review each increment and record feedback before the next iteration.\n"
            "The payment status view must show pending, completed, and failed states.\n"
            "Each delivered feature must have agreed acceptance criteria before sprint completion.\n"
            "The team should adjust the backlog when customer feedback changes priorities."
        ),
    },
    "sdlc_v_model": {
        "label": "SDLC · V-Model (regulated payment controls)",
        "project_name": "Regulated Payment Validation",
        "scenario": "Payments",
        "stakeholder_role": "Compliance",
        "sdlc_focus": "V-Model",
        "description": "Baselined controls with explicit verification and validation evidence.",
        "source_text": (
            "The payment service must reject instructions that fail an approved validation rule.\n"
            "Every payment state transition must be recorded with actor, timestamp, and outcome.\n"
            "Each approved requirement must map to a documented test case and retained test evidence.\n"
            "Compliance must approve control mappings before the requirements baseline is released.\n"
            "Release approval must confirm that all required verification evidence is complete."
        ),
    },
    "sdlc_spiral": {
        "label": "SDLC · Spiral (high-risk fraud analytics)",
        "project_name": "Fraud Analytics Risk Discovery",
        "scenario": "Fraud monitoring",
        "stakeholder_role": "Security",
        "sdlc_focus": "Spiral",
        "description": "Risk-driven prototypes for uncertain fraud signals, privacy, and model behavior.",
        "source_text": (
            "The team is uncertain which transaction signals reliably identify emerging fraud patterns.\n"
            "The analytics service should flag suspicious activity using appropriate indicators.\n"
            "Before using a new signal, the team must assess privacy impact and false-positive risk.\n"
            "Analysts should review a prototype against historical cases before any live pilot.\n"
            "The risk owner must define acceptable error thresholds and a rollback plan."
        ),
    },
    "sdlc_incremental": {
        "label": "SDLC · Incremental (core banking migration)",
        "project_name": "Core Banking Migration",
        "scenario": "Core banking",
        "stakeholder_role": "Engineering",
        "sdlc_focus": "Incremental",
        "description": "Phased migration with reconciled data and independently deployable capability slices.",
        "source_text": (
            "The migration must move customer account data in approved, verifiable batches.\n"
            "Each migration batch must reconcile source and destination account balances before sign-off.\n"
            "The first release must support read-only access to migrated account statements.\n"
            "Later releases may enable additional servicing capabilities after operational acceptance.\n"
            "Operations must be able to pause a migration batch and resume after reconciliation."
        ),
    },
}


def get_preset(preset_id: str) -> dict[str, str | None] | None:
    """Return a preset by its stable identifier."""
    return PRESETS.get(preset_id)
