-- run FIRST

USE sakila;

UPDATE simplified_film SET length = 86 WHERE film_id = 1; -- reset

SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ; -- CHANGE ISOLATION TYPE
START TRANSACTION;

SELECT 'read pre-commit' AS info, length FROM simplified_film WHERE film_id = 1;
DO SLEEP(10);
SELECT 'read post-commit' AS info, length FROM simplified_film WHERE film_id = 1;
COMMIT;