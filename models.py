"""
models.py
=========
SQLAlchemy ORM models for InsightForge AI.

Tables
------
ResearchSession   One research question/run, tracks overall status & timing.
ResearchTask      A planner-generated sub-task belonging to a session.
Source            A collected web source, with quality scoring metadata.
Report            The final structured research report for a session.
ProviderUsage     Per-call log of which AI provider handled which stage.
AppSetting        Simple key/value store for user-configurable settings
                   (provider routing preferences etc.) - never API keys.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    research_question: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="standard")  # quick|standard|deep|custom
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending -> planning -> searching -> analyzing -> crosschecking -> synthesizing -> completed | failed
    current_stage: Mapped[str] = mapped_column(String(30), default="pending")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    max_sources: Mapped[int] = mapped_column(Integer, default=10)
    max_tasks: Mapped[int] = mapped_column(Integer, default=8)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    progress_log: Mapped[list] = mapped_column(JSON, default=list)  # safe, high-level progress events

    tasks: Mapped[list["ResearchTask"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ResearchTask.order_index"
    )
    sources: Mapped[list["Source"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    report: Mapped["Report | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    provider_usages: Mapped[list["ProviderUsage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def add_progress(self, message: str, stage: str | None = None) -> None:
        entry = {"message": message, "stage": stage or self.current_stage, "timestamp": _now().isoformat()}
        # `progress_log`'s column default (`list`) is only applied by SQLAlchemy at
        # INSERT time, not when the Python object is constructed - so on a
        # brand-new, not-yet-flushed ResearchSession this attribute is still None.
        # Guard against that instead of assuming it's already a list.
        self.progress_log = [*(self.progress_log or []), entry]


class ResearchTask(Base):
    __tablename__ = "research_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("research_sessions.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    expected_output: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|in_progress|completed|failed
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped["ResearchSession"] = relationship(back_populates="tasks")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("research_sessions.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(2000))
    domain: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(50), default="web")
    published_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    raw_snippet: Mapped[str] = mapped_column(Text, default="")

    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    authority_score: Mapped[float] = mapped_column(Float, default=0.0)
    recency_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    bias_risk: Mapped[str] = mapped_column(String(20), default="unknown")  # low|medium|high|unknown
    overall_quality: Mapped[float] = mapped_column(Float, default=0.0)
    trust_label: Mapped[str] = mapped_column(String(20), default="uncertain")  # verified|uncertain|conflicting

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped["ResearchSession"] = relationship(back_populates="sources")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("research_sessions.id"), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500))
    executive_summary: Mapped[str] = mapped_column(Text, default="")
    methodology: Mapped[str] = mapped_column(Text, default="")
    key_findings: Mapped[list] = mapped_column(JSON, default=list)
    detailed_analysis: Mapped[str] = mapped_column(Text, default="")
    comparison: Mapped[str] = mapped_column(Text, default="")
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    conclusion: Mapped[str] = mapped_column(Text, default="")
    sources_json: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped["ResearchSession"] = relationship(back_populates="report")


class ProviderUsage(Base):
    __tablename__ = "provider_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("research_sessions.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(30))  # planning|analysis|crosscheck|synthesis
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    success: Mapped[bool] = mapped_column(default=True)
    was_fallback: Mapped[bool] = mapped_column(default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped["ResearchSession"] = relationship(back_populates="provider_usages")


class AppSetting(Base):
    """Simple key/value store for non-secret, user-configurable settings."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
