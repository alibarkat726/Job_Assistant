"""003 Skills & Projects — Full Schema with RLS

Revision ID: 003_skills_projects_schema
Revises: 002_cv_intake_schema
Create Date: 2026-09-04 12:00:00.000000

Design notes:
  - `skills` and `projects` tables already exist (created by migration 001 with stub columns).
    This migration adds the remaining columns via ALTER TABLE and creates indexes/constraints.
  - `project_skills` is a new join table with RLS enabled and forced (user_id for tenant isolation).
  - Skill normalization: `name_slug` = name.strip().lower() — unique per (user_id, name_slug).
  - Profile skills (this module) are separate from cv_skills (Module 2). See README for details.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_skills_projects_schema"
down_revision: Union[str, None] = "002_cv_intake_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Expand `skills` table (stub from migration 001 had id, user_id, name, timestamps)
    # ------------------------------------------------------------------ #
    op.add_column("skills", sa.Column("name_slug", sa.String(length=255), nullable=True))
    op.add_column("skills", sa.Column("category", sa.String(length=100), nullable=True))
    op.add_column("skills", sa.Column("proficiency", sa.SmallInteger(), nullable=False, server_default="3"))
    op.add_column("skills", sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"))

    # Back-fill name_slug for any existing rows (should be none in practice)
    op.execute("UPDATE skills SET name_slug = LOWER(TRIM(name)) WHERE name_slug IS NULL")

    # Now make name_slug NOT NULL
    op.alter_column("skills", "name_slug", nullable=False)

    # Unique constraint: (user_id, name_slug) — prevents case-insensitive duplicates
    op.create_unique_constraint("uq_skills_user_id_name_slug", "skills", ["user_id", "name_slug"])
    op.create_index("ix_skills_name_slug", "skills", ["name_slug"])
    op.create_index("ix_skills_source", "skills", ["source"])

    # ------------------------------------------------------------------ #
    # 2. Expand `projects` table (stub from migration 001 had id, user_id, title, timestamps)
    # ------------------------------------------------------------------ #
    op.add_column("projects", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "urls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("projects", sa.Column("start_date", sa.String(length=100), nullable=True))
    op.add_column("projects", sa.Column("end_date", sa.String(length=100), nullable=True))
    op.add_column(
        "projects",
        sa.Column("is_ongoing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # ------------------------------------------------------------------ #
    # 3. Create `project_skills` join table with full RLS
    # ------------------------------------------------------------------ #
    op.create_table(
        "project_skills",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("project_id", "skill_id"),
    )
    op.create_index("ix_project_skills_project_id", "project_skills", ["project_id"])
    op.create_index("ix_project_skills_skill_id", "project_skills", ["skill_id"])
    op.create_index("ix_project_skills_user_id", "project_skills", ["user_id"])

    # Enable & Force Row Level Security on project_skills
    op.execute("ALTER TABLE project_skills ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE project_skills FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation_policy ON project_skills
        FOR ALL
        USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
        """
    )

    # Grant privileges to app_user role if present
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
    # Drop project_skills join table
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON project_skills;")
    op.execute("ALTER TABLE project_skills DISABLE ROW LEVEL SECURITY;")
    op.drop_table("project_skills")

    # Revert projects columns
    op.drop_column("projects", "is_ongoing")
    op.drop_column("projects", "end_date")
    op.drop_column("projects", "start_date")
    op.drop_column("projects", "urls")
    op.drop_column("projects", "description")

    # Revert skills columns
    op.drop_index("ix_skills_source", table_name="skills")
    op.drop_index("ix_skills_name_slug", table_name="skills")
    op.drop_constraint("uq_skills_user_id_name_slug", "skills", type_="unique")
    op.drop_column("skills", "source")
    op.drop_column("skills", "proficiency")
    op.drop_column("skills", "category")
    op.drop_column("skills", "name_slug")
