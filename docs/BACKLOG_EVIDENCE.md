# Evidence réelle de travail — sprint « Socle Technique »

Date du livrable : 20 novembre 2026. Le sprint du projet est annoncé du 9 au 22 novembre 2026.

| Backlog | Élément livré | Preuves techniques | Statut honnête |
|---|---|---|---|
| SA-5 — API et accès | Contrat public/admin ; Swagger/OpenAPI ; clé provisoire | `docs/API_CONTRACT.md`, `app/core/security.py`, test du schéma OpenAPI | **Partiel** : RBAC à faire dans SA-28 |
| SA-7 — Initialiser le backend | App FastAPI, structure modulaire, env configuré, Dockerfile | `app/main.py`, `Dockerfile`, tests d'API | **Implémenté, vérification Docker locale en attente** |
| SA-12 — Tables du catalogue | `institutions`, `programs` avec contraintes et champs de preuve officielle | `app/models/`, `migrations/versions/0001_catalogue.py`, `docs/ARCHITECTURE.md` | **Première version implémentée** |
| SA-16 — PostgreSQL | PostgreSQL 16 Docker Compose, healthcheck, stockage persistant | `compose.yaml`, `.env.example`, `scripts/start.ps1` | **Configuré ; non exécuté dans l'environnement de génération** |
| SA-17 — Relations et migrations | Migration initiale, clé étrangère, CHECK, indexes, unicité | migration versionnée, `docs/migration_postgresql_preview.sql` | **Migration SQL générée ; appliquer sur PostgreSQL réel** |
| SA-20 — API de gestion formations | CRUD admin + lecture publique, publication contrôlée, archivage | `app/api/routers/programs.py`, `tests/test_catalogue.py` | **API implémentée, tests locaux passés ; test PostgreSQL CI à exécuter** |

**Ne pas marquer SA-16/SA-17 Done** avant un lancement Docker réussi et une inspection des tables. Ne pas marquer SA-5 Done tant que les règles d'accès définitives ne sont pas validées. Les tests en mémoire ne prouvent pas l'exécution de PostgreSQL.

## Preuves à joindre dans Project Supervision après lancement

1. Capture `docker compose ps` montrant `db` et `api` en état healthy.
2. Capture `GET /api/v1/health/ready` avec HTTP 200.
3. Capture Swagger des routes catalogue et un POST admin retournant 201.
4. Capture `GET /api/v1/admin/programs` avec la formation `DRAFT` et `GET /api/v1/programs` montrant qu'elle est masquée.
5. Résultat de `docker compose exec -T api python -m alembic current` donnant `0001_catalogue`.
6. `python -m pytest -q` puis, avec une base PostgreSQL dédiée aux tests, validation CI complète.

## À ne pas revendiquer dans cette livraison

SA-25, SA-26, SA-28, SA-32, SA-36, SA-37 : **non réalisés dans ce nouveau dépôt**. Ils viendront après stabilisation des fondations. Ne pas confondre l'ancien prototype et ce projet réinitialisé.


## Mise à jour v0.2.0 — 20 novembre 2026

L'utilisateur a confirmé le déploiement local v0.1.1 : containers PostgreSQL et API `healthy`, `alembic current = 0001_catalogue`, `GET /health/ready = ready/connected`, Swagger visible. Ces sorties constituent une vérification locale du **socle existant**, pas des nouvelles fonctionnalités v0.2.0.

| Backlog | Nouveau livrable | Preuves | Statut |
|---|---|---|---|
| SA-25 | Création, lecture, expiration, suppression et isolation de sessions visiteurs anonymes | `app/api/routers/visitors.py`, `app/models/visitor.py`, tests, SQL migration `0002` | Implémenté ; test avec PostgreSQL local v0.2.0 à exécuter |
| SA-26 | Messages ordonnés en base, historique paginé, fenêtre contexte N, suppression en cascade | mêmes fichiers + `tests/test_visitors.py`, `scripts/smoke_visitor.ps1` | Implémenté ; test avec PostgreSQL local v0.2.0 à exécuter |
| SA-20 | Script de test du cycle CRUD sur la vraie base | `scripts/smoke_catalogue.ps1` | À exécuter en local pour preuve finale |

Ne pas déclarer SA-36/SA-37 réalisés : `GET /context` retourne du texte stocké, **pas une réponse de LLM**.

## Vérification signalée par l'utilisateur — 20 novembre 2026

Les sorties du terminal démontrent sur son poste : `PASS` de `smoke_catalogue.ps1`, `PASS` de `smoke_visitor.ps1`, puis `0002_visitor_memory (head)` avec `PostgresqlImpl`. Il s'agit de preuves concrètes pour **SA-20, SA-25 et SA-26**.

## Nouvelle livraison v0.3.0 — LLM avec mémoire (à valider sur Windows)

| Backlog | Preuves dans le dépôt | Statut |
|---|---|---|
| SA-36 | `app/llm/provider.py`, `app/api/routers/chat.py`, `tests/test_llm_provider.py`, `scripts/smoke_chat.ps1` | Implémenté + tests isolés ; **appel à un vrai LLM sur Windows restant à exécuter** |
| SA-37 | `app/llm/context.py`, historique DB dans `chat.py`, tests de multi-tours et de propriété du jeton | Implémenté + tests isolés ; **preuve d'inférence et de mémoire réelle en attente** |

Migration additive `0003_chat_lease` : sauvegarde des messages utilisateur + assistant dans une même transaction, prévention des tours concurrents, libération après erreur. Les tests utilisent un double de modèle uniquement pour contrôler l'intégration. **Ne pas déclarer LLM testé en production avant `smoke_chat.ps1` PASS avec modèle configuré.** Consulter `docs/SPRINT_PHASE_3.md`.

## Validation réelle SA-36 / SA-37 et nouveau livrable SA-28 — 20 novembre 2026

L'utilisateur a communiqué `PASS: 2 live model calls, 4 persisted messages, multi-turn context (model: qwen3.5:4b).` avec le modèle tournant à **100 % GPU**, soit une preuve effective de la liaison FastAPI → Ollama et du stockage PostgreSQL. L'exactitude des réponses en tunisien/Arabizi n'est pas encore établie.

**SA-28 — partiellement validé** : comptes administrateurs et responsables académiques, Argon2id, bearer de session, connexion / expiration / logout / changement mot de passe, attribution/changement de rôle, contrôles IIT vs ISB. `app/models/staff.py`, `app/api/routers/auth.py`, `app/api/routers/staff.py`, `app/core/security.py`, `migrations/versions/0004_staff_auth.py`, `tests/test_staff_auth.py`. **71 tests API automatisés passés**, migration SQL hors ligne générée ; test réel Docker et comptes sur le PC utilisateur encore à faire. Ne cocher Done qu'après les smoke tests. `docs/SPRINT_PHASE_4.md`.
