"""Deterministic lexical retrieval over local Markdown knowledge documents."""
from __future__ import annotations

import re
from pathlib import Path

from config import KB_PATH

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,}", re.IGNORECASE)


def retrieve_evidence(query: str, limit: int = 3, kb_path: Path = KB_PATH) -> list[dict[str, str]]:
    query_tokens = {token.lower() for token in TOKEN_RE.findall(query)}
    if not query_tokens or not kb_path.exists():
        return []

    matches: list[tuple[int, str, str]] = []
    for path in sorted(kb_path.glob("*.md")):
        paragraphs = re.split(r"\n\s*\n", path.read_text(encoding="utf-8"))
        for index, paragraph in enumerate(paragraphs, start=1):
            cleaned = paragraph.strip()
            tokens = {token.lower() for token in TOKEN_RE.findall(cleaned)}
            score = len(query_tokens & tokens)
            if score and cleaned:
                citation = f"KB-{path.stem.upper()}-{index:02d}"
                matches.append((score, citation, cleaned[:900]))
    matches.sort(key=lambda result: (-result[0], result[1]))
    return [
        {"citation": citation, "excerpt": excerpt, "score": str(score)}
        for score, citation, excerpt in matches[:limit]
    ]
