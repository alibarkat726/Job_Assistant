"""004 Learning Triage Schema

Revision ID: 004_learning_triage_schema
Revises: 003_skills_projects_schema
Create Date: 2026-09-04 13:00:00.000000

Design notes:
  - Expands existing `learning_entries` table.
  - Adds `learning_proposals` and `proposed_skill_items` tables.
  - All tables have Row Level Security (RLS) enabled and forced.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004_learning_triage_schema"
down_revision: Union[str, None] = "003_skills_projects_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Expand `learning_entries` table (stub from migration 001)
    # ------------------------------------------------------------------ #
    # Stub had: id, user_id, topic, created_at, updated_at
    # We rename 'topic' to 'title' (optional), add 'content' and 'timestamp'.
    op.alter_column("learning_entries", "topic", new_column_name="title", nullable=True)
    op.add_column("learning_entries", sa.Column("content", sa.Text(), nullable=True))
    # Populate existing content if any rows existed, then make NOT NULL
    op.execute("UPDATE learning_entries SET content = title WHERE content IS NULL")
    op.alter_column("learning_entries", "content", nullable=False)
    
    op.add_column("learning_entries", sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    
    # ------------------------------------------------------------------ #
    # 2. Create `learning_proposals` table
    # ------------------------------------------------------------------ #
    op.create_table(
        "learning_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning_entries.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("is_skill_worthy", sa.Boolean(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_learning_proposals_status", "learning_proposals", ["status"])

    # ------------------------------------------------------------------ #
    # 3. Create `proposed_skill_items` table
    # ------------------------------------------------------------------ #
    op.create_table(
        "proposed_skill_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning_proposals.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("skill_name", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False), # 'reinforce_existing' or 'create_new'
        sa.Column("matched_skill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("skills.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confidence", sa.String(length=50), nullable=False), # 'high', 'medium', 'low'
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False), # 'pending', 'approved', 'rejected'
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_proposed_skill_items_status", "proposed_skill_items", ["status"])

    # ------------------------------------------------------------------ #
    # 4. RLS Enforcement
    # ------------------------------------------------------------------ #
    for table in ["learning_proposals", "proposed_skill_items"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table}
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
    # Drop policies and tables
    for table in ["proposed_skill_items", "learning_proposals"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        op.drop_table(table)

    # Revert learning_entries
    op.drop_column("learning_entries", "timestamp")
    op.drop_column("learning_entries", "content")
    op.alter_column("learning_entries", "title", new_column_name="topic", nullable=False)
