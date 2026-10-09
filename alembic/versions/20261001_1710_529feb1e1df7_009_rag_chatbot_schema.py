"""009_rag_chatbot_schema

Revision ID: 529feb1e1df7
Revises: b05ee130c3eb
Create Date: 2026-10-01 17:10:16.276167

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy.vector

# revision identifiers, used by Alembic.
revision: str = '529feb1e1df7'
down_revision: Union[str, None] = 'b05ee130c3eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Check if pgvector extension is installed on PostgreSQL system
    res = conn.execute(sa.text("SELECT count(*) FROM pg_available_extensions WHERE name = 'vector';")).scalar()
    has_vector_ext = bool(res and res > 0)

    if has_vector_ext:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 1. Create chat_sessions table
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False, server_default='New Chat Session'),
        sa.Column('system_prompt_override', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_chat_sessions_user_id_users'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_sessions'))
    )
    op.create_index(op.f('ix_chat_sessions_id'), 'chat_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_chat_sessions_user_id'), 'chat_sessions', ['user_id'], unique=False)

    # 2. Create document_chunks table with pgvector or fallback JSON storage
    embedding_col_type = (
        pgvector.sqlalchemy.vector.VECTOR(dim=768) if has_vector_ext else sa.JSON()
    )

    op.create_table(
        'document_chunks',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', embedding_col_type, nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_document_chunks_user_id_users'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_document_chunks'))
    )
    op.create_index(op.f('ix_document_chunks_id'), 'document_chunks', ['id'], unique=False)
    op.create_index(op.f('ix_document_chunks_source_id'), 'document_chunks', ['source_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_source_type'), 'document_chunks', ['source_type'], unique=False)
    op.create_index(op.f('ix_document_chunks_user_id'), 'document_chunks', ['user_id'], unique=False)
    op.create_index('ix_document_chunks_user_source', 'document_chunks', ['user_id', 'source_type'], unique=False)

    # 3. Create HNSW Cosine Vector Index if pgvector extension is available
    if has_vector_ext:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops);"
        )

    # 4. Create chat_messages table
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('sources_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['session_id'], ['chat_sessions.id'],
            name=op.f('fk_chat_messages_session_id_chat_sessions'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_chat_messages_user_id_users'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_messages'))
    )
    op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)
    op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_user_id'), 'chat_messages', ['user_id'], unique=False)

    # 5. Enable RLS and Tenant Isolation Policies
    for table in ['chat_sessions', 'document_chunks', 'chat_messages']:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY tenant_isolation_policy ON {table} "
            "USING (user_id = current_setting('app.current_tenant', true)::uuid);"
        )


def downgrade() -> None:
    for table in ['chat_messages', 'document_chunks', 'chat_sessions']:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")

    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding;")

    op.drop_index(op.f('ix_chat_messages_user_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_id'), table_name='chat_messages')
    op.drop_table('chat_messages')

    op.drop_index('ix_document_chunks_user_source', table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_user_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_source_type'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_source_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_id'), table_name='document_chunks')
    op.drop_table('document_chunks')

    op.drop_index(op.f('ix_chat_sessions_user_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_id'), table_name='chat_sessions')
    op.drop_table('chat_sessions')
