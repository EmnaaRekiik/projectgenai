# Sprint Socle Technique — phase 2, sessions visiteurs et mémoire (SA-25, SA-26)

## Changement livré en v0.2.0

Le serveur continue à gérer le catalogue académique déjà en place. Une migration **additive** `0002_visitor_memory` ajoute deux tables, sans suppression ni modification des données du catalogue.

| Story | Tâche | Livrable vérifiable |
|---|---|---|
| SA-24 | **SA-25** Gestion des sessions visiteurs | API de création, lecture et suppression, identifiant UUID et jeton aléatoire envoyé une seule fois, contrôle d'accès par jeton, durée de validité limitée |
| SA-24 | **SA-26** Mémoire temporaire | Messages utilisateur stockés en PostgreSQL avec ordre chronologique, pagination, fenêtre des N derniers messages, séparation stricte par visiteur, suppression en cascade |

La route de contexte **ne génère pas de réponses IA** et **ne calcule pas de profil candidat**. Les conversations avec un vrai LLM seront réalisées en SA-36/SA-37.

## Routes

| Méthode | Route | Résultat |
|---|---|---|
| POST | `/api/v1/visitor/sessions` | 201, identifiant et `token` secret |
| GET | `/api/v1/visitor/sessions/{session_id}` | Détails de la session du propriétaire |
| POST | `/api/v1/visitor/sessions/{session_id}/messages` | 201, message utilisateur persisté |
| GET | `/api/v1/visitor/sessions/{session_id}/messages?limit=20&offset=0` | Historique paginé |
| GET | `/api/v1/visitor/sessions/{session_id}/context?limit=12` | Fenêtre récente dans l'ordre naturel |
| DELETE | `/api/v1/visitor/sessions/{session_id}` | 204 et effacement de l'historique |

À l'exception du `POST` de création, ces routes requièrent `X-Visitor-Token` obtenu à la création. La valeur brute n'est **jamais persistée** : seule son empreinte SHA-256 est stockée. Les jetons ont une entropie cryptographique d'environ 256 bits. Aucune route publique ne permet de créer des messages avec le rôle `assistant`.

## Démonstration sur la vraie base PostgreSQL

Après remplacement des fichiers et redémarrage Docker :

```powershell
.\scripts\start.ps1
.\scripts\smoke_catalogue.ps1
.\scripts\smoke_visitor.ps1

docker compose exec -T api python -m alembic current
```

La migration courante doit être `0002_visitor_memory (head)`.

Le test `smoke_catalogue.ps1` crée un brouillon **fictif**, le modifie, vérifie son invisibilité publique et l'archive ; il ne publie aucun contenu non vérifié. Le test `smoke_visitor.ps1` crée deux visiteurs, persiste deux tours d'échange pour le premier, vérifie l'isolation des données, puis supprime ses deux sessions de test.

## Tests et limites

- Tests pytest du catalogue et des visiteurs : `python -m pytest -q` (en mémoire SQLite pour tests rapides).
- CI : `.github/workflows/ci.yml` prépare une **base PostgreSQL de test** distincte, applique Alembic, vérifie les migrations et exécute toute la suite.
- Les expirations refusent l'accès après un TTL par défaut de 24 heures (`VISITOR_SESSION_TTL_HOURS`, maximum 168 heures).
- Les données expirées **restent en base jusqu'à purge** ; la commande `docker compose exec -T api python -m app.db.purge_expired` est prévue pour un job quotidien. Sans programmation quotidienne, il n'existe pas encore de garantie de suppression physique au bout de 24 h.
- Limites : 4 000 caractères/message, 200 messages/session par défaut, fenêtre mémoire <=30 messages.
- **Avant production publique** : ajouter rate limiting, purge automatique planifiée, monitoring et politique de conservation validée. Ce ne sont pas des éléments prouvés par la suite de tests actuelle.

## Captures/preuves à joindre dans Project Supervision

1. `docker compose ps` avec les deux services healthy.
2. `alembic current` donnant `0002_visitor_memory (head)`.
3. Swagger : nouveau groupe « Sessions visiteurs et mémoire ».
4. `POST /visitor/sessions` : `201`; cacher le token dans la capture.
5. `POST /messages` deux fois puis `GET /context` avec les deux messages.
6. Résultat terminal des deux scripts smoke PASS.
7. Résultat `python -m pytest -q`.

**Ne jamais publier les valeurs de `.env` ni les tokens de sessions dans les captures.**
