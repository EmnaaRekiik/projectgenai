# Contrat API — Catalogue universitaire (v1)

Base URL local Docker : `http://127.0.0.1:8001`.
Format : JSON UTF-8 ; identifiants : UUID ; dates : ISO 8601 avec fuseau.
La documentation OpenAPI est générée par FastAPI à `/docs` et `/openapi.json`.

| Méthode | Route | Accès | Comportement |
|---|---|---|---|
| GET | `/api/v1/health/live` | Public | État du processus |
| GET | `/api/v1/health/ready` | Public | Connexion BDD et schéma vérifiés |
| GET | `/api/v1/institutions` | Public | Liste des établissements |
| GET | `/api/v1/institutions/{id}` | Public | Un établissement |
| POST | `/api/v1/institutions` | `StaffBearer` (admin) | Création établissement |
| GET | `/api/v1/programs` | Public | Formations publiées seulement |
| GET | `/api/v1/programs/{id}` | Public | Formation publiée, sinon 404 |
| GET | `/api/v1/admin/programs` | `StaffBearer` (rôle autorisé) | Liste incluant brouillons/archives |
| GET | `/api/v1/admin/programs/{id}` | `StaffBearer` (rôle autorisé) | Détails y compris brouillon |
| POST | `/api/v1/admin/programs` | `StaffBearer` (édition) | Création toujours en brouillon |
| PATCH | `/api/v1/admin/programs/{id}` | `StaffBearer` (édition) | Mise à jour et publication contrôlée |
| DELETE | `/api/v1/admin/programs/{id}` | `StaffBearer` (édition) | Archivage, code 204 |

## Champs du programme

`id`, `institution_id`, `code`, `title`, `level`, `duration_years`, `description`, `official_source_url`, `verified_at`, `status`, `created_at`, `updated_at`.

- `level` : `LICENCE`, `PREPARATORY`, `ENGINEERING`, `OTHER`.
- `status` : `DRAFT`, `PUBLISHED`, `ARCHIVED`.
- Une formation créée avec `POST` reste `DRAFT` sans exception.
- Publication : `official_source_url` doit être HTTPS, `verified_at` doit être horodaté, avec fuseau, non futur. Les deux champs sont obligatoires, et la base impose leur présence par contrainte CHECK lorsque le statut est `PUBLISHED`.
- Les archives ne sont plus visibles publiquement. L'identifiant n'est jamais réutilisé.
- Un même `code` ne peut pas être réutilisé dans un établissement ; il peut exister dans un autre établissement.
- `duration_years` vaut entre 1 et 10 si renseigné.
- Il n'y a **aucun tarif ou condition d'admission saisi arbitrairement** ; ces ressources relèvent de SA-21 et de l'intégration de sources officielles.

## Recherche et pagination

`GET /api/v1/programs?institution_id=UUID&level=LICENCE&q=informatique&limit=20&offset=0`.
`limit` : 1–100 (20 par défaut). `offset` : entier positif. L'objet réponse : `{"items":[],"total":0,"limit":20,"offset":0}`.
`q` : recherche textuelle sur le titre, sans interprétation des jokers SQL saisis par l'utilisateur.

## Accès et erreurs

- 200 / 201 / 204 : lecture, création, archivage réussis.
- 401 : session staff absente, invalide, expirée ou révoquée.
- 403 : rôle non autorisé.
- 404 : établissement ou formation absent ; les brouillons sont également masqués sur les routes publiques.
- 409 : violation d'unicité ou conflit d'intégrité.
- 422 : données invalides ou publication sans sources vérifiées.
- 503 : bootstrap non configuré, ou BDD indisponible sur l'endpoint ready.

## Authentification staff (v0.4.0)

| Méthode | Route | Accès | Comportement |
|---|---|---|---|
| POST | `/api/v1/auth/bootstrap` | `X-Admin-Key` une seule fois | Premier admin uniquement |
| POST | `/api/v1/auth/login` | Public avec mot de passe | Fournit un bearer expirant |
| GET | `/api/v1/auth/me` | `StaffBearer` | Profil et rôle |
| POST | `/api/v1/auth/logout` | `StaffBearer` | Révoque le token |
| POST | `/api/v1/auth/change-password` | `StaffBearer` | Remplace le mot de passe, révoque tous les tokens |
| GET | `/api/v1/staff` | `PLATFORM_ADMIN` | Liste comptes staff |
| POST | `/api/v1/staff` | `PLATFORM_ADMIN` | Crée un membre avec son rôle |
| PATCH | `/api/v1/staff/{id}` | `PLATFORM_ADMIN` | Édite rôle/établissement/nom et révoque les tokens si droits changés |
| POST | `/api/v1/staff/{id}/deactivate` | `PLATFORM_ADMIN` | Désactive et révoque les tokens |

Consulter `docs/SPRINT_PHASE_4.md` pour la matrice de permissions complète et les instructions d'initialisation.

---

# Extension v0.5.0 — catalogue complet, candidats et rétention

## Catalogue académique normalisé (SA-12 / SA-17 / SA-20)

Pour chaque programme `P`, les quatre familles de ressources ci-dessous ont les mêmes opérations :

| Type | Endpoint public (lecture des données vérifiées uniquement) | Endpoint staff (lecture, création, modification, suppression) |
|---|---|---|
| Spécialités | `GET /api/v1/programs/P/specializations` | `GET/POST /api/v1/admin/programs/P/specializations`, `PATCH/DELETE /api/v1/admin/programs/P/specializations/{item_id}` |
| Matières / unités | `GET /api/v1/programs/P/courses` | `GET/POST /api/v1/admin/programs/P/courses`, `PATCH/DELETE /api/v1/admin/programs/P/courses/{item_id}` |
| Admissions / prérequis / documents requis | `GET /api/v1/programs/P/admission-rules` | `GET/POST /api/v1/admin/programs/P/admission-rules`, `PATCH/DELETE /api/v1/admin/programs/P/admission-rules/{item_id}` |
| Tarifs officiels | `GET /api/v1/programs/P/tuition` | `GET/POST /api/v1/admin/programs/P/tuition`, `PATCH/DELETE /api/v1/admin/programs/P/tuition/{item_id}` |

- `POST` retourne 201 et l'élément créé ; `PATCH` retourne 200 ; `DELETE` retourne 204.
- Spécialité : `code`, `title`, `description`. Matière : `code`, `title`, `semester` (1–20), `credits` (0–60), `specialization_id` facultatif. Une clé étrangère composite garantit que la spécialité appartient au même programme.
- Règle : `kind = ADMISSION | PREREQUISITE | DOCUMENT`, `title`, `description`. Ce sont les **conditions documentaires** requises, pas les fichiers candidats.
- Tarif : `label`, `amount` (`DECIMAL(12,2)`, >= 0), `currency` (ISO 3 lettres), `academic_year` (`2026-2027`), `note`.
- Chaque détail comprend `official_source_url` (HTTPS) et `verified_at` (horodatage non futur). Un détail créé sans preuve reste administrable mais invisible au public même si son programme est publié. Modifier les données invalide la vérification jusqu'à revue par un responsable.
- Toute écriture nécessite `PLATFORM_ADMIN` ou `ACADEMIC_IIT/ISB` pour sa propre institution. `DIRECTION` a un accès **lecture** aux détails, sans droit d'écriture. Les visiteurs ne voient ni brouillons ni données non vérifiées.
- Pagination des listes : `limit` entre 1 et 100 et `offset` positif. Les programmes publics et staff se filtrent par `institution_id`, `level` et `q` (titre/code/description) ; la liste staff peut aussi filtrer `status`.

## Comptes candidats (SA-28)

| Méthode | URL | Accès | Réponse |
|---|---|---|---|
| POST | `/api/v1/candidates/register` | Public, limité en fréquence | 201, profil candidat sans mot de passe |
| POST | `/api/v1/candidates/login` | Public, limité en fréquence | 200, bearer token opaque et expiration |
| GET | `/api/v1/candidates/me` | CandidateBearer | 200, profil du candidat connecté |
| PATCH | `/api/v1/candidates/me` | CandidateBearer | 200, mise à jour profil uniquement |
| DELETE | `/api/v1/candidates/me` | CandidateBearer | 204, suppression du compte et de ses sessions |
| POST | `/api/v1/candidates/logout` | CandidateBearer | 204, révocation immédiate |
| POST | `/api/v1/candidates/change-password` | CandidateBearer | 204, révoque tous ses jetons |
| POST | `/api/v1/candidates/resend-verification` | CandidateBearer et SMTP | 202 ou 503 si SMTP absent |
| POST | `/api/v1/candidates/verify-email` | Code à usage unique envoyé par mail | 204, confirme la propriété de l'adresse |

Un candidat n'obtient **jamais** les droits `StaffBearer`. Un token candidat est distinct du token `X-Visitor-Token` utilisé sans inscription, qui reste accessible à tous. Les mots de passe sont hachés Argon2id, et les tentatives erronées sont limitées avec verrouillage temporaire.

La vérification d'email est entièrement implémentée, mais son **envoi réel dépend de SMTP**. Sans SMTP, le compte peut se connecter avec `email_verified_at = null` et ne doit pas être considéré comme une identité vérifiée.

## Utilisation, sécurité, durée de vie (SA-25 / SA-26)

- `POST /api/v1/visitor/sessions` : jeton de session aléatoire retourné une fois, stocké uniquement par empreinte SHA-256. Dépendance à la possession de ce jeton pour voir/écrire des messages.
- Expiration visiteur par défaut : 24 h ; messages maximum : 200. Fenêtre LLM par défaut : 12 derniers messages. Limite atomique création visiteur : 300 par adresse IP par heure ; inscription candidat : 10 par heure ; login candidat : 60 par heure ; configurations via `.env`.
- Le service Docker `retention` exécute `app.db.cleanup_loop` toutes les heures et purge les sessions expirées ainsi que les conversations enfants (cascade PostgreSQL). Il supprime aussi les sessions staff/candidats expirées, les challenges d'email expirés et les compteurs expirés.
- Codes d'erreur pertinents : `401` token absent/expiré ; `403` rôle interdit ; `404` objet inaccessible/hors institution ; `409` doublon ou conflit ; `410` session visiteur expirée ; `422` données non valides ; `429` quota de création dépassé (en-tête `Retry-After`) ; `503` SMTP non configuré ou service indisponible.

## Fichiers candidats — contrat de phase ultérieure, pas une API livrée

Les documents candidat (pièce d'identité, diplôme, relevé) exigeront du stockage binaire, des consentements, antivirus, politiques d'accès, liens temporaires et quotas. **Aucun endpoint de dépôt de fichier n'est implémenté en 0.5.0** ; le futur contrat est `POST /api/v1/candidates/me/documents` (upload), `GET /api/v1/candidates/me/documents` (liste), `DELETE /api/v1/candidates/me/documents/{id}` (retrait) et consultation staff filtrée par rôle. Ce choix évite de simuler un stockage de fichiers à l'aide de métadonnées fictives. L'implémentation appartient à une phase de dossiers/préinscription distincte.
