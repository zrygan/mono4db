/* QUERY 3: Find films that outperform both their category average and their language average
   by rental count */
SELECT 
	f.film_id,
	f.title,
	COUNT(r.rental_id) AS total_rentals
FROM film f
JOIN inventory i ON i.film_id = f.film_id
LEFT JOIN rental r ON r.inventory_id = i.inventory_id
GROUP BY f.film_id, f.title
HAVING COUNT(r.rental_id) > (
	SELECT AVG(rental_count) FROM (
		SELECT f2.film_id, COUNT(r2.rental_id) AS rental_count
		FROM film f2
		JOIN film_category fc2 ON fc2.film_id = f2.film_id
		JOIN inventory i2 ON i2.film_id = f2.film_id
		LEFT JOIN rental r2 ON r2.inventory_id = i2.inventory_id
		WHERE fc2.category_id = (
			SELECT category_id FROM film_category fc3 WHERE fc3.film_id = f.film_id
		)
		GROUP BY f2.film_id
	) cat_avg
)
AND COUNT(r.rental_id) > (
	SELECT AVG(rental_count) FROM (
		SELECT f2.film_id, COUNT(r2.rental_id) AS rental_count
		FROM film f2
		JOIN inventory i2 ON i2.film_id = f2.film_id
		LEFT JOIN rental r2 ON r2.inventory_id = i2.inventory_id
		WHERE f2.language_id = f.language_id
		GROUP BY f2.film_id
	) lang_avg
)
ORDER BY total_rentals DESC;
