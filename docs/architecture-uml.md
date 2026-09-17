# Architecture et UML du MVP

Ce document décrit les composants du MVP local, leurs interactions et la persistance
des conversations. Les diagrammes Mermaid sont lisibles directement dans GitHub.
Les capacités et permissions sont détaillées dans le [guide de l'agent](agent-outils-et-roles.md).

## Composants

```mermaid
flowchart LR
    User[Utilisateur local] --> UI[Streamlit]
    UI -->|HTTP| API[FastAPI]
    API --> Agent[Agent LangChain / LangGraph]
    API --> Conversations[ConversationStore]
    Conversations --> DB[(PostgreSQL)]
    Agent -->|Chat| Mistral[API Mistral]
    Agent -->|search_procedures| RAG[RAG]
    RAG -->|Embeddings| Mistral
    RAG --> Vector[(pgvector)]
    Agent -->|Streamable HTTP| MCP[Serveur MCP]
    MCP --> Auth[Contrôle des permissions]
    Auth --> Service[OrderOpsService]
    Service --> UOW[SqlAlchemyUnitOfWork]
    UOW --> Repos[Repositories SQLAlchemy]
    Repos --> DB
    Agent --> Checkpoint[AsyncPostgresSaver]
    Checkpoint --> DB
    Agent -. Traces optionnelles .-> LangSmith[LangSmith]
```

PostgreSQL héberge les tables métier, les conversations, les checkpoints et les
vecteurs. Les checkpoints LangGraph et les tables pgvector sont gérés par leurs
bibliothèques respectives. Le service MCP propose quatre lectures et une écriture :
`get_order`, `get_customer`, `get_delivery_status`, `check_stock`, `create_incident`.

## Classes métier et orchestration

Vue simplifiée des modèles de `src/orderops/domain/models.py`, du service et de son
unité de travail. Les associations représentent les identifiants métier ; elles
ne signifient pas que chaque modèle Pydantic charge des objets liés.

```mermaid
classDiagram
    class Customer {
        +str customer_id
        +str name
        +str email
    }
    class Order {
        +str order_id
        +str customer_id
        +OrderStatus status
        +datetime created_at
    }
    class OrderItem {
        +str product_id
        +int quantity
        +Decimal unit_price
    }
    class Delivery {
        +str delivery_id
        +str order_id
        +DeliveryStatus status
    }
    class ProductStock {
        +str product_id
        +int on_hand_quantity
        +int reserved_quantity
        +int quantity_available
    }
    class Incident {
        +str incident_id
        +str order_id
        +str reason
        +IncidentStatus status
        +str idempotency_key
    }
    class CreateIncidentCommand {
        +str order_id
        +str reason
        +str idempotency_key
        +request_hash() str
    }
    class IncidentCreationResult {
        +Incident incident
        +bool already_existed
    }
    class OrderOpsService {
        +get_order(order_id) Order
        +get_customer(customer_id) Customer
        +get_delivery_status(order_id) Delivery
        +check_stock(product_id) ProductStock
        +create_authorized_incident(command, user, proposed_by) IncidentCreationResult
    }
    class UnitOfWork {
        <<interface>>
        +orders
        +customers
        +inventory
        +deliveries
        +incidents
        +audits
        +commit()
    }
    class SqlAlchemyUnitOfWork {
        +session
        +commit()
    }
    Customer "1" --> "0..*" Order : client
    Order "1" *-- "0..*" OrderItem : lignes
    Order "1" --> "0..1" Delivery : livraison
    Order "1" --> "0..*" Incident : incidents
    OrderItem ..> ProductStock : product_id
    OrderOpsService --> UnitOfWork : transaction
    UnitOfWork <|.. SqlAlchemyUnitOfWork
    OrderOpsService ..> CreateIncidentCommand
    OrderOpsService ..> IncidentCreationResult
    IncidentCreationResult --> Incident
```

Les modèles métier sont immuables. La base impose une seule livraison par commande,
un stock réservé inférieur ou égal au stock physique, ainsi qu'une clé d'idempotence
unique pour les incidents. Le hash du payload distingue une répétition valide d'un
conflit. L'incident et son audit sont écrits dans une même transaction.

## Séquence : demande et validation d'un incident

```mermaid
sequenceDiagram
    actor Operator as Opérateur SAV
    participant UI as Streamlit
    participant API as FastAPI
    participant Agent as LangGraph
    participant MCP as MCP / Service métier
    participant DB as PostgreSQL
    actor Supervisor as Superviseur
    Operator->>UI: Demander une vérification de commande
    UI->>API: POST /chat (thread_id, message)
    API->>DB: Vérifier identité de démo et accès à la conversation
    API->>Agent: ainvoke(message)
    Agent->>MCP: Lectures commande, client, livraison, stock
    MCP->>DB: Requêtes bornées
    DB-->>Agent: Résultats métier via MCP
    Note over Agent,DB: Recherche RAG via Mistral Embeddings et pgvector
    Agent->>Agent: Proposer create_incident
    Agent->>DB: Sauvegarder le checkpoint avant écriture
    Agent-->>API: Interruption HITL
    API->>DB: Sauvegarder les actions en attente
    API-->>UI: approval_required
    Supervisor->>UI: Ouvrir la demande et décider
    UI->>API: POST /threads/{thread_id}/decision
    API->>DB: Vérifier rôle superviseur et accès
    alt Approbation
        API->>Agent: Command(resume=approve)
        Agent->>MCP: create_incident avec contexte approuvé
        MCP->>DB: Vérifier permissions, idempotence et payload
        MCP->>DB: Incident et audit dans une transaction
        DB-->>Agent: Incident créé ou déjà existant, via MCP
    else Refus
        API->>Agent: Command(resume=reject)
        Note over Agent,MCP: create_incident n'est pas exécuté
    end
    Agent->>DB: Sauvegarder le checkpoint
    Agent-->>API: Réponse finale
    API->>DB: Mettre à jour conversation et superviseur
    API-->>UI: Résultat
```

Les identités Lecteur, Opérateur et Superviseur sont simulées, sans authentification.
Un utilisateur actif possède au plus un rôle dans le schéma actuel. Une conversation
a un propriétaire et éventuellement un superviseur ayant traité la demande.
Le verrou par conversation reste en mémoire dans un unique worker API.

## Identité et contrôle des appels

Streamlit transmet l'identifiant du profil dans l'en-tête `X-Demo-User-Id`.
L'API relit en PostgreSQL l'état actif, le rôle et les droits d'accès à la
conversation. Le rôle n'est pas accepté dans le corps JSON de la requête.

L'agent transmet au MCP le jeton interne, l'identité, le thread et la décision
fournis par le serveur. Ces informations ne figurent pas dans les arguments
métier produits par le modèle. `MCP_INTERNAL_TOKEN` doit avoir la même valeur
dans l'API et le MCP ; sa valeur publique de démonstration ne fournit pas
d'authentification utilisateur.

Avant une création, le MCP vérifie le rôle du superviseur, la décision serveur
et la correspondance des arguments avec la proposition en attente. Le service
métier vérifie ensuite le rôle et les contraintes métier dans la transaction.
L'audit enregistre le superviseur dans `action_audit.actor` et le propriétaire
de la conversation dans `action_audit.details.proposed_by`.

## Persistance des conversations

| Stockage PostgreSQL | Contenu |
| --- | --- |
| `users`, `roles`, `user_roles` | Profils simulés, état actif et permissions. |
| `conversations` | UUID du thread, propriétaire, titre, statut, actions en attente, superviseur ayant traité la demande et dates. |
| Tables `checkpoint*` | Historique LangGraph, résultats des outils et état de pause/reprise. |

L'interface recharge les messages depuis le checkpointer après réouverture du
navigateur ou redémarrage de l'API. Les messages d'erreur d'affichage restent
locaux à la session Streamlit ; l'état déjà sauvegardé reste en base.

La migration des profils et conversations est additive. Elle conserve les tables
et checkpoints antérieurs, mais n'attribue pas automatiquement les anciens threads
sans propriétaire : ces threads ne deviennent pas visibles dans les profils.
Les commandes de mise à jour sans réingestion figurent dans le
[README](../README.md#mise-à-jour-locale).

Le volume PostgreSQL conserve les données après `docker compose down`.
`docker compose down -v` supprime ce volume. Cette persistance ne remplace pas
une sauvegarde externe.

### Suppression et transactions

La suppression d'un chat nécessite une confirmation dans l'interface et reste
réservée au propriétaire. Elle supprime d'abord les checkpoints, blobs et écritures
LangGraph du thread, puis ses métadonnées. Une proposition en attente disparaît
sans être exécutée ; les incidents créés, l'audit métier et les traces LangSmith
restent conservés. Les sauvegardes externes peuvent contenir l'ancien historique.

Les métadonnées et les checkpoints utilisent des transactions distinctes, sans
atomicité commune. Si la suppression des métadonnées échoue après celle des
checkpoints, une nouvelle tentative permet de terminer le nettoyage.
Le verrou en mémoire ne coordonne pas plusieurs processus API : une exécution
avec plusieurs workers ou instances nécessite une coordination partagée.

## Routes API

Les routes ci-dessous requièrent `X-Demo-User-Id`, à l'exception de `/demo/users`,
public dans le mode de démonstration. Les schémas de requête et de réponse sont
accessibles dans la documentation FastAPI sur <http://127.0.0.1:8000/docs>.

| Route | Fonction |
| --- | --- |
| `GET /demo/users` | Profils disponibles. |
| `POST /conversations` | Création d'une conversation avec UUID serveur et propriétaire. |
| `GET /conversations` | Chats personnels et demandes déjà traitées par le superviseur. |
| `GET /conversations/{thread_id}` | Historique, actions en attente et droits de la session. |
| `DELETE /conversations/{thread_id}` | Suppression par le propriétaire ; réponse `204`. |
| `POST /chat` | Message du propriétaire dans une conversation sans action en attente. |
| `GET /approvals` | Demandes accessibles en attente ; superviseur uniquement. |
| `POST /threads/{thread_id}/decision` | Approbation ou refus ; superviseur uniquement. |

Une identité absente renvoie `401`, une permission refusée `403`, une conversation
inaccessible `404` et une reprise sans action en attente `409`. Chaque décision
couvre toutes les actions de la proposition. Une deuxième approbation après
traitement est refusée.

Les tests d'intégration sur `orderops_test` couvrent le transport MCP, la reprise
des checkpoints, les permissions, l'approbation/refus et l'audit avec un modèle
simulé. Les commandes sont regroupées dans le [README](../README.md#développement-et-tests).
