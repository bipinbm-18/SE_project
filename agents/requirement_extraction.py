"""Requirement extraction using Gemini or a deterministic offline baseline."""
from __future__ import annotations

import json
import re
from typing import Any

from config import GEMINI_API_KEY, LLM_MODEL, read_env_value
from schemas.models import ExtractedRequirements, Requirement

FALLBACK_GEMINI_MODELS = (
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
)

VAGUE_TERMS = (
    "quickly",
    "user-friendly",
    "as soon as possible",
    "appropriate",
    "sufficient",
    "easy",
    "fast",
    "secure",
    "reasonable",
    "timely",
)


def call_gemini_json(prompt: str) -> Any:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "LLM_PROVIDER is gemini, but GEMINI_API_KEY (or GOOGLE_API_KEY) is not set."
        )
    from langchain_google_genai import ChatGoogleGenerativeAI

    configured_model = read_env_value("LLM_MODEL", LLM_MODEL) or LLM_MODEL
    candidates = [configured_model] + [
        model_name for model_name in FALLBACK_GEMINI_MODELS if model_name != configured_model
    ]
    last_error: Exception | None = None
    content: Any = None
    for candidate in candidates:
        try:
            model = ChatGoogleGenerativeAI(
                model=candidate,
                google_api_key=GEMINI_API_KEY,
                temperature=0,
                max_retries=1,
                timeout=20,
            )
            response = model.invoke(prompt)
            content = response.content
            break
        except Exception as exc:
            last_error = exc
            continue
    else:
        assert last_error is not None
        raise last_error

    if isinstance(content, list):
        content = "\n".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    text = str(content).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Gemini returned invalid JSON.") from exc


def _gemini_json(prompt: str) -> Any:
    return call_gemini_json(prompt)


def _mock_extract(source_text: str) -> list[Requirement]:
    source_text = "\n".join(
        line for line in source_text.splitlines() if not line.lstrip().startswith("#")
    )
    candidates = [
        sentence.strip(" \t\r\n-•")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", source_text)
        if len(sentence.strip(" \t\r\n-•")) >= 18
    ]
    if not candidates and source_text.strip():
        candidates = [source_text.strip()[:500]]

    requirements: list[Requirement] = []
    for index, sentence in enumerate(candidates, start=1):
        lowered = sentence.lower()
        flags = [term for term in VAGUE_TERMS if term in lowered]
        if re.search(r"\b(as needed|etc\.?|and so on|appropriate)\b", lowered):
            flags.append("Unbounded or underspecified scope")
        requirements.append(
            Requirement(
                requirement_id=f"FR-{index:03d}",
                statement=sentence[:1000],
                source_excerpt=sentence[:500],
                ambiguity_flags=sorted(set(flags)),
                acceptance_criteria=[],
            )
        )
    return requirements


def extract_requirements(source_text: str, provider: str = "mock") -> list[dict[str, Any]]:
    if not source_text.strip():
        raise ValueError("Source material is empty.")
    if provider == "mock":
        requirements = _mock_extract(source_text)
    elif provider == "gemini":
        schema = {
            "requirements": [
                {
                    "requirement_id": "FR-001",
                    "statement": "A concise, testable requirement",
                    "source_excerpt": "Verbatim supporting text",
                    "ambiguity_flags": ["Specific ambiguity or an empty list"],
                    "acceptance_criteria": ["Measurable criterion or an empty list"],
                }
            ]
        }
        result = _gemini_json(
            "Extract independently testable requirements from the source material. "
            "Do not invent legal obligations. Preserve traceability using short verbatim "
            "source excerpts. Flag vague or conflicting language instead of guessing. "
            "Return JSON only with this shape:\n"
            f"{json.dumps(schema)}\n\n"
            f"Stakeholder source material:\n{source_text[:30000]}"
        )
        parsed = ExtractedRequirements.model_validate(result)
        requirements = parsed.requirements
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}. Use 'mock' or 'gemini'.")

    for index, requirement in enumerate(requirements, start=1):
        requirement.requirement_id = f"FR-{index:03d}"
    return [item.model_dump(mode="json") for item in requirements]
