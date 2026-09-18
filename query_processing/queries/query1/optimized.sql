CREATE INDEX IF NOT EXISTS idx_rental_inventory_id ON rental(inventory_id);
CREATE INDEX IF NOT EXISTS idx_inventory_film_id ON inventory(film_id);
WITH actor_rentals AS(
    SELECT
        film_actor.actor_id,
        COUNT(*) as rental_count

    FROM film_actor
    JOIN inventory ON film_actor.film_id = inventory.film_id
    JOIN rental ON inventory.inventory_id = rental.inventory_id
    GROUP BY film_actor.actor_id
)

SELECT 
    actor.actor_id,
    CONCAT(actor.first_name, ' ', actor.last_name) AS actor_name,
    actor_rentals as rental_count
    
FROM actor_rentals

JOIN actor ON actor.actor_id = actor_rentals.actor_id

WHERE actor_rentals.rental_count > (SELECT AVG(rental_count) FROM actor_rentals)

ORDER BY actor_rentals.rental_count DESC;