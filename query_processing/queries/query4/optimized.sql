WITH C1 AS (
    SELECT
        -- K = f.film_id, f.title, fc.category_id
        f.film_id,
        f.title,
        fc.category_id,
        COUNT(i.inventory_id) AS copies_in_stock
        -- from J2: F >< FC
    FROM film f
    JOIN film_category fc
        ON fc.film_id = f.film_id
    JOIN inventory i
        ON i.film_id = f.film_id
    GROUP BY
        f.film_id,
        f.title,
        fc.category_id
),


-- old C2 and C4 used the same attributes + J3
C2 AS (
    SELECT
        f.film_id,
        f.title,
        fc.category_id,
        COUNT(r.rental_id) AS total_rentals,
        COUNT(r.customer_id) AS unique_customers
    FROM film f
    JOIN film_category fc
        ON fc.film_id = f.film_id
    JOIN inventory i
        ON i.film_id = f.film_id
    LEFT JOIN rental r
        ON r.inventory_id = i.inventory_id
    GROUP BY
        f.film_id,
        f.title,
        fc.category_id
)

SELECT
    C1.film_id,
    C1.title,
    C1.category_id,
    C1.copies_in_stock,
    C2.total_rentals,
    C2.unique_customers,

    -- was in the original, wasn't changed to RA
    ROUND(
        C2.total_rentals::numeric
        / NULLIF(C1.copies_in_stock, 0),
        2
    ) AS rentals_per_copy,

    ROUND(
        C2.total_rentals::numeric
        / NULLIF(C2.unique_customers, 0),
        2
    ) AS rentals_per_customer

FROM C1
JOIN C2 USING (film_id, title, category_id)

-- was in the original, wasn't changed to RA
ORDER BY rentals_per_copy DESC;