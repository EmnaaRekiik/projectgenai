# SmartCampus AI — SA-36 + SA-37 — LLM et mémoire (v0.3.0)

## Ce qui est effectivement développé

- `app/llm/provider.py`: **vraie requête HTTP** au format Chat Completions d'une API compatible OpenAI (`POST .../v1/chat/completions`), modèle configurable, clé facultative pour Ollama et obligatoire selon le fournisseur distant. Pas de réponse fictive en production.
- `app/llm/context.py`: instructions système en français, tunisien et Arabizi, mémoire ordonnée et tronquée pour limiter les coûts, catalogue strictement limité aux programmes publiés avec source et date de vérification.
- `POST /api/v1/visitor/sessions/{session_id}/chat`: vérifie l'appartenance par token, envoie contexte + nouvelle question au LLM, stocke **dans une seule transaction** le message utilisateur et celui du modèle. Échec réseau : aucun message incomplet en base.
- `0003_chat_lease`: deux nouvelles colonnes nullable sur `visitor_sessions`, sans destruction des sessions existantes, pour empêcher deux requêtes concurrentes sur la même session.
- `scripts/smoke_chat.ps1`: test de deux appels IA réels, 4 messages en PostgreSQL, avec suppression des données de test à la fin.
- Tests d'API avec un **double LLM uniquement en tests**. Tests transport HTTP avec `httpx.MockTransport`. Ils ne prouvent pas la qualité d'un modèle exécuté sur le poste utilisateur.

## Flux technique

```mermaid
sequenceDiagram
    participant C as Client / Swagger
    participant A as FastAPI
    participant P as PostgreSQL
    participant L as Ollama / LLM distant
    C->>A: POST /visitor/sessions/{id}/chat + X-Visitor-Token
    A->>P: Vérifie token, expiration et réservation de tour
    P-->>A: Session réservée; verrou libéré
    A->>P: Charge messages récents et catalogue publié
    P-->>A: Contexte ordonné et références autorisées
    A->>L: POST /chat/completions (contexte + question)
    L-->>A: Réponse réellement générée
    A->>P: Transaction: user + assistant; fin de réservation
    P-->>A: 2 messages enregistrés
    A-->>C: 201 + réponse + modèle + sources du catalogue
```

### Contraintes et comportements

| Situation | HTTP | Comportement |
|---|---|---|
| Aucun modèle configuré | 503 | Aucun message sauvegardé |
| Token absent | 401 | Accès refusé |
| Token d'une autre session | 404 | Pas de fuite de données |
| LLM indisponible / réponse invalide | 502 | Tour annulé, le prochain essai est possible |
| Timeout du modèle | 504 | Tour annulé |
| Autre requête chat en cours | 409 | Pas de tour superposé |
| Conversation déjà pleine | 409 | Pas d'enregistrement partiel |
| LLM répond correctement | 201 | 2 messages enregistrés, ordonnés |

**Attention aux limites** : Le LLM n'est pas un RAG complet. Le système utilise uniquement un **extrait limité** du catalogue des programmes publiés (au plus huit fiches). La colonne `catalogue_sources` indique les références fournies au modèle, **pas des citations vérifiées générées par lui**. Le fait d'inscrire une URL et une date dans la base ne prouve pas automatiquement qu'une source est officielle. Il faut une vérification humaine préalable. Pas de profil candidat structuré, de recommandation calculée, de fine-tuning, de transcription vocale, d'authentification des comptes (SA-28) ni de workflow agentique.

### Sécurité et protection des données

- La réponse est limitée en taille; les messages utilisateur sont limités à 4 000 caractères.
- Les jetons visiteurs restent secrets et seule leur empreinte est stockée en base.
- Ne pas publier les clés dans Swagger, Git, des captures ou des logs.
- Avec un fournisseur distant, les messages de conversation et les données du catalogue incluses dans le prompt lui sont transmis. **N'utilisez pas de données réelles de candidats sans étude de confidentialité, information et consentement appropriés.**
- La base conserve les sessions jusqu'à leur expiration puis jusqu'à l'exécution du job de purge; lancer périodiquement `python -m app.db.purge_expired`.
- Avant un déploiement public : rate limits, politique RGPD/locale de confidentialité, contrôle de dépenses, observabilité sans logs de texte brut, contrôle d'authentification/RBAC et gestion des incidents.

## Configuration et preuve locale

Dans `.env` **du projet existant**, ajouter les lignes suivantes si vous utilisez Ollama installé sur Windows :

```dotenv
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen2.5:3b-instruct
LLM_API_KEY=
```

À exécuter **sur Windows**, avec Ollama installé et démarré :

```powershell
ollama pull qwen2.5:3b-instruct
ollama list
```

Un modèle peut être lent sur CPU, en particulier au premier appel. Le modèle 3B est un modèle de démarrage, **pas une preuve de performance sur l'Arabizi**.

Puis :

```powershell
cd D:\SmartCampus_AI_Backend_v1
.\scripts\start.ps1

docker compose exec -T api python -m alembic current
.\scripts\smoke_catalogue.ps1
.\scripts\smoke_visitor.ps1
.\scripts\smoke_chat.ps1
```

Attendu: `0003_chat_lease (head)` et PASS de chacun des scripts, y compris un véritable appel au modèle. Si `smoke_chat.ps1` échoue HTTP 502, vérifier que Ollama tourne et qu'il est joignable depuis le conteneur Docker (`host.docker.internal:11434`) ; vérifier le nom du modèle avec `ollama list`. Si 504, réduire le modèle ou ajuster `LLM_TIMEOUT_SECONDS` après avoir confirmé que l'inférence démarre correctement. Le lancement PostgreSQL et le Swagger restent fonctionnels **même si le LLM n'est pas configuré**.

### Tests reproductibles

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

**Ne jamais** faire tourner la suite `pytest` avec `TEST_DATABASE_URL` pointant vers le PostgreSQL normal de l'application : les fixtures réinitialisent le catalogue. La CI peut tester sur une base séparée avec toutes les migrations.

### Preuves pour Project Supervision

1. Swagger: `POST .../chat` avec sécurité `VisitorSessionToken`.
2. La migration `0003_chat_lease (head)` dans le terminal.
3. PASS de `smoke_chat.ps1` **après avoir configuré un vrai modèle**.
4. `GET .../messages` contenant un aller-retour user/assistant avec le bon ordre (masquer token et données privées).
5. Capture de la configuration du modèle **sans clé API** et des réponses FR/TN/Arabizi à évaluer séparément.

N'annoncer SA-36/SA-37 **Done** qu'après exécution des tests sur votre machine avec un vrai modèle et inspection des réponses produites. Le protocole de comparaison des modèles est un autre livrable, SA-33/SA-34.

## Correctif v0.3.1 — Ollama local et délai d'inférence

Un essai réel de l'utilisateur a confirmé la configuration LLM et l'accès HTTP 200 à Ollama,
mais `smoke_chat.ps1` retournait HTTP 504 (`Language model timed out`).
Le client v0.3.0 limitait le temps d'attente à 90 s et passait par `/v1/chat/completions`
sans contrôle explicite du mode de réflexion.

v0.3.1 introduit `LLM_PROVIDER=ollama`, une requête native `/api/chat` avec `think=false`,
une limite configurable jusqu'à 300 s et un test Windows du temps réel d'inférence.
Le mode `openai` précédent est conservé. Pas de modification PostgreSQL ni de migration.

**Validation** : tests automatiques HTTP mock + base de test ; essai de modèle réel
et test de mémoire sur PostgreSQL Windows encore à refaire avant de cocher SA-36/37 Done.
