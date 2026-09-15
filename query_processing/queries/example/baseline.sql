SELECT 
    f.film_id,
    f.title,
    f.rental_rate,
    COUNT(DISTINCT r.rental_id) AS rental_count
FROM film f
JOIN inventory i ON f.film_id = i.film_id
JOIN rental r ON i.inventory_id = r.inventory_id
GROUP BY f.film_id, f.title, f.rental_rate
ORDER BY rental_count DESC
LIMIT 10;

