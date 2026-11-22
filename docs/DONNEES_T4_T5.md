# SmartCampus AI — Modèle de données ajouté par les tâches T4 et T5

Migrations additives, à la suite de `0007_abuse_limits` : aucune table existante n'est modifiée ou supprimée.

| Migration | Contenu | Tâche |
|---|---|---|
| `0008_admission_requests` | `preregistrations`, `equivalence_requests`, `appointments`, `interview_results` | T4 |
| `0009_profile_conversations` | `academic_profiles`, `candidate_conversations`, `candidate_messages`, index « une préinscription active par programme » | T4 |
| `0010_documents_ingestion` | `documents`, `document_versions`, `document_chunks`, `ingestion_jobs` | T5 |

La prochaine migration (T7, paiement et validité des tarifs) sera `0011`.

## Les trois profils dans la base

| Profil | Table | Remarque |
|---|---|---|
| Visiteur sans compte | `visitor_sessions`, `conversation_messages` | Existantes : jeton haché, expiration 24 h |
| Candidat identifié | `candidate_users`, `candidate_sessions`, `academic_profiles`, `candidate_conversations`, `candidate_messages` | Profil académique séparé de la table des comptes |
| Responsable | `staff_users`, `staff_sessions` | 5 rôles |

## Candidat, demandes et conversations

```mermaid
erDiagram
    CANDIDATE_USERS ||--o| ACADEMIC_PROFILES : possede
    CANDIDATE_USERS ||--o{ CANDIDATE_CONVERSATIONS : possede
    CANDIDATE_CONVERSATIONS ||--o{ CANDIDATE_MESSAGES : contient
    CANDIDATE_USERS ||--o{ PREREGISTRATIONS : depose
    PROGRAMS ||--o{ PREREGISTRATIONS : vise
    CANDIDATE_USERS ||--o{ EQUIVALENCE_REQUESTS : depose
    CANDIDATE_USERS ||--o{ APPOINTMENTS : a
    STAFF_USERS ||--o{ APPOINTMENTS : anime
    APPOINTMENTS ||--o| INTERVIEW_RESULTS : produit
    STAFF_USERS ||--o{ INTERVIEW_RESULTS : enregistre
```

### Rattachement d'une conversation visiteur (pour T9)

```mermaid
sequenceDiagram
    participant V as Visiteur
    participant F as Frontend
    participant B as Backend
    participant DB as PostgreSQL
    V->>F: se connecte ou crée un compte
    F->>B: login (jeton visiteur présent)
    B-->>F: pending_session = true
    F->>V: associer votre conversation à votre profil ?
    V->>F: oui (consentement explicite)
    F->>B: POST claim (jeton candidat + jeton visiteur + consentement)
    B->>DB: vérifier empreinte du jeton, session non expirée, non déjà rattachée
    B->>DB: transaction : copier les messages vers candidate_messages
    DB-->>B: source_visitor_session_id unique : refus si déjà rattachée
    B-->>F: conversation du candidat
```

Contrôles à implémenter dans T9 : empreinte du jeton visiteur égale à celle en base (comparaison à temps constant), session non expirée, consentement vrai, tout dans une seule transaction. Codes attendus : 403 session d'un autre visiteur, 409 déjà rattachée, 410 expirée.

## Documents et indexation

```mermaid
erDiagram
    INSTITUTIONS ||--o{ DOCUMENTS : possede
    DOCUMENTS ||--o{ DOCUMENT_VERSIONS : versions
    DOCUMENT_VERSIONS ||--o{ DOCUMENT_CHUNKS : decoupe
    DOCUMENTS ||--o{ INGESTION_JOBS : suivi
    DOCUMENT_VERSIONS ||--o{ INGESTION_JOBS : traite
```

### Flux d'indexation

| Événement | Ce que fait le backend | Ce que fait le worker |
|---|---|---|
| Import d'un document | Crée `documents` et une version (`sha256`, chemin, `is_current`) puis un job `ADD` en `PENDING` | Prend le job (`RUNNING`, bail `locked_until`), extrait le texte, écrit `document_chunks`, calcule les embeddings quand le vecteur sera disponible, termine en `SUCCEEDED` |
| Nouvelle version | Crée la version, passe l'ancienne à `is_current = false`, crée un job `UPDATE` | Remplace les chunks de l'ancienne version par ceux de la nouvelle |
| Suppression | Soft delete (`deleted_at`), crée un job `DELETE` | Retire les chunks du document de l'index |
| Échec | — | `FAILED` avec `error_message`, `attempts` incrémenté ; nouveau job possible jusqu'à `max_attempts` |

### Ajouter les vecteurs plus tard
Quand le modèle d'embedding sera choisi (T10), une migration ajoutera, par exemple, une table `chunk_embeddings (chunk_id, embedding vector(N))` avec l'extension pgvector. `document_chunks.embedding_model` et `embedded_at` indiquent déjà quels chunks sont indexés et avec quel modèle. Ce changement nécessitera l'image `pgvector/pgvector:pg16` : à tester sur une base neuve.
