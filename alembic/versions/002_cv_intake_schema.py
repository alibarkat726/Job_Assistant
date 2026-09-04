"""002 CV Intake Schema with Work History, Education, CV Skills and RLS

Revision ID: 002_cv_intake_schema
Revises: 001_initial_multitenant_schema
Create Date: 2026-09-03 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_cv_intake_schema"
down_revision: Union[str, None] = "001_initial_multitenant_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Expand `cvs` table columns
    op.add_column("cvs", sa.Column("variant_name", sa.String(length=255), nullable=False, server_default="Base Intake CV"))
    op.add_column("cvs", sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("cvs", sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("cvs", sa.Column("raw_file_key", sa.String(length=255), nullable=True))
    op.add_column("cvs", sa.Column("raw_file_name", sa.String(length=255), nullable=True))
    op.add_column("cvs", sa.Column("mime_type", sa.String(length=100), nullable=True))
    op.add_column("cvs", sa.Column("file_size", sa.Integer(), nullable=True))
    op.add_column("cvs", sa.Column("raw_text", sa.Text(), nullable=True))
    op.add_column("cvs", sa.Column("full_name", sa.String(length=255), nullable=True))
    op.add_column("cvs", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("cvs", sa.Column("phone", sa.String(length=100), nullable=True))
    op.add_column("cvs", sa.Column("location", sa.String(length=255), nullable=True))
    op.add_column("cvs", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("cvs", sa.Column("parse_confidence", sa.String(length=50), nullable=False, server_default="high"))

    op.create_index("ix_cvs_job_id", "cvs", ["job_id"])

    # 2. Create `work_histories` table
    op.create_table(
        "work_histories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.String(length=100), nullable=True),
        sa.Column("end_date", sa.String(length=100), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_work_histories_id", "work_histories", ["id"])
    op.create_index("ix_work_histories_user_id", "work_histories", ["user_id"])
    op.create_index("ix_work_histories_cv_id", "work_histories", ["cv_id"])

    # 3. Create `education_entries` table
    op.create_table(
        "education_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("institution", sa.String(length=255), nullable=False),
        sa.Column("degree", sa.String(length=255), nullable=True),
        sa.Column("field_of_study", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.String(length=100), nullable=True),
        sa.Column("end_date", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_education_entries_id", "education_entries", ["id"])
    op.create_index("ix_education_entries_user_id", "education_entries", ["user_id"])
    op.create_index("ix_education_entries_cv_id", "education_entries", ["cv_id"])

    # 4. Create `cv_skills` table
    op.create_table(
        "cv_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cv_skills_id", "cv_skills", ["id"])
    op.create_index("ix_cv_skills_user_id", "cv_skills", ["user_id"])
    op.create_index("ix_cv_skills_cv_id", "cv_skills", ["cv_id"])

    # 5. Enable & Force Postgres Row Level Security (RLS) on new child tables
    new_tables = ["work_histories", "education_entries", "cv_skills"]
    for table_name in new_tables:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table_name}
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
    new_tables = ["cv_skills", "education_entries", "work_histories"]
    for table_name in new_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;")
        op.drop_table(table_name)

    op.drop_index("ix_cvs_job_id", table_name="cvs")
    op.drop_column("cvs", "parse_confidence")
    op.drop_column("cvs", "summary")
    op.drop_column("cvs", "location")
    op.drop_column("cvs", "phone")
    op.drop_column("cvs", "email")
    op.drop_column("cvs", "full_name")
    op.drop_column("cvs", "raw_text")
    op.drop_column("cvs", "file_size")
    op.drop_column("cvs", "mime_type")
    op.drop_column("cvs", "raw_file_name")
    op.drop_column("cvs", "raw_file_key")
    op.drop_column("cvs", "is_canonical")
    op.drop_column("cvs", "job_id")
    op.drop_column("cvs", "variant_name")
