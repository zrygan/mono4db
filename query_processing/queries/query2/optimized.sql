ALTER TABLE rental
ADD COLUMN rental_month INT
GENERATED ALWAYS AS (EXTRACT(MONTH FROM rental_date)) STORED;

CREATE INDEX IF NOT EXISTS idx_rental_inventory_month ON rental(inventory_id, rental_month);

SELECT 
    inventory.store_id,
    rental.rental_month AS month,
    COUNT(*) AS rental_count
FROM rental
JOIN inventory ON rental.inventory_id = inventory.inventory_id
GROUP BY inventory.store_id, month
ORDER BY inventory.store_id, rental_count DESC;