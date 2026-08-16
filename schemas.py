"""
schemas.py
==========
Pydantic models used for:
  1. API request/response validation (FastAPI).
  2. Structured output contracts that AI providers are asked to fill in
     (research plan, source metadata, final report). Using real schemas
     here - instead of ad-hoc free-form text parsing - is what makes the
     agent's output reliable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

ResearchMode = Literal["quick", "standard", "deep", "custom"]


# ----------------------------------------------------------------------------
# Structured AI output contracts
# ----------------------------------------------------------------------------
class PlannedTask(BaseModel):
    title: str
    description: str
    priority: Literal["low", "medium", "high"] = "medium"
    expected_output: str = ""


class ResearchPlan(BaseModel):
    research_question: str
    tasks: list[PlannedTask] = Field(default_factory=list)
    priority: Literal["low", "medium", "high"] = "medium"
    expected_output: str = ""


class SourceCandidate(BaseModel):
    title: str
    url: str
    source: str = ""  # domain / publisher name
    relevance: float = 0.0
    summary: str = ""
    published_date: Optional[str] = None


class ConflictItem(BaseModel):
    topic: str
    description: str
    source_a_title: str
    source_a_value: str
    source_b_title: str
    source_b_value: str


class FinalReport(BaseModel):
    title: str
    executive_summary: str
    research_question: str = ""
    methodology: str = ""
    key_findings: list[str] = Field(default_factory=list)
    detailed_analysis: str = ""
    comparison: str = ""
    conflicting_information: list[ConflictItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    conclusion: str = ""
    sources: list[SourceCandidate] = Field(default_factory=list)


# ----------------------------------------------------------------------------
# API request/response models
# ----------------------------------------------------------------------------
class ResearchRequest(BaseModel):
    research_question: str = Field(min_length=5, max_length=2000)
    mode: ResearchMode = "standard"
    max_sources: Optional[int] = Field(default=None, ge=1, le=30)
    max_tasks: Optional[int] = Field(default=None, ge=1, le=15)

    @field_validator("research_question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("research_question cannot be empty")
        return v


class ProgressEvent(BaseModel):
    message: str
    stage: str
    timestamp: str


class SourceOut(BaseModel):
    id: str
    title: str
    url: str
    domain: str
    source_type: str
    published_date: Optional[str] = None
    summary: str
    relevance_score: float
    authority_score: float
    recency_score: float
    evidence_score: float
    bias_risk: str
    overall_quality: float
    trust_label: str

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: str
    order_index: int
    title: str
    description: str
    priority: str
    expected_output: str
    status: str
    result_summary: Optional[str] = None

    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: str
    title: str
    executive_summary: str
    methodology: str
    key_findings: list[str]
    detailed_analysis: str
    comparison: str
    conflicts: list[dict]
    limitations: list[str]
    conclusion: str
    sources_json: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class ResearchSessionOut(BaseModel):
    id: str
    research_question: str
    mode: str
    status: str
    current_stage: str
    progress_percent: int
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    progress_log: list[dict]

    model_config = {"from_attributes": True}


class ResearchSessionDetail(ResearchSessionOut):
    tasks: list[TaskOut] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    report: Optional[ReportOut] = None


class ProviderStatus(BaseModel):
    name: str
    configured: bool
    model: str
    role: list[str] = Field(default_factory=list)


class ExportFormat(BaseModel):
    format: Literal["markdown", "html", "pdf", "txt", "json"]


class ErrorResponse(BaseModel):
    detail: str
