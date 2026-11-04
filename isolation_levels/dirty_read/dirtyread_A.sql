-- run FIRST

USE sakila;

UPDATE simplified_film SET length = 86 WHERE film_id = 1; -- reset

SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE; -- CHANGE ISOLATION LEVEL
START TRANSACTION;

UPDATE simplified_film SET length = 5 WHERE film_id = 1;
SELECT 'updated, not committed' AS info, length FROM simplified_film WHERE film_id = 1;
DO SLEEP(10);
ROLLBACK;
SELECT 'after rollback' AS info, length FROM simplified_film WHERE film_id = 1;