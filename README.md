# OrderOps AI Agent

OrderOps est un copilote pour l'**administration des ventes (ADV)** et le
**service après-vente (SAV)**, avec conservation de l'état des conversations.
Il consulte commandes, clients, stocks et livraisons, recherche les procédures
internes et prépare des incidents logistiques. Un superviseur doit approuver
chaque création d'incident avant son exécution.

Le projet est un MVP de démonstration locale : Streamlit pour l'interface,
LangGraph pour l'agent, MCP pour l'accès aux outils et PostgreSQL/pgvector pour
les données et la recherche documentaire. LangSmith permet d'observer les appels,
les temps d'exécution et les coûts.

## Sommaire

- [Démarrage rapide avec Docker](#démarrage-rapide)
- [Démonstration : diagnostic et proposition](#démonstration--diagnostic-et-proposition-daction)
- [Démonstration : validation et création](#démonstration--validation-humaine-et-création-de-lincident)
- [Résultats LangSmith : durées, tokens et coûts](#résultats--temps-de-réponse-et-coût-des-tokens-dans-langsmith)
- [Capacités, outils et rôles](#capacités-outils-et-rôles)
- [Architecture](#architecture)
- [PostgreSQL : données et persistance](#postgresql--données-métier-et-persistance)
- [Docker : services](#docker--services-de-la-démonstration)
- [Mise à jour locale](#mise-à-jour-locale)
- [Développement et tests](#développement-et-tests)
- [Dépannage](#dépannage)
- [Sécurité et limites](#sécurité-et-limites)
- [Structure du projet](#structure)

## Démarrage rapide

Ce parcours lance toute l'application dans Docker. Prérequis : **Docker avec
Compose** et une **clé API Mistral**. Python et les dépendances sont installés dans
l'image ; leur installation sur la machine hôte est réservée au parcours
[développement et tests](#développement-et-tests).

Depuis la racine du dépôt cloné, créer la configuration de la première installation
avec la commande suivante. Si un `.env` existe déjà, le conserver et le compléter
directement sans exécuter cette copie.

```bash
cp .env.example .env
```

Avant de lancer les services, modifier les valeurs suivantes **uniquement dans `.env`** :

| Variable | Valeur à renseigner |
| --- | --- |
| `MISTRAL_API_KEY` | Votre clé API Mistral, nécessaire au chat et aux embeddings. |
| `POSTGRES_PASSWORD` | Remplacer `<POSTGRES_PASSWORD>` par un mot de passe local. Pour ce parcours Compose, utiliser des lettres et des chiffres afin de l'insérer directement dans les URL de connexion. |
| `POSTGRES_PORT` | Garder `5432`, ou choisir un port libre, par exemple `5433`, si une autre base utilise déjà ce port. |

Compose reconstruit `DATABASE_URL` et `CHECKPOINT_DATABASE_URL` à partir des
variables `POSTGRES_*`. Pour exécuter du Python **hors Compose**, remplacer aussi
`<POSTGRES_PASSWORD>` dans ces deux URL et y reporter le port choisi ; conserver
l'hôte `127.0.0.1`. Les détails figurent dans la [configuration](docs/configuration.md).

Valider la configuration et démarrer :

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

Le premier démarrage construit l'image, initialise la base et ingère les procédures.
Les tâches `migrate`, `seed`, `checkpointer-setup` et `ingest` doivent se terminer
avec le code `0` ; les services `postgres`, `mcp`, `api` et `ui` restent actifs.

Ouvrir ensuite l'interface sur <http://127.0.0.1:8501>, la documentation API sur
<http://127.0.0.1:8000/docs> et la santé API sur <http://127.0.0.1:8000/health>.
Choisir **Alex — Opérateur SAV** pour suivre la démonstration ci-dessous.

LangSmith est optionnel et désactivé par défaut ; pgAdmin est optionnel pour
consulter PostgreSQL. L'ingestion et les échanges avec l'agent effectuent des
appels Mistral facturables ; les tests hors ligne utilisent des modèles simulés.

### Windows / WSL 2

Dans Docker Desktop, activer le moteur WSL 2 et l'intégration de la distribution
Ubuntu dans **Settings > Resources > WSL Integration**. Exécuter les commandes du
projet dans le terminal Ubuntu. Cloner le dépôt sous `/home/<user>/projects` pour
conserver les fichiers dans le système de fichiers Linux.

Vérifier l'accès au moteur Docker depuis Ubuntu :

```bash
docker version
docker compose version
```

Si le moteur est inaccessible, démarrer Docker Desktop et vérifier l'intégration
WSL. Pour développer ou lancer les tests hors des conteneurs, installer aussi
Python 3.12 et `uv` dans cette distribution, puis suivre le parcours dédié.

## Démonstration : diagnostic et proposition d'action

Le premier GIF couvre les étapes 1 à 4 du scénario : partir d'une demande client,
consulter les données, examiner une solution et préparer une action soumise à
validation. Ouvrir Streamlit avec **Alex — Opérateur SAV** et LangSmith avec le
traçage activé pour suivre les outils réellement appelés.

1. Demander : « Le client nous relance au sujet de CMD-1042, qu'il n'a toujours pas
   reçue. Peux-tu vérifier son dossier, la commande et le suivi de livraison, puis
   me dire quelle procédure appliquer ? »
2. Examiner la trace LangSmith et les paramètres/résultats des outils appelés,
   par exemple `get_order`, `get_customer`, `get_delivery_status` et
   `search_procedures`. Le choix exact et l'ordre des outils peuvent varier.
3. Demander : « Si une réexpédition est envisagée, avons-nous assez de stock pour
   les produits et les quantités de cette commande ? » L'agent peut vérifier le
   stock avec `check_stock` ; il ne dispose pas d'un outil de réexpédition.
4. Demander : « Prépare un incident pour cette commande en reprenant le retard
   confirmé et les éléments utiles au suivi SAV. » La proposition apparaît en
   attente de validation ; l'incident n'est pas encore créé.

![Démonstration de l'agent SAV : diagnostic, consultation des outils et proposition d'incident](docs/gif/DEMO_AGENT.gif)

## Démonstration : validation humaine et création de l'incident

Le second GIF couvre les étapes 5 à 8 : vérifier l'absence du nouvel incident,
approuver la proposition, puis constater l'enregistrement et sa traçabilité dans
PostgreSQL avec pgAdmin connecté à la base `orderops`.

1. Copier l'`idempotency_key` de la proposition affichée dans Streamlit et
   exécuter la requête A ci-dessous. Pour une clé nouvelle, aucune ligne n'apparaît.
2. Passer au profil **Sam — Superviseur**, ouvrir la demande en attente, examiner
   le motif puis cliquer sur **Approuver**. Cette décision autorise l'exécution
   de `create_incident`.
3. Réexécuter la requête A avec exactement la même clé : le nouvel incident
   apparaît avec sa commande, son motif, son statut et sa date de création.
4. Exécuter la requête B pour retrouver le résultat `created`, le superviseur
   ayant approuvé et l'opérateur à l'origine de la demande. Alex retrouve ensuite
   la décision et la réponse de l'agent dans son chat sauvegardé.

![Validation par le superviseur, création de l'incident et vérification de l'audit dans PostgreSQL](docs/gif/CREATION_INCIDENT.gif)

<details>
<summary>Requêtes SQL : vérifier la création et retrouver son audit</summary>

### Requête A — vérifier l'incident avant et après approbation

Remplacer `CLE_DE_LA_PROPOSITION` par la clé exacte affichée dans Streamlit, en
conservant les quotes SQL. Les données de démonstration contiennent déjà un
incident pour `CMD-1042` : filtrer par la nouvelle clé, et non uniquement par la
commande, permet d'isoler cette création sans supprimer les incidents existants.

```sql
SELECT
    incident_id,
    order_id,
    reason,
    status,
    idempotency_key,
    created_at
FROM incidents
WHERE idempotency_key = 'CLE_DE_LA_PROPOSITION';
```

### Requête B — retrouver les acteurs et le résultat dans l'audit

Utiliser la même clé que dans la requête A.

```sql
SELECT
    a.action,
    a.entity_id AS incident_id,
    a.outcome AS resultat,
    superviseur.name AS superviseur,
    operateur.name AS operateur,
    a.created_at
FROM action_audit AS a
LEFT JOIN users AS superviseur
    ON superviseur.user_id::text = a.actor
LEFT JOIN users AS operateur
    ON operateur.user_id::text = a.details ->> 'proposed_by'
WHERE a.action = 'create_incident'
    AND a.details ->> 'idempotency_key' = 'CLE_DE_LA_PROPOSITION'
ORDER BY a.created_at;
```

</details>

## Résultats : temps de réponse et coût des tokens dans LangSmith

La capture ci-dessous présente **trois exécutions LangGraph** de la démonstration.
Les appels modèle dépliés utilisent `mistral-small-latest`. Ces chiffres sont
relevés dans la trace fournie ; ils ne constituent pas un benchmark sur un grand
nombre de demandes.

| Exécution visible | Durée LangGraph | Tokens affichés | Coût affiché (USD) |
| --- | --- | --- | --- |
| 1 | 11,19 s | 3,946 K | 0,0009 $ |
| 2 | 3,69 s | 4,927 K | 0,0009 $ |
| 3 | 1,75 s | 2,849 K | 0,0005 $ |

Le bandeau **Summary** affiche une latence **P50 de 3,72 s**, **11,72 K tokens**
et un **coût total de 0,0022209 $** pour ces trois exécutions. Les coûts de chaque
ligne sont arrondis dans l'interface : leur somme affichée peut donc différer du
coût total, présenté avec davantage de précision. Le P50 est repris tel qu'affiché
par LangSmith, sans le recalculer à partir des trois durées visibles.

### Comprendre les temps observés

Dans la première exécution, les appels `get_order` et `get_delivery_status`
prennent respectivement **4,18 s** et **4,16 s**, et `search_procedures` prend
**0,72 s**. Les trois appels au modèle affichent **0,95 s**, **0,95 s** et
**3,07 s**. La trace permet ainsi de distinguer le temps passé dans les outils
et dans la génération du modèle ; les durées des sous-appels ne doivent pas être
additionnées sans tenir compte de leur éventuel chevauchement.

Ces durées décrivent les exécutions tracées. Elles ne mesurent pas le délai complet
vécu par l'utilisateur, notamment son temps de lecture et d'approbation. Les GIF
illustrent le parcours ; ils ne servent pas de chronomètre pour ces résultats.

### Comprendre le coût observé

Le nombre de tokens et le coût sont ceux affichés par LangSmith pour les appels
tracés. La capture ne détaille pas la répartition entre tokens d'entrée et de
sortie. Ce montant ne représente pas un coût complet d'exploitation incluant
l'hébergement, l'ingestion documentaire et le temps de validation humaine.

Pour reproduire l'observation, activer `LANGSMITH_TRACING=true` et renseigner les
paramètres LangSmith décrits dans la [configuration](docs/configuration.md), puis
ouvrir les traces de la conversation de démonstration.

![Trace LangSmith : durées des exécutions et des outils, consommation de tokens et coûts](docs/images/LANGSMITH.png)

## Capacités, outils et rôles

Cette section présente les capacités de l'agent, ses six outils et les permissions
des profils de démonstration.

### Ce que peut faire l'agent

- Consulter une commande, son statut, ses lignes et sa date de livraison prévue.
- Consulter la fiche d'un client à partir de son identifiant.
- Lire les informations de livraison enregistrées : statut, transporteur,
  numéro de suivi et date prévue.
- Consulter les quantités physiques, réservées et disponibles d'un produit.
- Rechercher des procédures ADV/SAV et citer leur fichier source et leur version.
- Croiser ces résultats pour expliquer une situation et proposer une action.
- Préparer une création d'incident, puis suspendre son exécution jusqu'à
  l'approbation ou au refus d'un superviseur.
- Reprendre une conversation sauvegardée, y compris une demande en attente.

Les données métier proviennent de PostgreSQL. Le numéro de suivi est une donnée
enregistrée en base : aucun appel à un transporteur n'est effectué. Le choix et
l'ordre des outils dépendent de la demande et des réponses du modèle.

### Outils disponibles

L'agent SAV dispose de six outils : cinq outils métier exposés par le serveur
MCP et un outil de recherche de procédures exécuté dans le processus de l'agent.
Le profil Lecteur dispose des cinq outils de consultation.

| Outil | Paramètres fournis par le modèle | Résultat | Effet métier |
| --- | --- | --- | --- |
| `get_order` | `order_id` | Identifiant client, statut, dates et lignes de commande avec produits, quantités et prix unitaires. | Lecture seule. |
| `get_customer` | `customer_id` | Nom, adresse e-mail et téléphone éventuel du client. | Lecture seule. |
| `get_delivery_status` | `order_id` | Livraison associée, statut, transporteur, suivi et date prévue. | Lecture seule. |
| `check_stock` | `product_id` | Nom du produit et quantités physiques, réservées et disponibles. | Lecture seule. |
| `search_procedures` | `query` | Jusqu'à quatre extraits de procédures, avec source et version. | Lecture seule. |
| `create_incident` | `order_id`, `reason`, `idempotency_key` | Incident et indicateur `already_existed`. | Création après approbation, avec audit en base. |

Les outils métier consultent un identifiant à la fois. Ils ne proposent pas de
recherche globale par nom de client, de liste de toutes les commandes ou d'accès
SQL libre. L'agent peut obtenir l'identifiant client et ceux des produits en
consultant d'abord une commande connue.

`search_procedures` recherche uniquement les documents marqués `approved=true`.
L'ingestion attribue ce marqueur aux documents qui passent le filtre heuristique
de détection d'injection. Ce marqueur ne correspond pas à une validation humaine
documentaire. Le contenu récupéré est présenté au modèle comme une source à citer,
sans autorité pour modifier ses instructions.

Pour `create_incident`, le motif comporte entre 5 et 500 caractères. La clé
d'idempotence identifie une demande : avec la même clé et le même contenu métier,
le service retourne l'incident existant ; avec un contenu différent, il refuse
l'opération. Une commande absente ou annulée ne permet pas de créer un incident.
L'incident et son audit sont enregistrés dans une même transaction.

### Rôles et permissions

Les profils de démonstration sont **Camille — Lecteur**, **Alex — Opérateur SAV**
et **Sam — Superviseur**.

| Action | Lecteur | Opérateur SAV | Superviseur |
| --- | --- | --- | --- |
| Consulter commandes, clients, livraisons et stocks | Oui | Oui | Oui |
| Rechercher les procédures | Oui | Oui | Oui |
| Demander une proposition de création d'incident | Non | Oui | Oui |
| Approuver ou refuser une proposition accessible | Non | Non | Oui |
| Créer, retrouver et supprimer ses propres conversations | Oui | Oui | Oui |
| Envoyer un message dans sa conversation sans action en attente | Oui | Oui | Oui |
| Consulter une demande d'opérateur en attente | Non | Non | Oui |
| Consulter une demande d'opérateur déjà traitée | Non | Non | S'il l'a traitée |
| Écrire dans la conversation d'un autre profil | Non | Non | Non |
| Supprimer la conversation d'un autre profil | Non | Non | Non |

<details>
<summary>Détails des profils et déroulement de la validation humaine</summary>

#### Lecteur

Le modèle peut consulter les données et les procédures. L'outil `create_incident`
est absent de la liste qui lui est fournie. La lecture seule concerne les données
métier : les messages et conversations du lecteur sont néanmoins sauvegardés.

Exemple : « Quel est le statut de CMD-1042 et quelle procédure s'applique au retard ? »

#### Opérateur SAV

L'opérateur peut demander à l'agent de préparer un incident. L'agent affiche la
proposition puis s'interrompt. L'opérateur ne peut ni approuver ni refuser cette
action ; il attend la décision du superviseur.

Exemple : « Vérifie CMD-1042 et prépare un incident si les informations le justifient. »

#### Superviseur

Le superviseur consulte les demandes des opérateurs en attente et les approuve ou
les refuse. Il conserve l'accès aux demandes qu'il a traitées. Ce rôle ne donne
pas accès à toutes les conversations : celles d'un lecteur ou d'un autre
superviseur restent privées dans les règles de l'application.

Le superviseur peut aussi créer une proposition dans sa propre conversation et
l'approuver lui-même. Le MVP n'impose pas deux personnes distinctes pour la
proposition et l'approbation. L'approbation reste une action explicite dans
l'interface ; un message de chat ne remplace pas cette décision.

### Déroulement d'une demande

1. Alex ouvre une conversation et demande l'analyse d'une commande.
2. L'agent consulte les données et les procédures nécessaires à sa réponse.
3. S'il propose `create_incident`, le graphe sauvegarde son état avant l'appel.
   Aucun incident n'est créé à cette étape.
4. Sam ouvre la demande en attente et examine l'action et ses paramètres.
5. Sam approuve ou refuse. L'approbation autorise l'exécution ; le refus reprend
   la conversation sans exécuter cette action.
6. Alex retrouve la décision et la réponse de l'agent dans sa conversation.

Tant qu'une action attend une décision, les nouveaux messages sont bloqués dans
cette conversation. Si la proposition contient plusieurs actions, la décision
porte sur l'ensemble des actions affichées. Une approbation peut encore échouer
si une règle métier ou une erreur technique empêche l'opération.

L'identité, le rôle et l'approbation sont transmis par le serveur et vérifiés
côté API, MCP et service métier. Le modèle fournit uniquement les paramètres
métier de l'outil. Le MCP vérifie également que ces paramètres correspondent à
la proposition enregistrée en attente.

</details>

### Limites fonctionnelles

L'agent ne dispose d'aucun outil pour effectuer un remboursement, une réexpédition,
une annulation de commande, une modification de stock ou un envoi d'e-mail.
Les procédures peuvent décrire ces opérations, mais leur présence dans la base
documentaire n'ajoute pas de capacité d'exécution à l'agent.

Il ne peut pas non plus lister les incidents existants, les modifier ou les
clôturer. `create_incident` est la seule écriture métier exposée au modèle.
La gestion des conversations passe par l'interface et l'API, sans outil de
suppression de conversation accessible au modèle.

La suppression d'un chat efface son historique et ses propositions en attente ;
elle ne supprime pas les incidents déjà créés, l'audit métier ni les traces
externes LangSmith. Les règles de rôle décrites ici ne remplacent pas une
authentification : toute personne ayant accès à la démonstration peut choisir
un autre profil.

Implémentation : [outils MCP](src/orderops/mcp/server.py),
[recherche documentaire](src/orderops/rag/tool.py),
[construction de l'agent](src/orderops/agent/factory.py) et
[permissions](src/orderops/access.py).

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

## PostgreSQL : données métier et persistance

La capture pgAdmin montre les tables de la base `orderops` et le résultat de
`SELECT * FROM deliveries`. La livraison associée à `CMD-1042` porte le statut
`delayed`, ce qui fournit le contexte métier du scénario.

La base contient aussi les commandes, les clients, les stocks, les incidents et
l'audit, ainsi que les conversations, les checkpoints LangGraph et les embeddings
des procédures. Les requêtes de la démonstration précédente servent à vérifier
précisément la création de l'incident et les acteurs impliqués.

![Base orderops dans pgAdmin : tables et livraisons, dont CMD-1042 en retard](docs/images/POSTGRESQL.jpg)

## Docker : services de la démonstration

La capture Docker Desktop montre les quatre services en cours d'exécution :
`ui` pour Streamlit, `api` pour FastAPI, `mcp` pour les outils métier et
`postgres` pour PostgreSQL/pgvector. Compose lance également des tâches
ponctuelles de préparation, notamment les migrations et l'ingestion documentaire.

Les ports visibles correspondent à cette installation locale : `8501` pour
Streamlit, `8000` pour l'API et `5433` côté hôte vers `5432` dans le conteneur
PostgreSQL. Le port hôte de PostgreSQL est configurable avec `POSTGRES_PORT`.

![Services OrderOps en cours d'exécution dans Docker Desktop](docs/images/CONTAINER.jpg)

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

Ce parcours utilise **Python 3.12** et **`uv` sur la machine hôte** pour travailler
sur le code et exécuter les contrôles. Docker reste nécessaire pour les tests
d'intégration PostgreSQL. Depuis la racine du dépôt, installer les dépendances
verrouillées et les hooks de contrôle avant commit :

```bash
uv sync --locked
uv run pre-commit install --install-hooks
```

Pour les commandes Python connectées à la base de démonstration, garder
`DATABASE_URL` et `CHECKPOINT_DATABASE_URL` cohérents avec le mot de passe et le
port de PostgreSQL dans `.env`. Les commandes d'intégration ci-dessous définissent
leurs propres URL pour la base de test.

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

## Dépannage

Commencer par vérifier l'état des services, puis consulter les journaux du
composant en erreur :

```bash
docker compose ps -a
docker compose logs --tail=100 migrate seed checkpointer-setup ingest
docker compose logs --tail=100 postgres mcp api ui
```

| Symptôme | Vérification ou action |
| --- | --- |
| Docker est inaccessible depuis WSL | Démarrer Docker Desktop et vérifier l'intégration de la distribution Ubuntu. |
| Le port PostgreSQL est déjà occupé | Choisir un `POSTGRES_PORT` libre dans `.env`, puis relancer Compose. Reporter aussi ce port dans les URL utilisées hors Compose et dans pgAdmin. |
| L'interface ne démarre pas | Vérifier que les tâches de préparation se sont terminées avec le code `0`, puis consulter les logs de `api` et `ui`. Une tâche ponctuelle arrêtée avec le code `0` est normale. |
| L'ingestion ou le chat échoue avec une erreur Mistral | Vérifier `MISTRAL_API_KEY`, l'accès réseau et les crédits/quota du compte. Après correction, relancer `docker compose up -d --build`. |
| PostgreSQL refuse l'authentification après une modification du mot de passe | Un volume existant conserve le mot de passe initial de la base. Rétablir la valeur correspondante dans `.env`, ou changer le mot de passe du rôle dans PostgreSQL et mettre à jour la configuration. |
| Aucune trace n'apparaît dans LangSmith | Vérifier `LANGSMITH_TRACING=true`, la clé, le projet et l'endpoint régional dans `.env`, puis recréer le service avec `docker compose up -d --no-deps api`. |

Pour arrêter la pile en conservant les données PostgreSQL :

```bash
docker compose down
```

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
docs                      architecture, configuration et médias de démonstration
```
