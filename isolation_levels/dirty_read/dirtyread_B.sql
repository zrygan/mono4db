-- run within 10 SECONDS of running A

USE sakila;

SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE; -- CHANGE ISOLATION LEVEL
START TRANSACTION;

SELECT 'read pre-rollback' AS info, length FROM simplified_film WHERE film_id = 1;
DO SLEEP(10);
SELECT 'read post-rollback' AS info, length FROM simplified_film WHERE film_id = 1;
COMMIT;