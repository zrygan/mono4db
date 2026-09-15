CREATE INDEX IF NOT EXISTS idx_rental_inventory_id ON rental(inventory_id);
CREATE INDEX IF NOT EXISTS idx_inventory_film_id ON inventory(film_id);

SELECT 
    f.film_id,
    f.title,
    f.rental_rate,
    top10.rental_count
FROM (
    SELECT 
        i.film_id,
        COUNT(*) AS rental_count
    FROM rental r
    JOIN inventory i ON r.inventory_id = i.inventory_id
    GROUP BY i.film_id
    ORDER BY rental_count DESC
    LIMIT 10
) top10
JOIN film f ON f.film_id = top10.film_id
ORDER BY top10.rental_count DESC;
