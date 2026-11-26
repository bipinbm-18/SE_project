"""Validated models for requirements and project decisions."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    requirement_id: str
    statement: str = Field(min_length=8)
    source_excerpt: str = ""
    category: str = "Unclassified"
    priority: str = "Medium"
    ambiguity_flags: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    compliance_notes: list[str] = Field(default_factory=list)
    security_controls: list[str] = Field(default_factory=list)
    risk_level: str = "Medium"
    risk_notes: list[str] = Field(default_factory=list)


class ExtractedRequirements(BaseModel):
    requirements: list[Requirement]
