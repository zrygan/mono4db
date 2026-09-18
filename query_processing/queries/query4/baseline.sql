/* QUERY 4: Get the number of stock for a movie, the number of rentals its had and the number
   of distinct customers whove rented it */
SELECT 
	f.film_id,
	f.title,
	fc.category_id,
	COUNT(DISTINCT i.inventory_id) AS copies_in_stock,
	COUNT(r.rental_id) AS total_rentals,
	COUNT(DISTINCT r.customer_id) AS unique_customers,
	ROUND(COUNT(r.rental_id)::numeric / NULLIF(COUNT(DISTINCT i.inventory_id), 0), 2) AS rentals_per_copy,
	ROUND(COUNT(r.rental_id)::numeric / NULLIF(COUNT(DISTINCT r.customer_id), 0), 2) AS rentals_per_customer
FROM film f
JOIN film_category fc ON fc.film_id = f.film_id
JOIN inventory i ON i.film_id = f.film_id
LEFT JOIN rental r ON r.inventory_id = i.inventory_id
GROUP BY f.film_id, f.title, fc.category_id
ORDER BY rentals_per_copy DESC;
