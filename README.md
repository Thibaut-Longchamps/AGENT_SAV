# OrderOps AI Agent

OrderOps est un copilote ADV/SAV stateful. Il consulte commandes, clients, stocks et
livraisons via MCP, recherche les procédures approuvées avec PostgreSQL/pgvector, puis
suspend toute écriture sensible jusqu'à la décision d'un superviseur.

Le [guide de l'agent, des outils et des rôles](docs/agent-outils-et-roles.md)
présente ses capacités, les six outils disponibles et les permissions des profils
Lecteur, Opérateur SAV et Superviseur.

## Architecture

[![Architecture OrderOps : outils MCP, RAG et validation humaine](docs/images/architecture.svg)](docs/images/architecture.svg)

Le serveur MCP expose quatre outils de consultation et `create_incident`, la seule
écriture métier accessible au modèle. `search_procedures` est un sixième outil,
exécuté côté agent pour le RAG. Le profil Lecteur ne reçoit pas `create_incident`.

Le superviseur approuve ou refuse dans Streamlit. PostgreSQL conserve l'état de la
conversation pendant la pause ; l'approbation autorise la reprise de l'outil d'écriture.
Le MCP contrôle l'identité, les permissions et la correspondance avec la proposition.
La création utilise une clé d'idempotence, un hash du payload et une transaction commune
pour l'incident et son audit. Les traces LangSmith sont optionnelles.

**[Voir l’architecture détaillée](docs/architecture.md)** : classes métier,
composants et séquence de validation humaine.

## Démarrage rapide

Prérequis : Python 3.12, `uv`, Docker avec Compose et une clé API Mistral.
LangSmith est optionnel pour les traces. pgAdmin est optionnel pour visualiser les
tables PostgreSQL.

```bash
cp .env.example .env
# Renseigner MISTRAL_API_KEY. Les identifiants PostgreSQL fournis sont locaux au MVP.
uv sync --locked
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

Ouvrir ensuite l'UI sur <http://127.0.0.1:8501>, la documentation API sur
<http://127.0.0.1:8000/docs> et la santé API sur <http://127.0.0.1:8000/health>.

Les variables sont détaillées dans [Configuration](docs/configuration.md).
LangSmith est optionnel et désactivé par défaut. Le démarrage et l'ingestion RAG
effectuent des appels Mistral facturables ; les tests hors ligne utilisent des modèles simulés.

### Windows / WSL 2

Dans Docker Desktop, activer le moteur WSL 2 et l'intégration de la distribution
Ubuntu dans **Settings > Resources > WSL Integration**. Exécuter les commandes du
projet dans le terminal Ubuntu, avec Python et `uv` installés dans cette distribution.
Cloner le dépôt sous `/home/<user>/projects` pour conserver le projet et son
environnement Python dans le système de fichiers Linux.

Vérifier l'accès au moteur Docker depuis Ubuntu :

```bash
docker version
docker compose version
```

Si le moteur est inaccessible, démarrer Docker Desktop et vérifier l'intégration
WSL avant de lancer la pile. Un clone utilise le `pyproject.toml` et le `uv.lock`
existants ; l'installation des dépendances se fait avec `uv sync --locked`.

## Démonstration et conversations

Avec **Alex — Opérateur SAV**, demander : « Le client ACME indique que CMD-1042 n'est
toujours pas arrivée. Vérifie et prépare l'action appropriée. » Si l'agent propose
un incident, ouvrir la demande avec **Sam — Superviseur** pour l'approuver ou la
refuser. Alex retrouve le résultat dans son chat sauvegardé.

Le [guide de l'agent](docs/agent-outils-et-roles.md) détaille les outils et les
permissions, y compris le profil **Camille — Lecteur**.

## Mise à jour locale

Pour mettre à jour une installation existante **sans relancer l'ingestion Mistral** :

```bash
docker compose build migrate
docker compose run --rm migrate
docker compose up -d --no-deps postgres mcp api ui
```

La tâche de migration attend PostgreSQL et n'appelle pas Mistral. Les services
API et MCP utilisent ensuite l'image reconstruite. Les détails de persistance et
de migration des conversations figurent dans l'[architecture](docs/architecture.md).

## Développement et tests

Sur chaque nouveau clone, installer les hooks de contrôle avant commit :

```bash
uv run pre-commit install --install-hooks
```

Les hooks vérifient les fichiers ajoutés, les sorties des notebooks et les secrets
avec Gitleaks. Après avoir ajouté les changements à l'index avec `git add`, ils
peuvent aussi être lancés manuellement avec `uv run pre-commit run --all-files`.
Le `.env` personnel reste local ; seul `.env.example`, sans clé API, est versionné.

Les tests hors ligne n'appellent ni Mistral ni LangSmith :

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/agent -m "not live" -q
```

Pour les intégrations PostgreSQL :

```bash
POSTGRES_TEST_PORT=5544 docker compose -f compose.test.yaml up -d
DATABASE_URL=postgresql+psycopg://orderops_test:orderops_test@127.0.0.1:5544/orderops_test \
CHECKPOINT_DATABASE_URL=postgresql://orderops_test:orderops_test@127.0.0.1:5544/orderops_test?sslmode=disable \
uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://orderops_test:orderops_test@127.0.0.1:5544/orderops_test \
CHECKPOINT_DATABASE_URL=postgresql://orderops_test:orderops_test@127.0.0.1:5544/orderops_test?sslmode=disable \
uv run pytest tests/integration -q
```

Les scénarios live de `evals/cases.json` traversent le vrai pipeline
LangGraph/MCP/RAG/Mistral. Ils vérifient les tools appelés et les interruptions HITL sans
approuver les écritures. Ils nécessitent une clé Mistral dans `.env` :

```bash
docker compose --profile evals run --rm --build evals
```

La commande retourne le code `0` si tous les scénarios réussissent et `1` sinon. Si
`LANGSMITH_TRACING=true`, chaque scénario apparaît aussi dans le projet LangSmith configuré.

## Sécurité et limites

Les documents RAG sont présentés au modèle comme du contenu non fiable. Une détection
heuristique met en quarantaine le document d'injection de démonstration, tandis que les
tools bornés et le HITL constituent les contrôles déterministes. Le MVP n'a pas encore
d'authentification réelle : ses profils sont des identités de démonstration. Il utilise un
verrou en mémoire par thread avec un seul worker API et ne fournit pas de coordination
distribuée. Le token interne MCP par défaut est public et réservé au mode local ; choisir
un autre token ne transforme pas le sélecteur de profils en authentification. Le démarrage
de l'API est refusé avec `APP_ENV=production` ou `DEMO_MODE=false` tant qu'une vraie
authentification n'est pas implémentée.

## Structure

```text
src/orderops/domain       modèles et règles métier
src/orderops/repositories SQLAlchemy et unité de travail
src/orderops/services     orchestration transactionnelle
src/orderops/mcp          serveur de tools métier
src/orderops/rag          sécurité, ingestion et recherche
src/orderops/agent        agent et middleware HITL
src/orderops/api          API FastAPI
src/orderops/ui           interface Streamlit
tests                     unitaires, agent et intégration PostgreSQL
notebooks                 checkpoints pédagogiques
docs                      capacités de l'agent, architecture et configuration
```
