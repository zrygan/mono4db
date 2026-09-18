SELECT 
    store.store_id,
    EXTRACT(MONTH FROM rental.rental_date) AS month,
    COUNT(*) AS rental_count
FROM rental
JOIN inventory ON rental.inventory_id = inventory.inventory_id
JOIN store ON store.store_id = inventory.store_id

GROUP BY store.store_id, month
ORDER BY store.store_id, rental_count DESC;