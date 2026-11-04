-- run FIRST

USE sakila;

DELETE FROM simplified_film WHERE film_id = 1001; -- reset

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED; -- CHANGE ISOLATION TYPE
START TRANSACTION;

SELECT 'read, pre-insert' AS info, COUNT(*) AS num_films FROM simplified_film;
DO SLEEP(10);
SELECT 'read, post-insert' AS info, COUNT(*) AS num_films FROM simplified_film;
COMMIT;