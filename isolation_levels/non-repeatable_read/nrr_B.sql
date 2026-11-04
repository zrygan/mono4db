-- run within 10 SECONDS AFTER A

USE sakila;

SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ; -- CHANGE ISOLATION TYPE
START TRANSACTION;

UPDATE simplified_film SET length = 5 WHERE film_id = 1;
COMMIT;
SELECT 'committed' AS info, length FROM simplified_film WHERE film_id = 1;