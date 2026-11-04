-- run within 10 SECONDS AFTER A
USE sakila;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED; -- CHANGE ISOLATION TYPE
START TRANSACTION;

INSERT INTO simplified_film (film_id, title, release_year, length)
VALUES (1001, 'Kagamine Rin', 2007, 2);
COMMIT;
SELECT 'committed insert' AS info, COUNT(*) AS num_films FROM simplified_film;