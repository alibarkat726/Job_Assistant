from datetime import datetime, timezone
from typing import Optional, List
import uuid
from sqlalchemy import String, Boolean, Integer, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.shared.db.base import Base, TimestampMixin


class CV(Base, TimestampMixin):
    __tablename__ = "cvs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled CV")
    variant_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Base Intake CV")
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True, index=True)
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Raw file & text storage details
    raw_file_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Structured contact & profile information
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parse_confidence: Mapped[str] = mapped_column(String(50), nullable=False, default="high")

    # Relationships
    work_histories: Mapped[List["WorkHistory"]] = relationship(
        "WorkHistory", back_populates="cv", cascade="all, delete-orphan", lazy="selectin"
    )
    education_entries: Mapped[List["EducationEntry"]] = relationship(
        "EducationEntry", back_populates="cv", cascade="all, delete-orphan", lazy="selectin"
    )
    skills: Mapped[List["CVSkill"]] = relationship(
        "CVSkill", back_populates="cv", cascade="all, delete-orphan", lazy="selectin"
    )


class WorkHistory(Base, TimestampMixin):
    __tablename__ = "work_histories"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_date: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cv: Mapped["CV"] = relationship("CV", back_populates="work_histories")


class EducationEntry(Base, TimestampMixin):
    __tablename__ = "education_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    degree: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    field_of_study: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_date: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    cv: Mapped["CV"] = relationship("CV", back_populates="education_entries")


class CVSkill(Base, TimestampMixin):
    __tablename__ = "cv_skills"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    cv: Mapped["CV"] = relationship("CV", back_populates="skills")


class Skill(Base, TimestampMixin):
    """
    Canonical profile skill — the authoritative user skill list consumed by Modules 4, 6, 7.

    This is SEPARATE from cv_skills (Module 2), which are raw CV-extracted artifacts.
    Module 4 (Learning Triage) promotes cv_skills into this table via
    SkillsService.upsert_skill(..., source="cv_import").

    Normalization: name_slug = name.strip().lower() with a unique constraint on
    (user_id, name_slug) to prevent case-insensitive duplicates ("React" vs "react").
    """

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Display name as entered by user (e.g. "React.js", "TypeScript")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Normalized slug for dedup/matching: name.strip().lower() (e.g. "react.js", "typescript")
    name_slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Optional category (e.g. "language", "framework", "tool", "soft-skill")
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # 1–5 integer scale. Maps to 0.0–1.0 for Module 6 matching weights.
    proficiency: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # Origin tracking: "manual" | "cv_import" | "learning" (Module 4 will add cv_import/learning)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual", index=True)

    # Many-to-many back-reference from projects
    project_skills: Mapped[List["ProjectSkill"]] = relationship(
        "ProjectSkill", back_populates="skill", cascade="all, delete-orphan"
    )


class ProjectSkill(Base):
    """
    Join table for the many-to-many relationship between projects and skills.
    Includes user_id for RLS tenant isolation enforcement.
    """

    __tablename__ = "project_skills"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="project_skills")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="project_skills")


class Project(Base, TimestampMixin):
    """
    User's portfolio project. Supports multiple URLs (repo, live demo, case study)
    stored as JSONB: [{"label": "GitHub", "url": "https://..."}].
    Links to profile skills via many-to-many through ProjectSkill.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSONB list of {label: str, url: str} objects
    urls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    start_date: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_ongoing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Many-to-many to skills
    project_skills: Mapped[List["ProjectSkill"]] = relationship(
        "ProjectSkill", back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )


class LearningEntry(Base, TimestampMixin):
    """
    User's daily learning log entry.
    """
    __tablename__ = "learning_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # One-to-one relationship with LearningProposal
    proposal: Mapped[Optional["LearningProposal"]] = relationship(
        "LearningProposal", back_populates="entry", cascade="all, delete-orphan", uselist=False
    )


class LearningProposal(Base, TimestampMixin):
    """
    A proposal generated by the Triage Agent evaluating a LearningEntry.
    """
    __tablename__ = "learning_proposals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_entries.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_skill_worthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 'pending', 'approved', 'rejected', 'needs_manual_review'
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)

    entry: Mapped["LearningEntry"] = relationship("LearningEntry", back_populates="proposal")
    proposed_skills: Mapped[List["ProposedSkillItem"]] = relationship(
        "ProposedSkillItem", back_populates="proposal", cascade="all, delete-orphan"
    )


class ProposedSkillItem(Base, TimestampMixin):
    """
    A specific skill proposed within a LearningProposal.
    """
    __tablename__ = "proposed_skill_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_proposals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 'reinforce_existing' or 'create_new'
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    # Linked canonical skill if action is 'reinforce_existing'
    matched_skill_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), nullable=True
    )
    # 'high', 'medium', 'low' - Agent's confidence
    confidence: Mapped[str] = mapped_column(String(50), nullable=False)
    # 'pending', 'approved', 'rejected'
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)

    proposal: Mapped["LearningProposal"] = relationship("LearningProposal", back_populates="proposed_skills")


class JobApplication(Base, TimestampMixin):
    """
    User's job application record. The user manually pastes a job description;
    the system parses it, scores it against their skills, and produces a tailored CV.
    This is NOT a shared cache — it belongs exclusively to one user (tenant-scoped).
    """
    __tablename__ = "job_applications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    jd_raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    # 'draft' -> 'tailored' -> 'applied'
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", index=True)
    # 'pending_parse', 'parsed', 'needs_manual_review'
    parse_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending_parse")

    requirements: Mapped[List["JDRequirement"]] = relationship(
        "JDRequirement", back_populates="job_application", cascade="all, delete-orphan"
    )
    skill_matches: Mapped[List["ApplicationSkillMatch"]] = relationship(
        "ApplicationSkillMatch", back_populates="job_application", cascade="all, delete-orphan"
    )
    tailored_cv: Mapped[Optional["TailoredCV"]] = relationship(
        "TailoredCV", back_populates="job_application", cascade="all, delete-orphan", uselist=False
    )
    interview_prep_set: Mapped[Optional["InterviewPrepSet"]] = relationship(
        "InterviewPrepSet", back_populates="job_application", cascade="all, delete-orphan", uselist=False
    )
    cover_letter: Mapped[Optional["CoverLetter"]] = relationship(
        "CoverLetter", back_populates="job_application", cascade="all, delete-orphan", uselist=False
    )


class CoverLetter(Base, TimestampMixin):
    """
    A tailored cover letter draft/final version produced for a specific job application.
    """
    __tablename__ = "cover_letters"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    job_application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")
    length: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")
    # 'draft', 'finalized'
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    
    # Store unverified claims flagged by the grounding check as JSON string
    unverified_claims: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job_application: Mapped["JobApplication"] = relationship(
        "JobApplication", back_populates="cover_letter"
    )


class ApplicationSkillMatch(Base, TimestampMixin):
    """
    Transient-ish matching output persisted for analytics module querying.
    """
    __tablename__ = "application_skill_matches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    job_application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jd_skill_name: Mapped[str] = mapped_column(String(255), nullable=False)
    jd_skill_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    # 'matched', 'partial', 'missing'
    match_status: Mapped[str] = mapped_column(String(50), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    job_application: Mapped["JobApplication"] = relationship(
        "JobApplication", back_populates="skill_matches"
    )


class JDRequirement(Base, TimestampMixin):
    """
    A single extracted requirement from a job description.
    Normalized child table (not a JSON blob) — consistent with Module 2/4 pattern.
    """
    __tablename__ = "jd_requirements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    job_application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Normalized for matching against skills.name_slug
    skill_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    seniority: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    job_application: Mapped["JobApplication"] = relationship(
        "JobApplication", back_populates="requirements"
    )


class TailoredCV(Base, TimestampMixin):
    """
    A tailored CV draft produced for a specific job application.
    Hard constraint: only reorders/reweights existing CV data — never invents facts.
    Underlying fields (company names, dates, project URLs) from canonical CV are unchanged.
    """
    __tablename__ = "tailored_cvs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    job_application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_cv_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("cvs.id", ondelete="SET NULL"), nullable=True
    )
    # JSON string of tailored CV content (reordered/reweighted bullets)
    tailored_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Human-readable summary of what was changed
    diff_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 'draft', 'finalized'
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    # Array of strings storing project IDs
    selected_project_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    job_application: Mapped["JobApplication"] = relationship(
        "JobApplication", back_populates="tailored_cv"
    )
    source_cv: Mapped["CV"] = relationship(
        "CV", foreign_keys=[source_cv_id]
    )


class InterviewPrepSet(Base, TimestampMixin):
    """
    A generated set of interview questions for a specific job application.
    """
    __tablename__ = "interview_prep_sets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    job_application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 'pending_generation', 'generated', 'needs_manual_review'
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending_generation")
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    job_application: Mapped["JobApplication"] = relationship(
        "JobApplication", back_populates="interview_prep_set"
    )
    questions: Mapped[List["InterviewQuestion"]] = relationship(
        "InterviewQuestion", back_populates="prep_set", cascade="all, delete-orphan", order_by="InterviewQuestion.ordering"
    )


class InterviewQuestion(Base, TimestampMixin):
    """
    A specific interview question within a prep set.
    """
    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    prep_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_prep_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 'technical', 'project', 'behavioral'
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_answer_outline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_practiced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    prep_set: Mapped["InterviewPrepSet"] = relationship(
        "InterviewPrepSet", back_populates="questions"
    )
