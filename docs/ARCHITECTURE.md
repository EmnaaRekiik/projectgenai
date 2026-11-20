# SmartCampus AI — Architecture technique v0.2.0

## Flux métier actuellement implémentés

```mermaid
flowchart TD
    C[Client web / Swagger] --> A[FastAPI /api/v1]
    A --> PP[Catalogue public: PUBLISHED seulement]
    A --> PA[Administration: StaffBearer + RBAC]
    A --> VS[Sessions visiteurs: X-Visitor-Token]
    PP --> DB[SQLAlchemy ORM]
    PA --> DB
    VS --> DB
    DB --> PG[(PostgreSQL 16)]
    M[Alembic 0001 à 0004] --> PG
    PG --> I[institutions]
    PG --> P[programs]
    PG --> S[visitor_sessions]
    PG --> H[conversation_messages]
    PG --> U[staff_users]
    PG --> A[staff_sessions]
```

## Schéma relationnel

```mermaid
erDiagram
    INSTITUTIONS ||--o{ PROGRAMS : propose
    VISITOR_SESSIONS ||--o{ CONVERSATION_MESSAGES : contient
    INSTITUTIONS {
        UUID id PK
        VARCHAR code UK
        VARCHAR name
    }
    PROGRAMS {
        UUID id PK
        UUID institution_id FK
        VARCHAR code
        VARCHAR title
        VARCHAR level
        VARCHAR status
        VARCHAR official_source_url
        TIMESTAMPTZ verified_at
    }
    VISITOR_SESSIONS {
        UUID id PK
        VARCHAR token_hash UK
        TIMESTAMPTZ expires_at
        INTEGER next_message_sequence
    }
    CONVERSATION_MESSAGES {
        UUID id PK
        UUID session_id FK
        INTEGER sequence
        VARCHAR role
        TEXT content
    }
```

## Invariants et frontières

1. `0001_catalogue` est conservée à l'identique : nouvelles fonctionnalités ajoutées exclusivement dans `0002_visitor_memory`.
2. Un programme n'est consultable publiquement que s'il est publié avec URL et date de vérification.
3. Administration : comptes Argon2id, token opaque 256 bits révoquable, RBAC et isolement des responsables IIT/ISB. La clé historique n'autorise que le bootstrap initial ; après cela aucune route de catalogue ne l'accepte.
4. Visiteurs : sessions indépendantes, token 256 bits retourné une fois, empreinte SHA-256 en PostgreSQL, expiration vérifiée à chaque appel, plafond de messages.
5. Le modèle Ollama `qwen3.5:4b` est connecté et le test multi-tours a passé le 20 novembre 2026 sur le PC utilisateur. Le RAG documentaire complet et l'évaluation systématique Tunisien/Arabizi restent à faire.
6. Les données officielles IIT/ISB doivent être collectées et validées par l'équipe avant publication ; jamais d'informations inventées présentées comme officielles.

## Répartition des travaux

- Nous : SA-5, SA-7, SA-12, SA-16, SA-17, SA-20 et maintenant SA-25, SA-26 ; puis SA-36/37.
- Autres membres : SA-13/14 (candidatures/documents), SA-21/22 (tarifs et vérifications), SA-8/9 (frontend/env) et les autres tâches prévues. Coordonner les nouveaux modèles au moyen de migrations additives.
