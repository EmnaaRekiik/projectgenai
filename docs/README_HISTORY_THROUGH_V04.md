# SmartCampus AI — Backend v0.4.0


## Livrable actuel — v0.4.0 / SA-28

**Authentification staff et contrôle d'accès IIT/ISB.** 5 rôles, Argon2id, sessions bearer révoquables, verrouillage de login et migration additionnelle `0004_staff_auth`. L'ancienne clé admin ne sert plus qu'à créer le **premier** administrateur. Consulter **`docs/SPRINT_PHASE_4.md`** pour les commandes Windows exactes.

L'utilisateur a confirmé le 20 novembre 2026 que `smoke_chat.ps1` passe sur PostgreSQL avec **2 appels Ollama qwen3.5:4b réels et 4 messages enregistrés**, ainsi que le catalogue et les sessions visiteurs. Cette **nouvelle** partie SA-28 a **71 tests automatisés verts** mais la migration et les smoke tests staff restent à exécuter sur son Windows.

### Mise à niveau (remplace le parcours d'installation v0.3.0 décrit plus bas)

```powershell
cd D:\SmartCampus_AI_Backend_v1
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\rotate_bootstrap_key.ps1
.\scripts\start.ps1
docker compose exec -T api python -m alembic current
.\scripts\bootstrap_admin.ps1
.\scripts\smoke_auth.ps1
.\scripts\smoke_catalogue.ps1
.\scripts\smoke_visitor.ps1
.\scripts\smoke_chat.ps1
```

La migration attendue est **`0004_staff_auth (head)`**. Ne pas supprimer `.env` ni le volume `postgres_data`. Pour les tâches de catalogue, un compte staff authentifié est maintenant obligatoire ; les anciens tests de catalogue ont été adaptés.

---

> **Version de continuité** du dépôt que vous avez déjà lancé sur Windows. Pas de réinitialisation de la base PostgreSQL.

## État réel de l'avancement

**Validé sur le PC de l'équipe** (logs du 20 novembre 2026) : Docker/PostgreSQL, Alembic `0002_visitor_memory`, catalogue SQL (SA-20), sessions visiteur (SA-25), stockage et isolation mémoire (SA-26).

**Nouveau en v0.3.0 (SA-36/SA-37)** : backend de conversation branchable sur un **vrai modèle** via API OpenAI-compatible (local Ollama ou service hébergé), contexte multi-tours obtenu en PostgreSQL, références du catalogue *publié*, écriture atomique de chaque paire de messages, protection contre conversations simultanées. `0003_chat_lease` ajoute deux colonnes à la table existante.

**Historique v0.3.0** : les tests réels du LLM étaient initialement à confirmer ; ils ont depuis été **validés par l’utilisateur** avec `qwen3.5:4b` le 20 novembre 2026. Aucun modèle n’est inclus dans cette archive, et la qualité linguistique reste à mesurer.

## Installer / mettre à jour sur Windows

1. Garder le dossier existant `D:\SmartCampus_AI_Backend_v1`, son `.env` et ses volumes Docker. Ne jamais lancer `docker compose down -v` pour une mise à jour.
2. Décompresser la nouvelle archive **par-dessus** les fichiers du projet. Si votre extracteur recrée un dossier imbriqué, copier plutôt le contenu du dossier intérieur par-dessus l'ancien. **Ne pas remplacer `.env`**.
3. Dans PowerShell :

   ```powershell
   cd D:\SmartCampus_AI_Backend_v1
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\start.ps1
   docker compose exec -T api python -m alembic current
   .\scripts\smoke_catalogue.ps1
   .\scripts\smoke_visitor.ps1
   ```

   Migration attendue à partir de v0.4.0 : `0004_staff_auth (head)` ; les smoke tests du catalogue et des visiteurs doivent toujours passer. Swagger : <http://127.0.0.1:8001/docs>.

## Activer un **vrai** LLM

Option locale (Ollama, installation externe requise) : télécharger Ollama sur <https://ollama.com/download> pour Windows, démarrer le service, puis exécuter :

```powershell
ollama pull qwen2.5:3b-instruct
ollama list
```

Dans le fichier existant `.env`, ajouter (sans dupliquer les noms de variables) :

```dotenv
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen2.5:3b-instruct
LLM_API_KEY=
```

Ces paramètres font appeler le service local Windows **depuis le conteneur FastAPI**. Le modèle 3B est une option légère pour démarrer, pas un résultat de benchmark tunisien/Arabizi. Le premier appel peut être long.

Vous pouvez utiliser un fournisseur **hébergé** compatible OpenAI : choisissez son URL HTTPS se terminant par `/v1`, définissez `LLM_MODEL` selon son catalogue et `LLM_API_KEY` dans `.env`. Les messages seront alors **envoyés au fournisseur**, donc ne traitez pas de données personnelles réelles de candidats sans validation de confidentialité et consentement.

Redémarrez le conteneur API pour charger la configuration :

```powershell
.\scripts\start.ps1
.\scripts\smoke_chat.ps1
```

Le script `smoke_chat.ps1` déclenche **deux appels LLM réels**, vérifie 4 messages persistés dans PostgreSQL, puis nettoie sa session de test. Sans modèle configuré, `/chat` retourne volontairement `503` et n'enregistre aucune donnée. Le socle catalogue reste fonctionnel. En cas de `502`, vérifier le service Ollama et son modèle; en cas de `504`, vérifier la puissance machine ou le délai `LLM_TIMEOUT_SECONDS` (45 sec par défaut).

## Swagger — nouvelle route

1. `POST /api/v1/visitor/sessions` : créer un visiteur ; conserver `id` et `token` privés.
2. Swagger > **Authorize** > `VisitorSessionToken` : coller uniquement le `token` (pas la clé administrateur).
3. `POST /api/v1/visitor/sessions/{session_id}/chat`, body `{"content":"Salem, nheb na9ra informatique"}`.
4. Refaire le `POST` avec une question liée au premier message. Vérifier `user_message`, `assistant_message` et l'historique via `GET .../messages`.

Cette route fournit du texte généré uniquement si le fournisseur est configuré et disponible. Le champ `catalogue_sources` ne constitue **pas une citation garantie** du modèle. La partie RAG complète, le QCM, les comptes candidats et l'agent orchestrateur sont des travaux futurs.

## Tests et code

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Les tests rapides utilisent SQLite **uniquement comme double en mémoire**, et un stub LLM **uniquement dans les tests**. La production reste PostgreSQL et n'utilise **aucun** faux LLM. Le workflow CI s'exécute avec PostgreSQL de test, migrations réelles et suite API. **N'utilisez jamais la base de production comme `TEST_DATABASE_URL`** : les fixtures nettoient le catalogue.

Structure : `app/api/routers/` (API), `app/llm/` (provider réel + contexte), `app/db/` (SQLAlchemy), `app/models/`, `app/schemas/`, `migrations/` (0001, 0002, 0003), `scripts/` et `tests/`. Documentation détaillée : `docs/SPRINT_PHASE_3.md`, `docs/BACKLOG_EVIDENCE.md`, `docs/SPRINT_PHASE_2.md`, `docs/API_CONTRACT.md`.

## Limites avant un déploiement public

Les faits institutionnels doivent encore être vérifiés et publiés par un responsable. Le LLM ne fait ici que consulter une sélection du catalogue publiée; aucun RAG documentaire complet. Pas de STT/TTS, LoRA/QLoRA, authentification candidat (SA-29), orientation officielle ni action automatisée d'inscription. Les rôles staff SA-28 sont livrés en v0.4.0. Nécessite aussi rate limiting, politique de confidentialité et purge planifiée.


## v0.3.1 — Ollama local non-thinking transport / timeout diagnostics

The initial v0.3.0 OpenAI-compatible route waited up to 90 seconds for a
complete model reply. On a slower PC, this can time out even though Ollama is reachable.
This version preserves all PostgreSQL data and adds a native Ollama transport.

With an existing `.env`, **leave all PostgreSQL and admin settings unchanged** and set:

```dotenv
LLM_PROVIDER=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen3.5:4b
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=240
LLM_MAX_OUTPUT_TOKENS=256
```

`LLM_PROVIDER=ollama` selects Ollama's `/api/chat` endpoint with `think=false`.
`LLM_PROVIDER=openai` (the default) keeps the original `/v1/chat/completions` support.
Native non-thinking works on models that honor the switch. A response may still
be slow on CPU, depending on available RAM and hardware.

Use `./scripts/diagnose_ollama.ps1` on Windows to measure local inference
without Docker/FastAPI, and `ollama ps` to inspect whether the model is loaded
on CPU or GPU. Then run:

```powershell
docker compose up --build -d --force-recreate api
docker compose exec -T api python -c "from app.core.config import get_settings; s=get_settings(); print(s.llm_provider, s.llm_model, s.llm_timeout_seconds, s.llm_max_output_tokens)"
./scripts/smoke_chat.ps1
```

The old `/v1` setting can remain in `LLM_BASE_URL`; native mode strips `/v1`
before calling `/api/chat`. A 504 after these changes calls for measuring
actual model latency and confirming CPU/GPU offloading, rather than reinstalling
PostgreSQL or Docker. The model still must be evaluated for Derja/Arabizi quality.
