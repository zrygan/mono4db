WITH film_rentals AS (
	SELECT
		f.film_id,
		f.title,
		f.language_id,
		COUNT(r.rental_id) AS total_rentals
	FROM film f
	JOIN inventory i   ON i.film_id = f.film_id
	LEFT JOIN rental r ON r.inventory_id = i.inventory_id
	GROUP BY f.film_id, f.title, f.language_id
),
cat_avg AS (
	SELECT
		c.category_id,
		c.name,
		AVG(fr.total_rentals) AS avg_rentals
	FROM film_category fc
	JOIN category c      ON c.category_id = fc.category_id
	JOIN film_rentals fr ON fr.film_id = fc.film_id
	GROUP BY c.category_id, c.name
),
lang_avg AS (
	SELECT
		l.language_id,
		l.name,
		AVG(fr.total_rentals) AS avg_rentals
	FROM film_rentals fr
	JOIN language l ON l.language_id = fr.language_id
	GROUP BY l.language_id, l.name
)
SELECT
	fr.film_id,
	fr.title,
	fr.total_rentals,
	ca.name AS category_name,
	la.name AS language_name
FROM film_rentals fr
JOIN film_category fc ON fc.film_id = fr.film_id
JOIN cat_avg ca       ON ca.category_id = fc.category_id
JOIN lang_avg la      ON la.language_id = fr.language_id
WHERE fr.total_rentals > ca.avg_rentals
  AND fr.total_rentals > la.avg_rentals
ORDER BY fr.total_rentals DESC;