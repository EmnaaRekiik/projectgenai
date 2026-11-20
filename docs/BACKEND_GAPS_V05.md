# SmartCampus AI 0.5.0 — Backlog audit and technical evidence

> This describes **backend functionality**, not completion of the entire agentic platform. All official IIT/ISB prices and programme details must be provided and reviewed by authorized staff. We intentionally seed no fake official course facts.

## Actual scope of the release

| Story | Backend change | Evidence / acceptance |
|---|---|---|
| SA-5 — APIs and access | OpenAPI v0.5 contract, resource matrix for catalogue, candidate, visitor, staff; design for later file APIs | `docs/API_CONTRACT.md`, `/openapi.json`, `tests/test_openapi_contract.py` |
| SA-7 — Backend | Existing FastAPI, app modularization, typed errors, Swagger | Original tests and `/health/ready` |
| SA-12 — Academic model | Institution -> programme -> specializations/courses/admission/prerequisite/document rules/tuition; optional course->specialization FK | `app/models/catalogue_detail.py`, migration 0005, schema checks |
| SA-16 — PostgreSQL | Existing live PostgreSQL 16, no changes to existing container/volume | On user workstation: `docker compose ps`, `/health/ready` |
| SA-17 — Tables/relations | Additive migrations 0005, 0006, 0007 with named CHECK, UNIQUE, FK, indexes | `alembic upgrade head`, `alembic check` on real PostgreSQL |
| SA-20 — Catalogue APIs | Staff CRUD of each detail resource; protected admin drafts; verified-only public; search/filter programmes; archive programme | `tests/test_academic_details.py`, `smoke_backend_gaps.ps1` |
| SA-25 — Visitor sessions | Existing hashed owner token, 24h expiry, max messages; now atomic per-IP registration rate limits and background purge | `tests/test_visitors.py`, `tests/test_new_retention.py`, retention worker |
| SA-26 — Temporary memory | Existing ordered PostgreSQL messages, context window and isolation; now scheduled physical deletion after expiry | `app/db/cleanup_loop.py`, `tests/test_new_retention.py` |
| SA-28 — Login/roles | Existing staff Argon2id + 5 roles; now candidate signup/login/profile/change password/logout/account deletion; independent tokens; SMTP email verification when configured | `tests/test_staff_auth.py`, `tests/test_candidates.py` |
| SA-36 — LLM bridge | Existing Qwen/Ollama integration untouched | User's earlier `smoke_chat.ps1` PASS; rerun after deployment |
| SA-37 — LLM memory | Existing LLM conversation memory untouched | Same live chat test; semantic answer quality separate |

## Actual institutional data, not fabricated

A programme is publicly accessible only when `PUBLISHED` and with an authorized staff-recorded HTTPS source and verification time. A subordinate tuition/course/specialization/rule is **additionally private** until it independently receives an HTTPS source and timestamp. Editing substantive content clears its verification timestamp and removes the detail from public access until reverification.

Course-to-specialization is optional: the database uses the composite FK `(specialization_id, program_id)` to prevent linking a course to a specialization from a different programme.

## Explicit limitations / prerequisites

- No official IIT/ISB study programmes, admission requirements or tuition amounts are supplied or invented in this package. Publishing factual information requires the institution's real verified sources.
- Actual email verification requires SMTP_HOST and SMTP_FROM plus working TLS SMTP credentials. Candidate registration and authentication work without SMTP, but `email_verified_at` stays null, and resend verification returns 503. A production frontend should not treat unverified email as proof of identity.
- The automatic retention worker starts through `docker compose up -d --build` as the third `retention` service; the previous `db` volume is untouched. It cleans expired visitor/chat records (FK cascade), staff/candidate sessions, verification challenges and limit buckets.
- Fixed-window rate limiting is keyed to a server-HMAC of client IP without storing the IP. It is intentionally simple, persistent across API replicas, and should be supplemented by ingress/proxy controls for production deployments.
- No RAG, LangGraph, document storage, speech-to-text, preinscription, QCM or calendar integration in this release; those are other project phases and should not be claimed done.
- Generated code was tested in an isolated SQLite API test suite and PostgreSQL offline migrations. It **must still be deployed and checked on the user's real PostgreSQL** before marking the migration and runtime smoke checks validated.

## Install without destroying data

1. Back up the real database. Never `docker compose down -v`.
2. Extract the complete release ZIP into `D:\`, merging the `SmartCampus_AI_Backend_v1` directory. **Keep the existing local `.env` and Docker volumes.** The ZIP deliberately excludes `.env`.
3. In PowerShell, run:

   ```powershell
   cd D:\SmartCampus_AI_Backend_v1
   .\scripts\start.ps1
   docker compose exec -T api python -m alembic current
   docker compose ps
   .\scripts\smoke_backend_gaps.ps1
   .\scripts\smoke_catalogue.ps1
   .\scripts\smoke_visitor.ps1
   .\scripts\smoke_auth.ps1
   .\scripts\smoke_chat.ps1
   ```

   Expected migration: `0007_abuse_limits (head)`; three services: `db`, `api`, `retention`.
4. Run `docker compose logs --tail=50 retention` to confirm the retention job reports results (and no repeated error).

## Database operations

Old `0001`–`0004` tables and data are retained; new `0005`–`0007` migration steps **add** only new tables. No existing table is dropped in `upgrade()`. `down -v` and `alembic downgrade` are **not** part of the install instructions.
