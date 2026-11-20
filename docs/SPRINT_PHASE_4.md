# Sprint Socle Technique — SA-28 : comptes staff, connexion et droits IIT/ISB

## Fonctionnalité livrée (backend v0.4.0)

Le partage d'une clé `X-Admin-Key` pour toutes les opérations d'administration a été **remplacé par des comptes staff individuels** et des tokens de session révoquables. Le clé historique reste acceptée **uniquement pour créer le premier administrateur**, une seule fois (route `/auth/bootstrap`). Après cette opération, les routes de catalogue et création d'établissement n'acceptent plus de clé partagée : elles exigent `Authorization: Bearer <staff_token>`.

- Comptes en base `staff_users` avec emails normalisés uniques et hash Argon2id (jamais de mot de passe en clair en base).
- Sessions `staff_sessions`, identifiées par token aléatoire 256 bits dont **seul le SHA-256 est stocké**. Expiration configurable, déconnexion, révocation après modification du mot de passe, du rôle ou désactivation.
- Verrouillage du compte 15 minutes après cinq échecs de connexion ; `401` uniforme pour les identifiants incorrects ou comptes inactifs.
- Rôles `PLATFORM_ADMIN`, `ACADEMIC_IIT`, `ACADEMIC_ISB`, `INTERVIEW_MANAGER`, `DIRECTION`. Aucun endpoint d'inscription de compte libre ; seul l'admin crée les autres comptes.
- Contrôle **côté serveur** du périmètre IIT/ISB, non simplement dans le frontend.
- Swagger sépare trois mécanismes de sécurité : `BootstrapKey`, `StaffBearer` et `VisitorSessionToken`.
- Migration additive `0004_staff_auth` : préserve `institutions`, `programs`, `visitor_sessions`, `conversation_messages` et les données existantes. Aucun reset.

## Matrice de permissions implémentées

| Rôle | Catalogue admin : lecture | Créer/modifier/archiver programme | Créer établissement | Gestion staff |
|---|---|---|---|---|
| PLATFORM_ADMIN | IIT + ISB | IIT + ISB | Oui | Oui |
| ACADEMIC_IIT | IIT uniquement | IIT uniquement | Non | Non |
| ACADEMIC_ISB | ISB uniquement | ISB uniquement | Non | Non |
| DIRECTION | IIT + ISB (lecture) | Non | Non | Non |
| INTERVIEW_MANAGER | Non (à développer plus tard) | Non | Non | Non |
| Visiteur | Public seulement | Non | Non | Non |

Le contrôle des dossiers candidats (SA-13, SA-29) est **hors périmètre de cette livraison**. Ce livrable réalise les rôles du personnel pour l'API catalogue ; il n'introduit pas encore l'authentification des candidats.

## Mise à niveau sur le PC Windows existant

1. Extraire cette archive **par-dessus** `D:\SmartCampus_AI_Backend_v1`, en conservant le `.env` et les volumes Docker. Ne pas exécuter `docker compose down -v`.
2. Les secrets précédemment affichés dans la conversation sont compromis. Pour au moins la **clé bootstrap**, vous pouvez exécuter le script ci-dessous ; il ne touche pas la base et ne révèle pas la nouvelle clé. Pour le mot de passe PostgreSQL partagé précédemment, voir « rotation des identifiants » ci-dessous.
3. Démarrer l'API et appliquer la migration (effectué automatiquement par `start.ps1`).
4. Créer **une seule fois** le premier administrateur avec un email et un nouveau mot de passe secret.
5. Vérifier le login et la protection du catalogue, puis relancer les smoke tests déjà validés.

```powershell
cd D:\SmartCampus_AI_Backend_v1
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\rotate_bootstrap_key.ps1
.\scripts\start.ps1

docker compose exec -T api python -m alembic current
# attendu : 0004_staff_auth (head)

.\scripts\bootstrap_admin.ps1
.\scripts\smoke_auth.ps1
.\scripts\smoke_catalogue.ps1
.\scripts\smoke_visitor.ps1
.\scripts\smoke_chat.ps1
```

`bootstrap_admin.ps1` demande l'email, le nom et le mot de passe via PowerShell ; il n'enregistre pas le mot de passe sur disque. `smoke_auth.ps1` et `smoke_catalogue.ps1` vous redemandent les identifiants pour obtenir un nouveau token, sans stocker le token dans `.env`. Le test du LLM utilise **votre Ollama local** déjà configuré et peut prendre plus longtemps que les tests catalogue.

**Stop conditions :** si Alembic n'indique pas `0004_staff_auth (head)`, ne tentez pas le bootstrap. Si `bootstrap_admin.ps1` retourne 409, un administrateur a déjà été créé : ne réinitialisez pas la DB. Si un login renvoie 401, vérifiez l'email/mot de passe ; après 5 échecs, attendez 15 minutes et réessayez, ou utilisez un compte admin fonctionnel.

## Parcours Swagger

1. `POST /api/v1/auth/login` avec `email` et `password` du personnel ; noter temporairement l'`access_token`, sans le publier.
2. Swagger > **Authorize** > `StaffBearer` : coller uniquement le token, sans préfixe « Bearer » dans le champ d'autorisation de type HTTP bearer.
3. `GET /api/v1/auth/me` : vérifier le rôle.
4. `GET /api/v1/admin/programs` : tester le contrôle d'accès ; `POST /api/v1/staff` pour provisionner un compte si rôle `PLATFORM_ADMIN`.
5. `POST /api/v1/auth/logout` : vérifier que le token révoqué retourne `401` sur `/auth/me`.

**Attention :** le token de connexion staff est différent de `X-Visitor-Token` (sessions de conversation anonymes). Aucun changement à Ollama ou aux messages visiteurs pour SA-28.

## Tests & preuves

- 71 tests Python passent en SQLite isolé pour vérifier la logique API, les rôles, l'authentification et les cas d'erreur.
- Une migration SQL PostgreSQL a été générée **hors connexion** dans `docs/migration_0004_full_chain_preview.sql`. Cela vérifie la génération du DDL, **pas son exécution réelle dans votre Docker**.
- Les scripts Windows réalisent la vérification PostgreSQL via l'API réelle ; leur exécution sur le poste utilisateur reste à confirmer avant de marquer SA-28 « Done ».
- La CI `.github/workflows/ci.yml` applique les migrations sur PostgreSQL dédié et vérifie la correspondance ORM/migrations. Ne JAMAIS définir `TEST_DATABASE_URL` sur une DB de données réelles.

## Rotation des identifiants déjà affichés

La clé `ADMIN_API_KEY` a été incluse dans une capture de la conversation : `rotate_bootstrap_key.ps1` la remplace par une nouvelle valeur aléatoire, et le prochain `start.ps1` recrée l'API. Pour `POSTGRES_PASSWORD`, **changer uniquement le `.env` ne change pas le mot de passe déjà enregistré dans le volume**. La rotation PostgreSQL devra se faire de manière coordonnée : `ALTER ROLE` SQL exécuté dans le conteneur, modification du `.env` correspondant, puis recréation des conteneurs. Ne pas afficher le nouveau mot de passe en terminal ou dans ce chat.

## Limites de sécurité avant un déploiement public

Il manque : TLS/HTTPS externe, rate limiting IP en plus du verrouillage par compte, audit trail des opérations sensibles, MFA et récupération de compte, gestion du consentement/rétention des données personnelles et campagnes d'admission. Les tokens staff sont pour **développement local**, pas pour exposition directe sur Internet. Ne pas confondre « tests d'API verts » avec audit de sécurité.
