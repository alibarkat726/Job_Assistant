"""005 Job Applications & CV Tailoring Schema

Revision ID: 005_job_applications_tailoring_schema
Revises: 004_learning_triage_schema
Create Date: 2026-09-04 18:00:00.000000

Design notes:
  - Replaces the stubs `jobs_cache` and `applications` with proper domain tables.
  - `job_applications` is per-user (tenant-scoped), not a shared cache.
  - `jd_requirements` is a normalized child table of job_applications (not JSON blob).
  - `tailored_cvs` links to job_applications and stores tailored content + diff metadata.
  - All tables have RLS enabled and forced.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005_tailoring_schema"
down_revision: Union[str, None] = "004_learning_triage_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Create `job_applications` table
    # ------------------------------------------------------------------ #
    op.create_table(
        "job_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("job_title", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("jd_raw_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=True),  # Optional, user-pasted, never fetched
        # 'draft' -> 'tailored' -> 'applied'
        sa.Column("status", sa.String(50), server_default="draft", nullable=False),
        # 'pending_parse', 'parsed', 'needs_manual_review'
        sa.Column("parse_status", sa.String(50), server_default="pending_parse", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_job_applications_status", "job_applications", ["status"])

    # ------------------------------------------------------------------ #
    # 2. Create `jd_requirements` table (normalized, not JSON blob)
    # ------------------------------------------------------------------ #
    op.create_table(
        "jd_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("skill_name", sa.String(255), nullable=False),
        sa.Column("skill_slug", sa.String(255), nullable=False),  # Normalized for matching
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="true"),  # True = required, False = nice-to-have
        sa.Column("seniority", sa.String(100), nullable=True),  # e.g. "senior", "mid-level"
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------ #
    # 3. Create `tailored_cvs` table
    # ------------------------------------------------------------------ #
    op.create_table(
        "tailored_cvs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_cv_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cvs.id", ondelete="SET NULL"), nullable=True),
        # Tailored CV content as structured JSON (reordered/reweighted, no invented facts)
        sa.Column("tailored_content", sa.Text(), nullable=True),  # JSON string of tailored CV
        # Diff summary: which sections were reordered/reweighted vs canonical CV
        sa.Column("diff_summary", sa.Text(), nullable=True),
        # 'draft', 'finalized'
        sa.Column("status", sa.String(50), server_default="draft", nullable=False),
        # Which project UUIDs were selected as top-relevant for this JD
        sa.Column("selected_project_ids", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------ #
    # 4. RLS Enforcement for tenant tables
    # ------------------------------------------------------------------ #
    for table in ["job_applications", "jd_requirements", "tailored_cvs"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            FOR ALL
            USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
            """
        )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in ["tailored_cvs", "jd_requirements", "job_applications"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        op.drop_table(table)
