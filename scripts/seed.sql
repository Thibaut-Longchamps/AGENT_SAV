-- ============================================================================
-- OrderOps — Jeu de données métier de démonstration
-- ============================================================================
--
-- Objectif :
-- fournir des cas de test pour les repositories, les services métier,
-- les tools MCP et l'agent.
--
-- Situations métier présentes dans ce seed :
--
-- 1. commande livrée normalement ;
-- 2. commande actuellement en transit ;
-- 3. livraison en retard ;
-- 4. livraison en échec chez le transporteur ;
-- 5. commande confirmée mais pas encore expédiée ;
-- 6. commande en attente ;
-- 7. commande annulée ;
-- 8. commande expédiée mais sans livraison enregistrée / tracking absent ;
-- 9. date de livraison prévue dépassée ;
-- 10. produit avec du stock disponible ;
-- 11. produit avec stock faible ;
-- 12. produit totalement en rupture de stock ;
-- 13. stock présent mais entièrement réservé ;
-- 14. commandes contenant plusieurs produits ;
-- 15. clients possédant plusieurs commandes ;
-- 16. incident déjà ouvert ;
-- 17. incident en cours de traitement ;
-- 18. incident déjà résolu ;
-- 19. commande retardée sans incident dans les données initiales.
--
-- Ce script est idempotent :
-- il peut être exécuté plusieurs fois sans créer de doublons.
--
-- Cette étape concerne uniquement les données métier.
-- Elle ne crée aucune donnée RAG et ne configure pas pgvector.
--
-- Ce script n'insère aucune ligne dans action_audit ni dans security_events.
-- La création d'incident alimente action_audit ; l'ingestion affiche les quarantaines
-- dans ses sorties sans les enregistrer dans security_events.
-- ============================================================================

BEGIN;


-- ============================================================================
-- CLIENTS
-- ============================================================================

INSERT INTO customers (customer_id, name, email, phone)
VALUES
    ('CUS-001', 'ACME', 'sav@acme.example', '+33100000001'),
    ('CUS-002', 'Globex', 'contact@globex.example', '+33100000002'),
    ('CUS-003', 'Nova Retail', 'contact@nova.example', '+33100000003'),
    ('CUS-004', 'Atlas Services', 'adv@atlas.example', '+33100000004'),
    ('CUS-005', 'Hexa Distribution', 'achats@hexa.example', '+33100000005'),
    ('CUS-006', 'Orion Mobility', 'orders@orion.example', '+33100000006'),
    ('CUS-007', 'Delta Pro', 'contact@delta.example', '+33100000007'),
    ('CUS-008', 'Sigma Industrie', 'adv@sigma.example', '+33100000008'),
    ('CUS-009', 'Horizon Tech', 'purchasing@horizon.example', '+33100000009'),
    ('CUS-010', 'Nexo Commerce', 'commandes@nexo.example', '+33100000010'),
    ('CUS-011', 'Vertex Solutions', 'contact@vertex.example', '+33100000011'),
    ('CUS-012', 'Alpha Business', 'adv@alpha.example', '+33100000012')
ON CONFLICT (customer_id) DO UPDATE
SET
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    phone = EXCLUDED.phone;


-- ============================================================================
-- PRODUITS
-- ============================================================================

INSERT INTO products (product_id, name)
VALUES
    ('SKU-12', 'Scanner mobile'),
    ('SKU-13', 'Support scanner'),
    ('SKU-14', 'Imprimante étiquettes'),
    ('SKU-15', 'Rouleaux étiquettes'),
    ('SKU-16', 'Terminal portable'),
    ('SKU-17', 'Batterie terminal'),
    ('SKU-18', 'Chargeur terminal'),
    ('SKU-19', 'Routeur industriel'),
    ('SKU-20', 'Lecteur code-barres'),
    ('SKU-21', 'Tablette renforcée'),
    ('SKU-22', 'Dock tablette'),
    ('SKU-23', 'Kit câbles')
ON CONFLICT (product_id) DO UPDATE
SET
    name = EXCLUDED.name;


-- ============================================================================
-- STOCKS
--
-- Cas particuliers :
-- SKU-14 → stock très faible
-- SKU-16 → rupture totale
-- SKU-17 → tout le stock est réservé
-- SKU-19 → stock faible
-- SKU-22 → tout le stock est réservé
-- ============================================================================

INSERT INTO inventory (
    product_id,
    on_hand_quantity,
    reserved_quantity
)
VALUES
    ('SKU-12', 20, 4),
    ('SKU-13', 8, 2),
    ('SKU-14', 3, 2),
    ('SKU-15', 120, 35),
    ('SKU-16', 0, 0),
    ('SKU-17', 5, 5),
    ('SKU-18', 14, 3),
    ('SKU-19', 2, 0),
    ('SKU-20', 25, 8),
    ('SKU-21', 6, 1),
    ('SKU-22', 4, 4),
    ('SKU-23', 50, 10)
ON CONFLICT (product_id) DO UPDATE
SET
    on_hand_quantity = EXCLUDED.on_hand_quantity,
    reserved_quantity = EXCLUDED.reserved_quantity;


-- ============================================================================
-- COMMANDES
-- ============================================================================

INSERT INTO orders (
    order_id,
    customer_id,
    status,
    expected_delivery
)
VALUES
    ('CMD-1042', 'CUS-001', 'shipped',   DATE '2026-08-18'),
    ('CMD-1043', 'CUS-002', 'delivered', DATE '2026-08-15'),
    ('CMD-1044', 'CUS-003', 'confirmed', DATE '2026-08-26'),
    ('CMD-1045', 'CUS-001', 'pending',   DATE '2026-08-30'),
    ('CMD-1046', 'CUS-004', 'shipped',   DATE '2026-08-20'),
    ('CMD-1047', 'CUS-005', 'shipped',   DATE '2026-08-24'),
    ('CMD-1048', 'CUS-006', 'cancelled', DATE '2026-08-23'),
    ('CMD-1049', 'CUS-007', 'delivered', DATE '2026-08-19'),
    ('CMD-1050', 'CUS-008', 'shipped',   DATE '2026-08-21'),
    ('CMD-1051', 'CUS-009', 'confirmed', DATE '2026-08-20'),
    ('CMD-1052', 'CUS-010', 'delivered', DATE '2026-08-17'),
    ('CMD-1053', 'CUS-011', 'shipped',   DATE '2026-08-22'),
    ('CMD-1054', 'CUS-012', 'pending',   DATE '2026-09-01'),
    ('CMD-1055', 'CUS-003', 'delivered', DATE '2026-08-16'),
    ('CMD-1056', 'CUS-004', 'shipped',   DATE '2026-08-25'),
    ('CMD-1057', 'CUS-005', 'confirmed', DATE '2026-08-29'),
    ('CMD-1058', 'CUS-006', 'delivered', DATE '2026-08-18'),
    ('CMD-1059', 'CUS-007', 'shipped',   DATE '2026-08-20'),
    ('CMD-1060', 'CUS-008', 'cancelled', DATE '2026-08-21'),
    ('CMD-1061', 'CUS-009', 'shipped',   DATE '2026-08-27'),
    ('CMD-1062', 'CUS-010', 'confirmed', DATE '2026-08-21'),
    ('CMD-1063', 'CUS-011', 'delivered', DATE '2026-08-14'),
    ('CMD-1064', 'CUS-012', 'shipped',   DATE '2026-08-22'),
    ('CMD-1065', 'CUS-002', 'shipped',   DATE '2026-08-23')
ON CONFLICT (order_id) DO UPDATE
SET
    customer_id = EXCLUDED.customer_id,
    status = EXCLUDED.status,
    expected_delivery = EXCLUDED.expected_delivery;


-- ============================================================================
-- LIGNES DE COMMANDES
-- ============================================================================

INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
VALUES
    ('CMD-1042', 'SKU-12', 2, 249.90),
    ('CMD-1042', 'SKU-13', 2, 39.50),

    ('CMD-1043', 'SKU-14', 1, 329.00),

    ('CMD-1044', 'SKU-16', 3, 499.00),
    ('CMD-1044', 'SKU-17', 3, 89.00),

    ('CMD-1045', 'SKU-15', 10, 12.50),

    ('CMD-1046', 'SKU-19', 1, 749.00),

    ('CMD-1047', 'SKU-21', 2, 899.00),
    ('CMD-1047', 'SKU-22', 2, 119.00),

    ('CMD-1048', 'SKU-20', 4, 189.00),

    ('CMD-1049', 'SKU-18', 2, 69.00),
    ('CMD-1049', 'SKU-23', 3, 29.90),

    ('CMD-1050', 'SKU-12', 1, 249.90),
    ('CMD-1050', 'SKU-14', 1, 329.00),

    ('CMD-1051', 'SKU-17', 2, 89.00),

    ('CMD-1052', 'SKU-20', 2, 189.00),
    ('CMD-1052', 'SKU-15', 5, 12.50),

    ('CMD-1053', 'SKU-21', 1, 899.00),
    ('CMD-1053', 'SKU-23', 2, 29.90),

    ('CMD-1054', 'SKU-16', 1, 499.00),

    ('CMD-1055', 'SKU-18', 3, 69.00),

    ('CMD-1056', 'SKU-19', 1, 749.00),
    ('CMD-1056', 'SKU-23', 4, 29.90),

    ('CMD-1057', 'SKU-14', 2, 329.00),
    ('CMD-1057', 'SKU-15', 20, 12.50),

    ('CMD-1058', 'SKU-12', 3, 249.90),

    ('CMD-1059', 'SKU-20', 1, 189.00),
    ('CMD-1059', 'SKU-22', 1, 119.00),

    ('CMD-1060', 'SKU-21', 1, 899.00),

    ('CMD-1061', 'SKU-18', 1, 69.00),
    ('CMD-1061', 'SKU-23', 5, 29.90),

    ('CMD-1062', 'SKU-16', 2, 499.00),
    ('CMD-1062', 'SKU-17', 2, 89.00),

    ('CMD-1063', 'SKU-14', 1, 329.00),
    ('CMD-1063', 'SKU-15', 3, 12.50),

    ('CMD-1064', 'SKU-19', 1, 749.00),

    ('CMD-1065', 'SKU-12', 1, 249.90),
    ('CMD-1065', 'SKU-13', 1, 39.50)
ON CONFLICT (order_id, product_id) DO UPDATE
SET
    quantity = EXCLUDED.quantity,
    unit_price = EXCLUDED.unit_price;


-- ============================================================================
-- LIVRAISONS
--
-- CMD-1042 → retard
-- CMD-1046 → échec transporteur
-- CMD-1050 → retard
-- CMD-1059 → retard
-- CMD-1064 → échec transporteur
-- CMD-1065 → aucune ligne de livraison, pour le cas shipped sans suivi disponible.
-- ============================================================================

INSERT INTO deliveries (
    delivery_id,
    order_id,
    status,
    carrier,
    tracking_number,
    expected_delivery
)
VALUES
    ('DEL-1042', 'CMD-1042', 'delayed',    'Demo Transport', 'TRACK-1042', DATE '2026-08-18'),
    ('DEL-1043', 'CMD-1043', 'delivered',  'FastShip',       'TRACK-1043', DATE '2026-08-15'),
    ('DEL-1046', 'CMD-1046', 'failed',     'Euro Parcel',    'TRACK-1046', DATE '2026-08-20'),
    ('DEL-1047', 'CMD-1047', 'in_transit', 'FastShip',       'TRACK-1047', DATE '2026-08-24'),
    ('DEL-1049', 'CMD-1049', 'delivered',  'Demo Transport', 'TRACK-1049', DATE '2026-08-19'),
    ('DEL-1050', 'CMD-1050', 'delayed',    'Euro Parcel',    'TRACK-1050', DATE '2026-08-21'),
    ('DEL-1052', 'CMD-1052', 'delivered',  'FastShip',       'TRACK-1052', DATE '2026-08-17'),
    ('DEL-1053', 'CMD-1053', 'in_transit', 'Demo Transport', 'TRACK-1053', DATE '2026-08-22'),
    ('DEL-1055', 'CMD-1055', 'delivered',  'FastShip',       'TRACK-1055', DATE '2026-08-16'),
    ('DEL-1056', 'CMD-1056', 'in_transit', 'Euro Parcel',    'TRACK-1056', DATE '2026-08-25'),
    ('DEL-1058', 'CMD-1058', 'delivered',  'Demo Transport', 'TRACK-1058', DATE '2026-08-18'),
    ('DEL-1059', 'CMD-1059', 'delayed',    'FastShip',       'TRACK-1059', DATE '2026-08-20'),
    ('DEL-1061', 'CMD-1061', 'in_transit', 'Euro Parcel',    'TRACK-1061', DATE '2026-08-27'),
    ('DEL-1063', 'CMD-1063', 'delivered',  'FastShip',       'TRACK-1063', DATE '2026-08-14'),
    ('DEL-1064', 'CMD-1064', 'failed',     'Demo Transport', 'TRACK-1064', DATE '2026-08-22')
ON CONFLICT (order_id) DO UPDATE
SET
    status = EXCLUDED.status,
    carrier = EXCLUDED.carrier,
    tracking_number = EXCLUDED.tracking_number,
    expected_delivery = EXCLUDED.expected_delivery;


-- ============================================================================
-- INCIDENTS HISTORIQUES
--
-- Ils servent à tester :
-- - incident ouvert ;
-- - incident en cours ;
-- - incident résolu ;
-- - comparaison entre commande avec et sans incident.
-- ============================================================================

INSERT INTO incidents (
    incident_id,
    order_id,
    reason,
    status,
    idempotency_key,
    request_hash
)
VALUES
    (
        'INC-1001',
        'CMD-1042',
        'Livraison en retard signalée par le transporteur',
        'open',
        'seed-incident-CMD-1042',
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    ),
    (
        'INC-1002',
        'CMD-1046',
        'Échec de livraison chez le transporteur',
        'in_progress',
        'seed-incident-CMD-1046',
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
    ),
    (
        'INC-1003',
        'CMD-1050',
        'Retard de livraison traité avec le client',
        'resolved',
        'seed-incident-CMD-1050',
        'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'
    ),
    (
        'INC-1004',
        'CMD-1059',
        'Livraison toujours non reçue après la date prévue',
        'open',
        'seed-incident-CMD-1059',
        'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd'
    ),
    (
        'INC-1005',
        'CMD-1064',
        'Transporteur incapable de finaliser la livraison',
        'open',
        'seed-incident-CMD-1064',
        'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
    ),
    (
        'INC-1006',
        'CMD-1049',
        'Produit livré endommagé puis dossier résolu',
        'resolved',
        'seed-incident-CMD-1049',
        'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'
    )
ON CONFLICT (idempotency_key) DO UPDATE
SET
    order_id = EXCLUDED.order_id,
    reason = EXCLUDED.reason,
    status = EXCLUDED.status,
    request_hash = EXCLUDED.request_hash;


COMMIT;


-- ============================================================================
-- CONTRÔLE DU NOMBRE DE LIGNES
-- ============================================================================

SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'inventory', COUNT(*) FROM inventory
UNION ALL
SELECT 'orders', COUNT(*) FROM orders
UNION ALL
SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL
SELECT 'deliveries', COUNT(*) FROM deliveries
UNION ALL
SELECT 'incidents', COUNT(*) FROM incidents
UNION ALL
SELECT 'action_audit', COUNT(*) FROM action_audit
UNION ALL
SELECT 'security_events', COUNT(*) FROM security_events
ORDER BY table_name;
