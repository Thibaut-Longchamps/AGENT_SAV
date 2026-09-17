# Capacités de l'agent, outils et rôles

OrderOps est un assistant ADV/SAV pour consulter les données d'une commande,
retrouver une procédure et préparer un incident logistique. La création de
l'incident nécessite une décision explicite d'un superviseur dans l'interface.

Ce guide décrit les fonctions présentes dans le code. L'application utilise des
profils de démonstration sélectionnables sans mot de passe ; elle est destinée à
une utilisation locale.

## Ce que peut faire l'agent

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

## Outils disponibles

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

## Rôles et permissions

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

### Lecteur

Le modèle peut consulter les données et les procédures. L'outil `create_incident`
est absent de la liste qui lui est fournie. La lecture seule concerne les données
métier : les messages et conversations du lecteur sont néanmoins sauvegardés.

Exemple : « Quel est le statut de CMD-1042 et quelle procédure s'applique au retard ? »

### Opérateur SAV

L'opérateur peut demander à l'agent de préparer un incident. L'agent affiche la
proposition puis s'interrompt. L'opérateur ne peut ni approuver ni refuser cette
action ; il attend la décision du superviseur.

Exemple : « Vérifie CMD-1042 et prépare un incident si les informations le justifient. »

### Superviseur

Le superviseur consulte les demandes des opérateurs en attente et les approuve ou
les refuse. Il conserve l'accès aux demandes qu'il a traitées. Ce rôle ne donne
pas accès à toutes les conversations : celles d'un lecteur ou d'un autre
superviseur restent privées dans les règles de l'application.

Le superviseur peut aussi créer une proposition dans sa propre conversation et
l'approuver lui-même. Le MVP n'impose pas deux personnes distinctes pour la
proposition et l'approbation. L'approbation reste une action explicite dans
l'interface ; un message de chat ne remplace pas cette décision.

## Déroulement d'une demande

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

## Limites fonctionnelles

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

## Références

- [Architecture, persistance et routes API](architecture.md)
- [Configuration](configuration.md)
- Implémentation : [outils MCP](../src/orderops/mcp/server.py),
  [recherche documentaire](../src/orderops/rag/tool.py),
  [construction de l'agent](../src/orderops/agent/factory.py) et
  [permissions](../src/orderops/access.py).
