# Variables d'environnement

Copier `.env.example` vers `.env` et renseigner les clés uniquement dans `.env`.
Ne pas écraser un `.env` existant. Les variables du processus ont priorité sur le
fichier chargé par `Settings`. Les secrets restent sur la machine ; la CI utilise
des modèles simulés et des identifiants PostgreSQL de test.

| Variable | Usage et valeur de démonstration |
| --- | --- |
| `APP_ENV` | `development`. Le démarrage de l'API refuse `production`. |
| `DEMO_MODE` | `true`. Les profils ne constituent pas une authentification. |
| `POSTGRES_DB` | Base Compose : `orderops`. |
| `POSTGRES_USER` | Utilisateur Compose : `orderops`. |
| `POSTGRES_PASSWORD` | Remplacer le placeholder `<POSTGRES_PASSWORD>` dans `.env` avant la première initialisation de la base. |
| `POSTGRES_PORT` | Port local Compose : `5432`. |
| `DATABASE_URL` | URL SQLAlchemy, préfixe `postgresql+psycopg://`. Obligatoire pour Python hors Compose. |
| `CHECKPOINT_DATABASE_URL` | URL Psycopg, préfixe `postgresql://`. Obligatoire pour les checkpoints. |
| `MCP_HOST` | `127.0.0.1` en local ; Compose impose `0.0.0.0` dans le conteneur. |
| `MCP_PORT` | `8001`. |
| `MCP_URL` | `http://127.0.0.1:8001/mcp` ; Compose utilise `http://mcp:8001/mcp`. |
| `MCP_INTERNAL_TOKEN` | Jeton partagé API/MCP. Valeur de démo publique, jamais un secret de production. |
| `MISTRAL_API_KEY` | Secret requis pour le chat, les embeddings et les évaluations live. |
| `MISTRAL_CHAT_MODEL` | `mistral-small-latest`. |
| `MISTRAL_EMBED_MODEL` | `mistral-embed`. |
| `LANGSMITH_TRACING` | `false` par défaut. Activer volontairement l'envoi de traces. |
| `LANGSMITH_API_KEY` | Secret optionnel, nécessaire pour les traces LangSmith. |
| `LANGSMITH_PROJECT` | Projet de traces : `orderops-ai-agent`. |
| `LANGSMITH_ENDPOINT` | Le modèle utilise l'endpoint européen ; le défaut Python est `https://api.smith.langchain.com`. |
| `ORDEROPS_API_URL` | `http://127.0.0.1:8000` ; Compose utilise `http://api:8000`. |
| `IMAGE_TAG` | Option Compose : tag de l'image locale, `dev` par défaut. |
| `POSTGRES_TEST_PORT` | Option du Compose de test : `5433` par défaut. |

Compose reconstruit les deux URL PostgreSQL à partir de `POSTGRES_*`, avec l'hôte
interne `postgres`. Cette construction insère directement le mot de passe dans
les URL : pour le parcours Compose de démonstration, utiliser un mot de passe
composé de lettres et de chiffres.

Hors Compose, remplacer aussi `<POSTGRES_PASSWORD>` dans `DATABASE_URL` et
`CHECKPOINT_DATABASE_URL`. Garder le mot de passe, le port et le nom de base
cohérents dans les deux URL, avec l'hôte `127.0.0.1`. Encoder les caractères
réservés lorsqu'un mot de passe est utilisé dans une URL.

Sur un volume PostgreSQL déjà initialisé, modifier `POSTGRES_PASSWORD` dans `.env`
ne change pas le mot de passe enregistré dans la base. La configuration doit
correspondre au mot de passe du rôle PostgreSQL existant.

Les clés API et le jeton MCP utilisent `SecretStr`. Les URL contenant un mot de passe
sont exclues de la représentation de `Settings`. Cela ne rend pas sûre une impression
explicite de `settings.database_url`, `get_secret_value()`, `model_dump()` ou
`os.environ`. Ne pas publier ces sorties, ni celles de `docker compose config`
sans `--quiet`. La désactivation de LangSmith n'empêche pas les requêtes nécessaires
au fonctionnement du chat et des embeddings d'être envoyées à Mistral.
