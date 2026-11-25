# T3 — Guide d'installation (Windows, PowerShell, Docker Desktop)

Public : un nouveau membre de l'équipe qui part de zéro. Chaque erreur de la section 8 a été rencontrée pour de vrai pendant l'installation de Personne B.

## 1. Prérequis

| Outil | Vérification | Remarque |
|---|---|---|
| Git | `git --version` | |
| Docker Desktop | `docker info` | Doit être **démarré** (« Engine running ») |
| Python 3.12 | `python --version` | Pour les tests et le script d'évaluation |
| Ollama (modèle local) | `ollama --version` | Facultatif pour l'API, nécessaire pour T10 en local |
| Place disque | 15 Go libres conseillés | Images Docker + modèles Ollama (plusieurs Go chacun) |

## 2. Récupérer le projet

```powershell
cd $env:USERPROFILE\Desktop
git clone https://github.com/<organisation>/<depot>.git smartcampus
cd smartcampus
git switch main
git pull origin main
```
Cloner dans un **dossier qui n'existe pas encore** (voir section 8, « destination path already exists »).

## 3. Environnement Python (pour les tests)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```
Si PowerShell refuse d'activer l'environnement : `Set-ExecutionPolicy -Scope Process Bypass`.

## 4. Configurer `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```
Les valeurs `REPLACE_WITH_...` **doivent toutes être remplacées**, sinon l'API refuse de démarrer.

| Variable | Règle |
|---|---|
| `ADMIN_API_KEY` | au moins 32 caractères aléatoires |
| Mot de passe de la base | aléatoire, sans espace |
| Mot de passe du premier administrateur | au moins 12 caractères |

Générer une clé de 40 caractères hexadécimaux :
```powershell
-join ((1..40) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
```
Ne jamais commiter `.env`.

## 5. Démarrer

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8001/api/v1/health/ready
```
Résultat attendu : services `db` et `api` en `healthy`, `retention` en `running`. La documentation interactive est sur http://127.0.0.1:8001/docs.

Ports utilisés (uniquement sur la machine locale) : API **8001**, base de données **55432** (modifiable avec `POSTGRES_HOST_PORT`).

## 6. Données de démonstration

```powershell
.\scripts\seed_demo.ps1
```
Crée un catalogue de démonstration et 5 comptes (`demo.admin|iit|isb|entretien|direction@example.org`). **Les mots de passe sont affichés une seule fois** : les noter. Options : `-Publish` (rend le catalogue visible publiquement), `-NoStaff`, `-Remove` (supprime les données de démo).

## 7. Vérifier que tout fonctionne

```powershell
python -m pytest -q
.\scripts\smoke_t8.ps1
```
Les tests utilisent une base SQLite jetable, jamais votre vraie base. Ne jamais pointer `TEST_DATABASE_URL` vers la base de travail.

Pour tester le chat avec un modèle local :
```powershell
ollama pull qwen3.5:4b
.\scripts\smoke_chat.ps1
```

## 8. Problèmes fréquents

| Message ou symptôme | Cause | Solution |
|---|---|---|
| `failed to connect to the docker API ... dockerDesktopLinuxEngine` | Docker Desktop n'est pas démarré | Lancer Docker Desktop, attendre « Engine running », vérifier `docker info` |
| `fatal: not a git repository` | Commande lancée hors du dossier du projet | `cd` dans le dossier cloné |
| `destination path ... already exists` | Le dossier existe déjà | Cloner dans un autre nom (`smartcampus`) ou supprimer le dossier vide |
| `Rename-Item` refusé (dossier verrouillé) | Un programme ou un terminal utilise le dossier | Fermer les terminaux et l'éditeur, ou cloner sous un autre nom |
| Conteneur `api` : `dependency api failed to start`, logs avec `REPLACE_WITH` | `.env` contient encore des valeurs d'exemple | Remplacer toutes les valeurs, puis `docker compose up -d --force-recreate api` |
| `ADMIN_API_KEY` refusée | Moins de 32 caractères | Régénérer une clé de 40 caractères (section 4) |
| Mot de passe administrateur refusé | Moins de 12 caractères | Allonger le mot de passe |
| `port is already allocated` (55432, 8001) | Un autre programme ou conteneur utilise le port | `docker ps` ; arrêter l'autre conteneur ou changer `POSTGRES_HOST_PORT` |
| `pip ... ReadTimeout` pendant `docker build` | Réseau lent | Relancer simplement la commande |
| `No module named app.db.seed_demo` | Image `api` ancienne | `docker compose up -d --build` |
| Tests : `authentication failed` sur la base | `DATABASE_URL`/`TEST_DATABASE_URL` défini dans la session | `Remove-Item Env:DATABASE_URL, Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue` |
| `ollama` : terme non reconnu | Installation incomplète ou PATH absent | Terminer l'installateur, rouvrir PowerShell ; sinon `$env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"` |
| Installation d'Ollama « annulée par l'utilisateur » | Fenêtre d'autorisation fermée | Relancer l'installateur et accepter |
| Réponses de chat très lentes ou erreurs de délai | Modèle local lourd sans GPU | Augmenter `LLM_TIMEOUT_SECONDS` dans `.env` (max 300) |
| PowerShell : tableaux JSON vides ou à un seul élément mal comptés | Particularité de PowerShell 5.1 | Compter sur le texte JSON brut, comme `smoke_t8.ps1` |

## 9. Règles à ne jamais enfreindre

- Jamais `docker compose down -v` sur des données réelles (il supprime la base).
- Jamais de clé d'API, de mot de passe ou de `.env` dans git.
- Toujours une sauvegarde avant une migration sur des données réelles.

## 10. Arrêter, redémarrer, repartir de zéro

```powershell
docker compose stop            # arrêter sans rien perdre
docker compose up -d           # redémarrer
docker compose down            # supprimer les conteneurs, garder les données
docker compose down -v         # DANGER : supprime aussi la base (démo seulement)
```

## 11. À compléter avec T13 et pgvector

Quand le frontend (T13) sera ajouté au compose et que l'image `db` passera à `pgvector/pgvector:pg16`, ajouter ici : son port, sa commande de démarrage, et la procédure de sauvegarde et de restauration (voir `docs/DECISION_PGVECTOR.md`). Valider ce guide en l'appliquant sur une **machine propre**, sans aide.
