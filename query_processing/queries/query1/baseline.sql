SELECT 
    actor.actor_id,
    CONCAT(actor.first_name, ' ', actor.last_name) AS actor_name,
    COUNT(*) as rental_count
    
FROM actor

JOIN film_actor ON actor.actor_id = film_actor.actor_id
JOIN film ON film_actor.film_id = film.film_id
JOIN inventory ON film.film_id = inventory.film_id
JOIN rental ON inventory.inventory_id = rental.inventory_id

GROUP BY actor.actor_id

HAVING COUNT(*) > (
    SELECT AVG(rental_count)
    FROM(
        SELECT COUNT(*) AS rental_count
        FROM actor
        JOIN film_actor ON actor.actor_id = film_actor.actor_id
        JOIN film ON film_actor.film_id = film.film_id
        JOIN inventory ON film.film_id = inventory.film_id
        JOIN rental ON inventory.inventory_id = rental.inventory_id
        GROUP BY actor.actor_id
    ) AS actor_rentals
)

ORDER BY rental_count DESC;