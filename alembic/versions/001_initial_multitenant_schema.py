"""001 Initial Multi-Tenant Schema with Postgres RLS Policies

Revision ID: 001_initial_multitenant_schema
Revises: 
Create Date: 2026-09-02 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_multitenant_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create Users Table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verification_token_hash", sa.String(length=255), nullable=True),
        sa.Column("verification_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_reset_token_hash", sa.String(length=255), nullable=True),
        sa.Column("password_reset_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_verification_token_hash", "users", ["verification_token_hash"])
    op.create_index("ix_users_password_reset_token_hash", "users", ["password_reset_token_hash"])

    # 2. Create Refresh Tokens Table
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    # 3. Core Multi-Tenant Tables (cvs, skills, projects, learning_entries, jobs_cache, applications)
    tenant_tables = [
        ("cvs", sa.Column("title", sa.String(length=255), nullable=False, server_default="Untitled CV")),
        ("skills", sa.Column("name", sa.String(length=255), nullable=False)),
        ("projects", sa.Column("title", sa.String(length=255), nullable=False)),
        ("learning_entries", sa.Column("topic", sa.String(length=255), nullable=False)),
        ("jobs_cache", sa.Column("job_title", sa.String(length=255), nullable=False)),
        ("applications", sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True), sa.Column("status", sa.String(length=50), nullable=False, server_default="applied")),
    ]

    for item in tenant_tables:
        table_name = item[0]
        columns = item[1:]
        op.create_table(
            table_name,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            *columns,
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(f"ix_{table_name}_id", table_name, ["id"])
        op.create_index(f"ix_{table_name}_user_id", table_name, ["user_id"])

        # 4. Enable Row Level Security (RLS) and Create RLS Policy for every tenant table
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table_name}
            FOR ALL
            USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
            """
        )


def downgrade() -> None:
    tenant_tables = ["applications", "jobs_cache", "learning_entries", "projects", "skills", "cvs"]
    for table_name in tenant_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;")
        op.drop_table(table_name)

    op.drop_table("refresh_tokens")
    op.drop_table("users")
