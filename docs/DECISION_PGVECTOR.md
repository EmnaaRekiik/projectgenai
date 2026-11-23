# Décision — pgvector pour la recherche documentaire (ARCHITECTURE §7)

Statut : **proposition à valider par Personne A et Personne B** · Réponse à la décision ouverte n°1 de `ARCHITECTURE.md` §7.

## 1. Contexte

Le chat répond aujourd'hui à partir du catalogue vérifié et publié, injecté en entier dans le contexte. Cela ne tient plus dès que les documents (brochures, règlements, fiches) grossissent : il faut retrouver les passages pertinents avant d'appeler le LLM (RAG documentaire, tâches T11/T12). Il faut donc stocker des vecteurs et faire une recherche par similarité.

## 2. Options

| Option | Pour | Contre |
|---|---|---|
| **pgvector dans PostgreSQL** | Une seule base ; transactions, sauvegardes et droits d'accès identiques ; jointure directe avec les règles de visibilité (programme publié, vérifié) ; migrations Alembic | Nécessite une image PostgreSQL avec l'extension ; performances limitées à très grande échelle (sans objet ici) |
| Base vectorielle dédiée (Qdrant, Chroma…) | Fonctions avancées | Un service de plus à exploiter ; règles de visibilité à dupliquer ; risque de fuite de contenu non publié ; cohérence entre deux bases |
| Recherche en mémoire / fichiers | Aucun composant | Pas de persistance fiable, ne passe pas à l'échelle, hors modèle de sécurité |

## 3. Décision recommandée

**Adopter pgvector** : extension `vector`, colonne `vector(N)` dans une table de fragments de documents, index **HNSW** en similarité cosinus. Le filtrage de visibilité se fait dans la même requête SQL que la recherche, donc un fragment non publié ne peut jamais atteindre le LLM.

## 4. Conditions et ordre de mise en œuvre

1. **T10 d'abord** : le modèle d'embedding retenu fixe la dimension N. Ne pas écrire la migration avant.
2. Migration `0012` (ajout seulement, comme les précédentes) : `CREATE EXTENSION IF NOT EXISTS vector`, table de fragments rattachée au document, colonne `vector(N)`, index HNSW.
3. Changer **ensemble** l'image de `compose.yaml` (service `db`) et le service PostgreSQL de `.github/workflows/ci.yml` vers `pgvector/pgvector:pg16`. Sinon la CI ou l'environnement local échoue.
4. Tests : les tests SQLite ne connaissent pas `vector`. Prévoir une garde par dialecte (colonne créée seulement sur PostgreSQL) et vérifier que `alembic check` ne signale aucune dérive. Les tests de recherche s'exécutent avec `TEST_DATABASE_URL` (PostgreSQL).
5. Le modèle ORM et la migration restent identiques (pas de dérive).

## 5. Précautions pour la base existante

L'image actuelle est `postgres:16-alpine`, l'image pgvector est basée sur Debian. Les règles de tri (collation) peuvent différer : un volume de données existant ne se réutilise pas sans précaution.

- Pour les données de démonstration : `scripts/seed_demo.ps1` reconstruit tout, un volume neuf suffit.
- Pour des données réelles : sauvegarde `pg_dump` **avant**, restauration dans la nouvelle image, puis `REINDEX DATABASE`. Ne jamais exécuter `docker compose down -v` sur des données réelles.

## 6. Autres décisions ouvertes (§7) : où elles en sont

| Décision | Proposition | Dépend de |
|---|---|---|
| Stockage des fichiers | Disque (volume Docker) au début, interface abstraite pour passer à MinIO/S3 | Volume de documents |
| Traitement des documents (extraction, découpage, embeddings) | Conteneur worker dédié, hors de l'API | Choix du modèle d'embedding |
| Choix du LLM | Recommandation issue de T10 (principal + secours) | T10 |
| Repli si pgvector inadapté | Recherche textuelle PostgreSQL (`tsvector`) en complément ou en secours | Résultats de T11/T12 |

## 7. Points à valider en relecture A + B

- [ ] pgvector accepté comme choix.
- [ ] Moment de la migration 0012 : après le choix du modèle d'embedding.
- [ ] Changement d'image db (compose + CI) fait dans le même commit.
- [ ] Stockage disque d'abord, puis S3 si besoin.
- [ ] Worker en conteneur séparé.
