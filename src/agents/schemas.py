"""Pydantic response schemas shared by planner and answer chains."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchPlan(BaseModel):
    """Bounded list of allowed evidence-gathering tasks."""
    tasks: list[str] = Field(default_factory=list, description="Allowed task names: documents, sql, web, calculator, mcp")
    rationale: str = Field(default="", description="Short explanation of evidence needed")


class ResearchAnswer(BaseModel):
    """Structured answer with explicit uncertainty and evidence references."""
    answer: str
    citations: list[int] = Field(default_factory=list, description="One-based evidence item numbers used")
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
