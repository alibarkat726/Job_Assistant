"""Repair tenant isolation and add durable RAG indexing lifecycle.

Revision ID: 010_rag_production
Revises: 529feb1e1df7
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = '010_rag_production'
down_revision = '529feb1e1df7'
branch_labels = None
depends_on = None

# Standardize every existing tenant policy, including the older inconsistent ones.
TENANT_TABLES = ['cvs', 'work_histories', 'education_entries', 'cv_skills', 'skills',
    'projects', 'project_skills', 'learning_entries', 'learning_proposals', 'proposed_skill_items',
    'job_applications', 'jd_requirements', 'tailored_cvs', 'interview_prep_sets',
    'interview_questions', 'application_skill_matches', 'cover_letters',
    'chat_sessions', 'chat_messages', 'document_chunks', 'rag_index_jobs']
# table -> source kind and field identifying its parent document.
SOURCE_TABLES = {
    'cvs': ('cv', 'id'), 'work_histories': ('cv', 'cv_id'),
    'education_entries': ('cv', 'cv_id'), 'cv_skills': ('cv', 'cv_id'),
    'projects': ('project', 'id'), 'project_skills': ('project', 'project_id'),
    'skills': ('skill', 'id'), 'cover_letters': ('cover_letter', 'id'),
    'interview_prep_sets': ('interview_prep', 'id'),
    'interview_questions': ('interview_prep', 'prep_set_id'),
    'learning_entries': ('learning', 'id'),
}


def upgrade():
    conn = op.get_bind()
    vector_version = conn.scalar(sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
    if not vector_version or tuple(int(part) for part in vector_version.split('.')[:2]) < (0, 8):
        raise RuntimeError('pgvector is required; install the extension before applying this migration.')
    # Remove all legacy embeddings, whose model provenance cannot be established.
    # Their sources are durably queued below for a clean rebuild.
    op.execute('DELETE FROM document_chunks')
    column = next(c for c in sa.inspect(conn).get_columns('document_chunks') if c['name'] == 'embedding')
    if isinstance(column['type'], sa.JSON):
        op.alter_column('document_chunks', 'embedding', type_=Vector(768),
                        postgresql_using='NULL::vector(768)')
    for name, length in [('embedding_version', 255), ('chunking_version', 100), ('content_hash', 64)]:
        op.add_column('document_chunks', sa.Column(name, sa.String(length), nullable=False))
    op.create_unique_constraint('uq_document_chunks_source_position', 'document_chunks',
                                ['user_id', 'source_type', 'source_id', 'chunk_index'])
    op.create_check_constraint('chunk_index_nonnegative', 'document_chunks', 'chunk_index >= 0')
    op.execute('CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops)')
    op.execute("CREATE INDEX ix_document_chunks_lexical ON document_chunks USING gin (to_tsvector('simple', content))")
    # Reject corrupt legacy rows for explicit operator repair rather than deleting history.
    if conn.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM chat_messages m WHERE role NOT IN ('user', 'assistant') OR NOT EXISTS (SELECT 1 FROM chat_sessions s WHERE s.id=m.session_id AND s.user_id=m.user_id))")):
        raise RuntimeError('Repair inconsistent legacy chat messages before applying this migration.')
    op.create_unique_constraint('uq_chat_sessions_id_user', 'chat_sessions', ['id', 'user_id'])
    op.drop_constraint('fk_chat_messages_session_id_chat_sessions', 'chat_messages', type_='foreignkey')
    op.create_foreign_key('fk_chat_messages_session_owner', 'chat_messages', 'chat_sessions',
                         ['session_id', 'user_id'], ['id', 'user_id'], ondelete='CASCADE')
    op.create_check_constraint('message_role', 'chat_messages', "role IN ('user', 'assistant')")
    op.create_index('ix_chat_messages_user_session_created', 'chat_messages', ['user_id', 'session_id', 'created_at'])
    op.drop_column('chat_sessions', 'system_prompt_override')
    op.create_table('rag_index_jobs',
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('revision', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_error', sa.String(100), nullable=True))
    op.create_index('ix_rag_index_jobs_due', 'rag_index_jobs', ['next_attempt_at'])
    op.execute('INSERT INTO rag_index_jobs (user_id) SELECT id FROM users')
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation_policy ON {table}')
        expression = "user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid"
        op.execute(f'CREATE POLICY tenant_isolation_policy ON {table} USING ({expression}) WITH CHECK ({expression})')
    # The worker can discover queued user IDs only. Source and chunk tables still
    # require normal tenant context; the role must have neither SUPERUSER nor BYPASSRLS.
    op.execute("CREATE POLICY rag_worker_discovery ON rag_index_jobs FOR SELECT USING (current_user = 'rag_worker')")
    op.execute('''
        CREATE FUNCTION rag_source_changed() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE row_data jsonb; uid uuid; sid uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN row_data := to_jsonb(OLD);
            ELSE row_data := to_jsonb(NEW); END IF;
            uid := (row_data->>'user_id')::uuid;
            sid := (row_data->>TG_ARGV[1])::uuid;
            IF TG_OP = 'UPDATE' AND OLD.user_id <> NEW.user_id THEN
                RAISE EXCEPTION 'Changing source ownership is forbidden';
            END IF;
            IF TG_OP = 'UPDATE' AND to_jsonb(OLD)->>TG_ARGV[1] <> row_data->>TG_ARGV[1] THEN
                DELETE FROM document_chunks WHERE user_id = uid AND source_type = TG_ARGV[0]
                    AND source_id = (to_jsonb(OLD)->>TG_ARGV[1])::uuid;
            END IF;
            DELETE FROM document_chunks WHERE user_id = uid
                AND source_type = TG_ARGV[0] AND source_id = sid;
            -- Skill names are also represented inside project chunks.
            IF TG_TABLE_NAME = 'skills' THEN
                DELETE FROM document_chunks WHERE user_id = uid AND source_type = 'project';
            END IF;
            -- User deletion cascades must not resurrect a queue entry.
            IF EXISTS (SELECT 1 FROM users WHERE id = uid) THEN
                INSERT INTO rag_index_jobs (user_id) VALUES (uid)
                ON CONFLICT (user_id) DO UPDATE SET revision = rag_index_jobs.revision + 1,
                    requested_at = now(), next_attempt_at = now(), attempts = 0, last_error = NULL;
            END IF;
            RETURN NULL;
        END $$
    ''')
    for table, (source, field) in SOURCE_TABLES.items():
        op.execute(f"CREATE TRIGGER rag_source_changed AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION rag_source_changed('{source}', '{field}')")


def downgrade():
    # Do not restore the insecure prompt override or inconsistent RLS policies.
    raise RuntimeError('Security migration is forward-only; restore a verified backup to roll back.')
