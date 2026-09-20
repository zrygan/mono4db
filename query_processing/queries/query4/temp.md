```sql
WITH F AS (
    SELECT film_id, title
    FROM film
),

FC AS (
    SELECT film_id, category_id
    FROM film_category
),

I AS (
    SELECT film_id, inventory_id
    FROM inventory
),

R AS (
    SELECT inventory_id, rental_id, customer_id
    FROM rental
),

J1 AS (
    SELECT F.film_id, F.title, FC.category_id
    FROM F
    JOIN FC
        ON FC.film_id = F.film_id
),

J2 AS (
    SELECT
        J1.film_id,
        J1.title,
        J1.category_id,
        I.inventory_id
    FROM J1
    JOIN I
        ON I.film_id = J1.film_id
),

J3 AS (
    SELECT
        J2.film_id,
        J2.title,
        J2.category_id,
        J2.inventory_id,
        R.rental_id,
        R.customer_id
    FROM J2
    LEFT JOIN R
        ON R.inventory_id = J2.inventory_id
), 

C1 AS (
    SELECT
        -- K
        film_id,
        title,
        category_id,
        COUNT(inventory_id) AS copies_in_stock
    FROM J2
    GROUP BY film_id, title, category_id
),

C2 AS (
    SELECT 
        film_id,
        title,
        category_id,
        COUNT(rental_id) AS total_rentals 
    FROM J3
    GROUP BY film_id, title, category_id
),

C4 AS (
    SELECT
        film_id,
        title,
        category_id,
    COUNT(customer_id) AS unique_customers
    FROM J3
    GROUP BY film_id, title, category_id
)


-- C5 <- C1 >< C2 >< C4 
SELECT
    C1.film_id,
    C1.title,
    C1.category_id,
    C1.copies_in_stock,
    C2.total_rentals,
    C4.unique_customers,
    -- round was originally there
    ROUND(
        C2.total_rentals::numeric / NULLIF(C1.copies_in_stock, 0),
        2
    ) AS rentals_per_copy,

    ROUND(
        C2.total_rentals::numeric / NULLIF(C4.unique_customers, 0),
        2
    ) AS rentals_per_customer
FROM C1
JOIN C2 USING (film_id, title, category_id)
JOIN C4 USING (film_id, title, category_id)
-- this was originally there also 
ORDER BY rentals_per_copy DESC;
```