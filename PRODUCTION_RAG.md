# RAG implementation and rollout

The code now requires migration `010_rag_production`. Apply it with migration credentials, not the API's runtime credentials. It is forward-only: take and verify a backup first. It removes derived legacy embeddings because their model provenance is unknown, queues a rebuild for every existing user, removes the prompt override column, and refuses inconsistent legacy chat ownership. Source documents and valid chat history are preserved.

## Deployment sequence

1. Provision PostgreSQL with server-side pgvector **0.8 or newer**, Redis, and separate migration/API/worker database credentials. Install/update the vector extension before migrating an existing JSON-fallback installation.
2. Install the locked dependencies with `uv sync --locked`. Warm the tokenizer vocabulary during the image build using `python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"`. Preserve that cache in the deployed image (`TIKTOKEN_CACHE_DIR` can specify its location). Runtime startup must not depend on downloading vocabulary.
3. Apply `uv run alembic upgrade head` using the migration database URL. New requests must use the upgraded schema.
4. Start the API with a restricted database role and `ENVIRONMENT=production`, explicit `CORS_ORIGINS`, `OPENAI_API_KEY`, and `RATE_LIMIT_STORAGE_URI=rediss://...` (use TLS and authentication for Redis). `LLM_API_KEY` is not used as an OpenAI credential.
5. Start a separate worker with the same provider/Redis/chunking configuration and `DATABASE_URL` using the **rag_worker** database role: `uv run python -m app.rag.worker`. `--once` processes one batch for maintenance. Supervise and restart it through your process/container manager.
6. Route readiness probes to `/ready`; `/health` remains a liveness check. Readiness checks the database role, extension, migration, and Redis. Provider network availability is represented by request failures; do not make costly model calls from health probes.
7. Monitor `rag_index_jobs` backlog, oldest `requested_at`, retry counts, `last_error`, worker logs, provider latency/error rate, and quota rejections. Failed jobs remain queued and retry with bounded exponential backoff. Errors contain exception classes, never document text or provider error bodies.

Create roles through your secret-management process. The worker's database role must be named `rag_worker`, have LOGIN, and have neither SUPERUSER nor BYPASSRLS. The API role also must have neither attribute. Do not give either role table ownership, schema creation, TRUNCATE, or DDL privileges. RLS is forced, but superuser/BYPASSRLS still bypass it.

Example grants, adapted to your database and API role name:

```sql
GRANT USAGE ON SCHEMA public TO app_user, rag_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
REVOKE TRUNCATE ON ALL TABLES IN SCHEMA public FROM app_user, rag_worker;
GRANT SELECT ON cvs, work_histories, education_entries, cv_skills,
  projects, project_skills, skills, cover_letters, interview_prep_sets,
  interview_questions, learning_entries TO rag_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON document_chunks, rag_index_jobs TO rag_worker;
```

The narrow queue discovery policy lets `rag_worker` discover queued user IDs. Every source/chunk operation still binds transaction-local tenant context. Connection reuse does not retain tenant state. API requests cannot switch the tenant of an existing ORM session.

## API changes

- `POST /api/v1/chat/ingest/sync-all` returns **202**, `{"status":"queued", ...}`. It does not perform provider calls in the request.
- `GET /api/v1/chat/ingest/status` returns the current user's pending job, retry state, and chunk count. `idle` means no job is queued, not that the user necessarily has documents.
- Session creation rejects `system_prompt_override`; old overrides are removed by the migration.
- Messages reject whitespace-only input and content over 8,000 characters; titles are bounded to 255 characters.
- Source filters accept only `cv`, `project`, `skill`, `cover_letter`, `interview_prep`, and `learning`.
- Invalid or foreign session IDs return **404**. Provider failures return safe **503** responses. Daily token-budget exhaustion returns **429**.
- History returns the latest requested number of messages, ordered chronologically. Session lists are paginated.
- Citation records include `citation_id` (e.g. `S1`) corresponding to answer markers `[S1]`. Only cited records are returned; citation IDs are validated, but semantic support still needs evaluation.

## Index lifecycle and retrieval

Database triggers invalidate affected chunks and enqueue indexing in the same transaction as each source mutation. CV children, project-skill links, and interview questions participate. Skill edits also invalidate project text. Deleted documents are excluded by live-source checks even before cleanup. No stale fallback index is served after an edit; answers can temporarily abstain until indexing finishes. Previously saved chat answers and user messages remain chat records until session/account deletion; define retention separately from source-index deletion.

The worker serializes indexing per user with a transaction advisory lock. A complete sync commits atomically; provider failures roll back replacement. A queue revision/row-lock check detects changes during indexing. Crashed workers release their locks and leave work queued. Identical chunks in the active embedding/chunking version are reused without provider calls. Source ownership is validated before ingesting entities.

Every text section is split by tokens, with defaults of 400 tokens and 60 overlap. CV skills and raw extraction are preserved, interview questions are separate sections, and learning entries are indexed. Chunks store content hashes, embedding/chunking versions, token counts, and section metadata. Changing embedding models or chunking settings requires enqueueing all users for rebuild; incompatible embedding versions are never searched together.

Retrieval combines tenant-filtered cosine search and PostgreSQL full-text search using reciprocal-rank fusion, exact-content deduplication, and HNSW iterative scans. `RAG_MIN_SIMILARITY=0.25` is an initial cosine threshold to calibrate against your own dataset; lexical matches can still qualify. Context/history/output budgets are configurable. Retrieved evidence is untrusted JSON data; system policy is immutable. Generated cover letters/interview outlines are labeled as drafts.

`RAG_DAILY_TOKEN_BUDGET` defaults to 100,000 tokens per user, shared between API and worker through atomic Redis reservations. Chat reserves an upper bound on prompt, response, and embedding tokens; indexing reserves actual input token estimates before provider calls. Reservations include the configured SDK retry allowance, are conservative, and are not refunded after attempts. Redis failures fail closed. Development with memory rate-limit storage omits daily token budgets; production requires Redis.

`RAG_TEST_MODE=true` is allowed only with `ENVIRONMENT=testing`. It never calls providers and uses explicitly versioned synthetic vectors. Do not enable it in deployments or evaluate retrieval quality with its vectors.

## Verification and remaining rollout work

```bash
uv run pytest -q tests/unit/test_rag_production.py tests/unit/test_cv_security.py tests/unit/test_cv_storage.py
RAG_DATABASE_TESTS=1 uv run pytest -q tests/integration/test_rag_production_database.py
```

The opt-in database tests require test-admin credentials in `TEST_DATABASE_URL`. They create a fresh database and non-bypass role, run every migration, and remove both afterward. They never truncate the configured database. Several older tests use a destructive shared-database fixture; do not run the whole suite against a valuable database.

Before release: provision encrypted private storage and backup/restore verification; move credentials to your secrets manager; rotate any real credentials committed to Git and address sensitive repository history. Add a representative retrieval/grounding evaluation dataset, adversarial prompt-injection evaluation, concurrency/load tests, and SLO dashboards. Citation validation checks source identity, not truthfulness. File size/page/expanded-text limits are implemented; hard parser CPU/time isolation and malware scanning remain deployment work. Provider retries and input/output tokens must be budgeted against your provider's actual billing model.
