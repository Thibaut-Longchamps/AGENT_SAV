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

- [Installation - choisir son parcours](#installation---choisir-son-parcours)
- [Démonstration : diagnostic et proposition](#démonstration--diagnostic-et-proposition-daction)
- [Démonstration : validation et création](#démonstration--validation-humaine-et-création-de-lincident)
- [Résultats LangSmith : durées, tokens et coûts](#résultats--temps-de-réponse-et-coût-des-tokens-dans-langsmith)
- [Capacités, outils et rôles](#capacités-outils-et-rôles)
- [Architecture](#architecture)
- [PostgreSQL : données et persistance](#postgresql--données-métier-et-persistance)
- [Docker : services](#docker--services-de-la-démonstration)
- [Mise à jour locale](#mise-à-jour-locale)
- [Installation de développement et tests](#installation-de-développement-et-tests)
- [Dépannage](#dépannage)
- [Sécurité et limites](#sécurité-et-limites)
- [Structure du projet](#structure)

## Installation - choisir son parcours

Deux parcours sont proposés selon votre objectif :

| Objectif | Parcours | Prérequis principaux |
| --- | --- | --- |
| Tester rapidement l'application et reproduire la démonstration | **Parcours 1 - Installation pour tester** | Docker avec Compose + clé API Mistral |
| Modifier le code et exécuter les contrôles/tests | [**Parcours 2 - Installation de développement**](#installation-de-développement-et-tests) | Python 3.12 + `uv` + Docker |

Si vous souhaitez uniquement découvrir OrderOps, suivez **le parcours 1 uniquement** :
Python et les dépendances du projet n'ont pas besoin d'être installés sur la machine hôte.

### Parcours 1 - Installation pour tester

Ce parcours lance l'ensemble de l'application avec Docker : PostgreSQL/pgvector,
le serveur MCP, l'API FastAPI, l'interface Streamlit ainsi que les tâches de préparation
de la base et d'ingestion documentaire.

#### 1. Vérifier les prérequis

Vous avez besoin de :
- **Docker avec Docker Compose** ;
- une **clé API Mistral**, utilisée par le chat et les embeddings.
Vous n'avez pas besoin d'installer Python pour ce parcours : Python et les dépendances
sont déjà présents dans l'image Docker.

#### Windows / WSL 2

Sous Windows, utiliser Docker Desktop avec le moteur WSL 2 et activer l'intégration
de la distribution Ubuntu dans **Settings > Resources > WSL Integration**.
Exécuter ensuite les commandes du projet depuis le terminal Ubuntu. Pour de meilleures
performances, cloner le dépôt dans le système de fichiers Linux, par exemple sous
`/home/<user>/projects`.
Vérifier que Docker est accessible depuis Ubuntu :

```bash
docker version
docker compose version
```

Les deux commandes doivent afficher les informations de version sans erreur. Si le
moteur Docker est inaccessible, démarrer Docker Desktop et vérifier l'intégration WSL.

#### 2. Créer le fichier de configuration

Après avoir cloné le dépôt, se placer à sa racine.
Lors de la première installation :

```bash
cp .env.example .env
```

Si un `.env` existe déjà, **ne pas le remplacer** : le conserver et compléter
directement les valeurs nécessaires.

#### 3. Configurer `.env`

Renseigner au minimum les variables suivantes :

| Variable | Valeur à renseigner |
| --- | --- |
| `MISTRAL_API_KEY` | Votre clé API Mistral, nécessaire au chat et aux embeddings. |
| `POSTGRES_PASSWORD` | Remplacer `<POSTGRES_PASSWORD>` par un mot de passe local. Pour ce parcours Compose, utiliser de préférence des lettres et des chiffres afin de l'insérer directement dans les URL de connexion. |
| `POSTGRES_PORT` | Garder `5432`, ou choisir un port libre, par exemple `5433`, si une autre base utilise déjà ce port. |

Pour ce parcours Docker, Compose reconstruit automatiquement `DATABASE_URL` et
`CHECKPOINT_DATABASE_URL` à partir des variables `POSTGRES_*`. Il n'est donc pas
nécessaire de modifier manuellement ces deux URL pour simplement lancer la démonstration.
Les détails complets figurent dans la [configuration](docs/configuration.md).

#### 4. Vérifier la configuration

Avant de démarrer les services :

```bash
docker compose config --quiet
```

Si la commande ne renvoie pas d'erreur, la configuration Compose est valide.

#### 5. Démarrer OrderOps

Lancer l'ensemble de l'application :

```bash
docker compose up -d --build
```

Puis vérifier l'état des conteneurs et des tâches de préparation :

```bash
docker compose ps -a
```

Lors du premier démarrage, Docker construit l'image, initialise la base de données,
charge les données de démonstration, configure les checkpoints et ingère les procédures.
Les tâches ponctuelles `migrate`, `seed`, `checkpointer-setup` et `ingest` doivent se
terminer avec le code `0`. Il est normal qu'elles apparaissent ensuite comme arrêtées :
leur travail est terminé.
Les services `postgres`, `mcp`, `api` et `ui` doivent rester actifs.

#### 6. Ouvrir l'application

Une fois les services démarrés :
- interface Streamlit : <http://127.0.0.1:8501> ;
- documentation FastAPI : <http://127.0.0.1:8000/docs> ;
- état de santé de l'API : <http://127.0.0.1:8000/health>.
Pour reproduire la démonstration présentée ci-dessous, sélectionner
**Alex - Opérateur SAV** dans Streamlit.

#### 7. Outils facultatifs

**LangSmith** est optionnel et désactivé par défaut. L'activer uniquement pour
observer les exécutions LangGraph, les appels aux outils et au modèle, les temps
d'exécution, les tokens et les coûts. La configuration correspondante est décrite
dans `docs/configuration.md`.
**pgAdmin** n'est pas inclus dans Compose. L'installer séparément uniquement
si vous souhaitez reproduire les vérifications SQL du second GIF. Le connecter à
`127.0.0.1`, au port défini par `POSTGRES_PORT`, avec la base, l'utilisateur et le
mot de passe configurés dans `.env`.
L'ingestion initiale et les échanges avec l'agent effectuent des appels Mistral
potentiellement facturables selon votre compte et votre quota.

#### 8. Arrêter l'application

Pour arrêter OrderOps tout en conservant les données PostgreSQL :

```bash
docker compose down
```

Les données du volume PostgreSQL sont conservées pour le prochain démarrage.

## Démonstration : diagnostic et proposition d'action

Dans le premier GIF, **Alex - Opérateur SAV** échange avec l'agent au sujet de
la commande `CMD-1042`. La conversation progresse du diagnostic à la préparation
d'un incident :
- **Diagnostic du retard** : l'opérateur demande de vérifier la commande et la
  livraison, puis d'identifier la procédure applicable. L'agent consulte les
  données avec `get_order` et `get_delivery_status`, puis recherche les procédures
  avec `search_procedures` pour expliquer la situation.
- **Vérification du stock** : l'opérateur demande si les quantités disponibles
  permettraient une réexpédition. L'agent utilise `check_stock` pour les produits
  concernés et présente leur disponibilité. La réexpédition reste une option à
  traiter par le SAV ; aucun outil ne permet à l'agent de l'exécuter.
- **Préparation de l'incident** : l'opérateur demande un incident fondé sur le
  retard constaté. L'agent prépare `create_incident` et s'interrompt en attente
  d'une validation humaine. À ce stade, l'incident proposé n'est pas encore créé.
La fin du GIF montre dans LangSmith les trois exécutions de cette même
conversation, leurs appels d'outils et leurs résultats. Le choix et l'ordre des
outils peuvent varier lors d'une nouvelle exécution.

![Démonstration de l'agent SAV : diagnostic, consultation des outils et proposition d'incident](docs/gif/DEMO_AGENT.gif)

## Démonstration : validation humaine et création de l'incident

Le second GIF reprend la proposition en attente dans Streamlit et montre son
approbation, puis la vérification de son enregistrement dans PostgreSQL :
- **Vérification avant approbation** : la requête A ci-dessous recherche l'incident
  à partir de l'`idempotency_key` affichée dans la proposition. Pour une clé
  nouvelle, aucune ligne n'est présente dans la base `orderops`.
- **Décision du superviseur** : **Sam - Superviseur** ouvre la demande, examine le
  motif et les paramètres, puis clique sur **Approuver**. Cette décision autorise
  la reprise de l'agent et l'exécution de `create_incident`.
- **Vérification après approbation** : la même requête A, avec la même clé,
  retrouve l'incident créé, sa commande, son motif, son statut et sa date.
- **Traçabilité de l'action** : la requête B retrouve l'audit avec le résultat
  `created`, le superviseur ayant approuvé et l'opérateur à l'origine de la
  proposition.
Les vérifications SQL sont effectuées manuellement dans pgAdmin ; l'agent dispose
d'outils métier bornés et ne peut pas exécuter ces requêtes librement.

![Validation par le superviseur, création de l'incident et vérification de l'audit dans PostgreSQL](docs/gif/CREATION_INCIDENT.gif)

<details>
<summary>Requêtes SQL : vérifier la création et retrouver son audit</summary>

### Requête A - vérifier l'incident avant et après approbation

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

### Requête B - retrouver les acteurs et le résultat dans l'audit

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

Les mesures ci-dessous correspondent au **thread du premier GIF (`DEMO_AGENT.gif`)**,
c'est-à-dire à une seule conversation comprenant les trois demandes de l'opérateur.
Chaque demande déclenche une exécution LangGraph, qui peut contenir plusieurs
appels au modèle et aux outils. Les appels modèle dépliés utilisent
`mistral-small-latest`.

| Demande dans le premier GIF | Durée LangGraph | Tokens affichés | Coût affiché (USD) |
| --- | --- | --- | --- |
| Diagnostic de la commande et du retard | 11,19 s | 3,946 K | 0,0009 $ |
| Vérification des stocks pour une éventuelle réexpédition | 3,69 s | 4,927 K | 0,0009 $ |
| Préparation de l'incident jusqu'à l'attente de validation | 1,75 s | 2,849 K | 0,0005 $ |

La validation et la création effective de l'incident, montrées dans le second GIF,
sont hors du périmètre de ces trois mesures. Cet exemple décrit une conversation
observée ; il ne constitue pas un benchmark sur un grand nombre de demandes.
Le bandeau **Summary** affiche une latence **P50 de 3,72 s**, **11,72 K tokens**
et un **coût total de 0,0022209 $** pour ces trois exécutions. Les coûts de chaque
ligne sont arrondis dans l'interface : leur somme affichée peut donc différer du
coût total, présenté avec davantage de précision. `K` signifie mille tokens.
Le P50 est reproduit tel qu'affiché dans le bandeau. La médiane des trois durées
visibles dans le tableau est **3,69 s** ; la capture seule ne permet pas
d'expliquer l'écart avec les **3,72 s** du bandeau. Un export des traces serait
nécessaire pour vérifier cet agrégat.

### Comprendre les temps observés

Dans la première exécution, les appels `get_order` et `get_delivery_status`
prennent respectivement **4,18 s** et **4,16 s**, et `search_procedures` prend
**0,72 s**. Les trois appels au modèle affichent **0,95 s**, **0,95 s** et
**3,07 s**. La trace permet ainsi de distinguer le temps passé dans les outils
et dans la génération du modèle ; les durées des sous-appels ne doivent pas être
additionnées sans tenir compte de leur éventuel chevauchement.
Ces durées mesurent les trois exécutions de l'agent dans le premier GIF, jusqu'à
la proposition en attente. Elles n'incluent pas les pauses de l'opérateur entre
ses demandes, le temps d'approbation du superviseur ni l'exécution après reprise
dans le second GIF. Les GIF illustrent le parcours ; ils ne servent pas de
chronomètre pour ces résultats.

### Comprendre le coût observé

Le nombre de tokens et le coût sont ceux affichés par LangSmith pour les appels
tracés dans le thread du premier GIF, jusqu'à l'attente de validation. Le total
de **0,0022209 $** correspond à ces trois demandes ensemble. La capture ne
détaille pas la répartition entre tokens d'entrée et de sortie. Ce montant ne
représente pas un coût complet d'exploitation incluant l'hébergement, l'ingestion
documentaire et le temps de validation humaine.
Pour reproduire l'observation, activer `LANGSMITH_TRACING=true` et renseigner les
paramètres LangSmith décrits dans la [configuration](docs/configuration.md), puis
ouvrir le thread correspondant aux trois demandes du premier GIF. Les durées et
les coûts peuvent varier d'une exécution à l'autre.

![Thread du premier GIF dans LangSmith : trois exécutions, durées, tokens et coûts](docs/images/LANGSMITH.png)

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

Les profils de démonstration sont **Camille - Lecteur**, **Alex - Opérateur SAV**
et **Sam - Superviseur**.

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

#### Déroulement d'une demande

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
`delayed`, ce qui explique le diagnostic de retard présenté dans le premier GIF.
La base contient aussi les commandes, les clients, les stocks, les incidents et
l'audit, ainsi que les conversations, les checkpoints LangGraph et les embeddings
des procédures. Les [requêtes associées au second GIF](#démonstration--validation-humaine-et-création-de-lincident)
servent à vérifier précisément la création de l'incident et les acteurs impliqués.

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

## Installation de développement et tests

**Parcours 2 - Installation de développement** est destiné aux personnes qui
souhaitent modifier le code, utiliser les outils de qualité et exécuter les différents
niveaux de tests du projet.
Contrairement au parcours de démonstration, Python et les dépendances du projet sont
ici installés **sur la machine hôte**. Docker reste nécessaire pour les tests
d'intégration PostgreSQL et peut également être utilisé pour lancer l'application complète.

### 1. Vérifier les prérequis

Installer :
- **Python 3.12** ;
- **`uv`** ;
- **Docker avec Docker Compose**.
Sous Windows, utiliser de préférence Python, `uv`, Git et Docker depuis la même
distribution WSL 2 / Ubuntu.
Vérifier l'environnement :

```bash
python --version
uv --version
docker version
docker compose version
```

Python doit être disponible en version 3.12.

### 2. Installer les dépendances Python

Depuis la racine du dépôt, installer les dépendances verrouillées :

```bash
uv sync --locked
```

Cette commande recrée l'environnement Python attendu à partir du fichier de verrouillage
du projet.

### 3. Installer les contrôles `pre-commit`

Installer les hooks Git :

```bash
uv run pre-commit install --install-hooks
```

Les hooks contrôlent notamment les fichiers ajoutés, les sorties des notebooks et les
secrets avec Gitleaks. Le fichier `.env` personnel doit rester local ; seul
`.env.example`, sans clé API réelle, est versionné.
Après un `git add`, tous les hooks peuvent aussi être exécutés manuellement :

```bash
uv run pre-commit run --all-files
```

### 4. Configurer `.env` selon le besoin

Les tests hors ligne décrits à l'étape suivante n'appellent ni Mistral ni LangSmith.
Une clé API n'est donc pas nécessaire pour travailler sur ces tests.
En revanche, pour exécuter du Python connecté à la base de démonstration, garder
`DATABASE_URL` et `CHECKPOINT_DATABASE_URL` cohérents avec le mot de passe et le
port PostgreSQL définis dans `.env`, en conservant l'hôte `127.0.0.1`.
Si aucun fichier `.env` n'existe encore :

```bash
cp .env.example .env
```

### 5. Lancer les contrôles et tests hors ligne

Ces commandes n'effectuent aucun appel à Mistral ni à LangSmith :

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/agent -m "not live" -q
```

Elles vérifient respectivement le formatage, le linting, le typage et les tests
unitaires/agent hors scénarios live.

### 6. Lancer les tests d'intégration PostgreSQL

Les tests d'intégration utilisent une base PostgreSQL dédiée afin de ne pas modifier
la base de démonstration.
Démarrer cette base sur le port de test `5544` :

```bash
POSTGRES_TEST_PORT=5544 docker compose -f compose.test.yaml up -d
```

Appliquer les migrations :

```bash
DATABASE_URL=postgresql+psycopg://orderops_test:orderops_test@127.0.0.1:5544/orderops_test \
CHECKPOINT_DATABASE_URL=postgresql://orderops_test:orderops_test@127.0.0.1:5544/orderops_test?sslmode=disable \
uv run alembic upgrade head
```

Puis exécuter les tests d'intégration :

```bash
DATABASE_URL=postgresql+psycopg://orderops_test:orderops_test@127.0.0.1:5544/orderops_test \
CHECKPOINT_DATABASE_URL=postgresql://orderops_test:orderops_test@127.0.0.1:5544/orderops_test?sslmode=disable \
uv run pytest tests/integration -q
```

### 7. Facultatif - lancer les évaluations avec le vrai agent

Les scénarios live définis dans `evals/cases.json` traversent le vrai pipeline
LangGraph/MCP/RAG/Mistral. Ils vérifient les tools appelés et les interruptions HITL
sans approuver les écritures.
Ils nécessitent une clé Mistral valide dans `.env` :

```bash
docker compose --profile evals run --rm --build evals
```

La commande retourne le code `0` si tous les scénarios réussissent et `1` sinon.
Si `LANGSMITH_TRACING=true`, chaque scénario apparaît également dans le projet
LangSmith configuré.

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
