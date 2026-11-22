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

---

# Extension T7 — modalités de paiement, statut de publication et période de validité (migration 0011)

## Nouvelle ressource : modalités de paiement

Même schéma d'accès que les tarifs et les conditions d'admission.

| Type | Public (lecture) | Staff (lecture, création, modification, suppression) |
|---|---|---|
| Modalités de paiement | `GET /api/v1/programs/P/payment-terms` | `GET/POST /api/v1/admin/programs/P/payment-terms`, `PATCH/DELETE /api/v1/admin/programs/P/payment-terms/{item_id}` |

Champs : `label`, `academic_year` (`2026-2027`, deux années consécutives), `payment_mode` (`FULL` ou `INSTALLMENTS`), `installments_count` (2 à 12, **obligatoire** pour `INSTALLMENTS`, **interdit** pour `FULL`), `first_payment_percent` (supérieur à 0 et au plus 100), `schedule_description`, `note`, plus les champs de source et de publication ci-dessous. Un même `label` est unique par programme et par année (409 sinon).

## Statut de publication et validité (tarifs, modalités de paiement, conditions d'admission)

| Champ | Valeurs | Remarque |
|---|---|---|
| `publication_status` | `DRAFT`, `PUBLISHED`, `ARCHIVED` | Défaut `PUBLISHED` : le comportement existant est conservé, la vérification de la source reste obligatoire. `DRAFT` et `ARCHIVED` masquent l'élément au public sans effacer sa vérification. |
| `valid_from` | date-heure **avec fuseau horaire**, ou `null` | Début de validité. Converti en UTC. Une date sans fuseau est refusée (422). |
| `valid_to` | idem | Fin de validité. Doit être strictement postérieure à `valid_from` (422 sinon, y compris lors d'un PATCH comparé aux valeurs déjà enregistrées). Une borne vide signifie « sans limite ». |

### Ce que voient les candidats et l'agent IA

Un élément est visible par les routes publiques **si et seulement si** :
1. le programme est `PUBLISHED` ;
2. l'élément a une source HTTPS et une date de vérification non future ;
3. `publication_status = PUBLISHED` ;
4. la date du jour est comprise dans `[valid_from, valid_to]` (bornes vides = illimité).

Les routes administrateur montrent toujours tout, quelle que soit la période. L'agent IA doit appeler les routes publiques, ou la fonction `official_and_valid_now(model)` de `app/api/routers/catalogue_details.py`, pour ne jamais lire un brouillon, un élément archivé ou une période expirée.

### Vérification après modification
- Modifier le **contenu** (libellé, montant, mode de paiement, nombre d'échéances, description, etc.) ou les **dates de validité** retire `verified_at` : l'élément redevient privé jusqu'à une nouvelle vérification.
- Modifier seulement `publication_status` ne retire **pas** la vérification (c'est une action de gestion).

### Codes d'erreur
`401` sans jeton staff ; `403` rôle non autorisé ; `404` programme absent, brouillon sur route publique, ou autre institution ; `409` libellé déjà utilisé pour l'année ; `422` valeurs invalides (mode et échéances incohérents, période inversée, fuseau manquant, année non consécutive, `publication_status` nul).

## Exemple

```json
POST /api/v1/admin/programs/{P}/payment-terms
{
  "label": "Paiement en trois tranches",
  "academic_year": "2026-2027",
  "payment_mode": "INSTALLMENTS",
  "installments_count": 3,
  "first_payment_percent": "40.00",
  "schedule_description": "40 % à l'inscription, 30 % en décembre, 30 % en mars",
  "valid_from": "2026-09-01T00:00:00+01:00",
  "valid_to": "2027-08-31T23:59:59+01:00",
  "official_source_url": "https://exemple.tn/source-officielle",
  "verified_at": "2026-11-20T10:00:00+01:00"
}
```
(L'URL ci-dessus est un exemple de format, pas une source officielle.)
