# Fix v0.2.1 — Windows PowerShell smoke catalogue

## Cause
In Windows PowerShell 5.1, `@(Invoke-RestMethod ...)` can wrap the JSON list as a single pipeline object. `Where-Object` then passes the entire collection, so `$iit.id` contains both IIT and ISB UUID values. FastAPI correctly rejects the non-scalar `institution_id` with HTTP 422.

## Fix
`smoke_catalogue.ps1` now iterates through the actual institution result to select `IIT` as a single object and casts its ID to `[guid]` before generating JSON. No API, database, Docker, or Alembic changes were made.

## Install
For existing deployments, replace only `scripts/smoke_catalogue.ps1` with the fixed file. Do NOT delete `.env` or volumes. No rebuild required. Run:

```powershell
cd D:\SmartCampus_AI_Backend_v1
.\scripts\smoke_catalogue.ps1
.\scripts\smoke_visitor.ps1
docker compose exec -T api python -m alembic current
```

Expected: `PASS` for both scripts and `0002_visitor_memory (head)` for migration.

Note: PowerShell 5.1 cannot be executed in the code-generation environment; this is a targeted fix based on the actual returned schema validation error. Backend pytest regression suite and file structure are unchanged.
