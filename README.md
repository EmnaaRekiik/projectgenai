# SmartCampus AI — Backend v0.5.0 (backend backlog gap completion)

This project is the FastAPI/PostgreSQL backend for the IIT/ISB SmartCampus AI orientation project. It preserves the existing working Qwen/Ollama conversation integration while adding the previously missing academic catalogue, candidate authentication and scheduled retention features.

**This is not the complete agentic application.** Frontend, authoritative institutional content, RAG, speech, preinscription, QCM and appointments remain other phases. Candidate verification emails require separate working SMTP credentials.

## Delivered functionality

- FastAPI with typed REST APIs, Swagger/OpenAPI (`/docs`), PostgreSQL 16, SQLAlchemy and versioned Alembic migrations.
- Academic catalogue: programmes, specializations, course/semester/credits (optional same-program specialization), admission/prerequisite/document rules and official tuition by academic year. Admin staff can CRUD detail resources. Programme deletion archives rather than destroys history. Public APIs only show published programme data with independently verified HTTPS evidence.
- Role-based staff accounts: `PLATFORM_ADMIN`, `ACADEMIC_IIT`, `ACADEMIC_ISB`, `INTERVIEW_MANAGER`, `DIRECTION`, password hashing, revocable login, protected IIT/ISB writes.
- Candidate accounts: independent password login, profile, interests, password rotation, logout, deletion, optional SMTP-based email verification. **Unverified email is never presented as verified.**
- Anonymous visitors: random session secret, isolation, limited chat history, configurable message TTL and quotas, automatic expired-data cleanup by a dedicated Compose `retention` worker.
- Existing Ollama/Qwen chat with PostgreSQL memory and concurrent-turn protection; no artificial programme details seeded.
- Automated tests in `tests/`; PostgreSQL offline upgrade SQL generation and a GitHub Actions integration workflow for a real PostgreSQL test database.

## Upgrade existing Windows installation — retain `.env` and PostgreSQL data

**First make a backup.** Never use `docker compose down -v` and never overwrite the existing `.env` file. The release ZIP intentionally excludes `.env` and evaluation results.

Extract the ZIP into `D:\`, merging the contained `SmartCampus_AI_Backend_v1` folder with your existing folder. Then in PowerShell:

```powershell
cd D:\SmartCampus_AI_Backend_v1
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start.ps1
docker compose exec -T api python -m alembic current
docker compose ps
.\scripts\smoke_backend_gaps.ps1
.\scripts\smoke_catalogue.ps1
.\scripts\smoke_visitor.ps1
.\scripts\smoke_auth.ps1
.\scripts\smoke_chat.ps1
```

Expected migration: `0007_abuse_limits (head)`. Expected running services: `db`, `api` and `retention` (`api` and `db` healthy). The new smoke script prompts for the **existing** platform administrator email and password. **Do not bootstrap another administrator or rotate the existing key as part of this upgrade.**

```powershell
docker compose logs --tail=50 retention
```

You should see a retention-job result. The service checks for expired data hourly and deletes sessions and their dependent conversation messages after expiry. The job can also be run manually with `docker compose exec -T api python -m app.db.purge_expired`.

## Explore in Swagger

Open **http://127.0.0.1:8001/docs**. Useful groups:

- `POST /api/v1/candidates/register` and `POST /api/v1/candidates/login` — candidate self-service; candidate bearer is **not** staff bearer.
- `/api/v1/admin/programs/{program_id}/specializations`, `/courses`, `/admission-rules`, `/tuition` — read, create, edit and remove details with authorized staff bearer.
- `/api/v1/programs/{program_id}/...` — public verified detail lists; anonymous access cannot see drafts.
- `POST /api/v1/visitor/sessions` then `/chat` — anonymous model chat, no account required.

### SMTP for verified candidate emails

Email verification is implemented but not functional until an authenticated SMTP provider is configured. Add appropriate `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_FROM`, `SMTP_USERNAME`, `SMTP_PASSWORD` to the existing `.env` and recreate `api`. STARTTLS is required. Without SMTP, candidate login still works but `email_verified_at = null` and the resend endpoint responds 503. Do not represent such accounts as verified.

### Configuration

See `.env.example` for optional settings: `RETENTION_INTERVAL_SECONDS`, visitor/session TTL, per-IP create limits, candidate session TTL/login limits, SMTP settings. Your existing `.env` values remain valid without editing.

## Testing and claims

On a development machine with Python and dependencies installed:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

**IMPORTANT:** Unit tests use an isolated SQLite database only as a *test double*, with foreign keys enabled; runtime services always use PostgreSQL. CI provisions a disposable PostgreSQL 16 database, applies all migrations and compares the ORM schema to Alembic. **Never point `TEST_DATABASE_URL` at your actual working database** because tests delete records.

For real evidence on Windows, run the smoke scripts and inspect the responses. The code generator's environment does not have Docker/PostgreSQL available, so migration execution and end-to-end runtime smoke tests on your workstation still require your confirmation.

## Documentation

- `docs/BACKEND_GAPS_V05.md`: exact SA-5/7/12/16/17/20/25/26/28/36/37 task mapping, proofs and limitations.
- `docs/API_CONTRACT.md`: endpoint contract, model and access matrix, error codes and planned document API design.
- `docs/openapi_snapshot.json`: generated contract locked by an automated test.
- `docs/README_HISTORY_THROUGH_V04.md`: development history for earlier releases.

No official IIT/ISB programmes, tuition fees, prereqs, or admission decisions are invented by this repository.
