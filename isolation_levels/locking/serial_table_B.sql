-- Run with run_locking_experiments.py for synchronized timing.
-- Synchronization directives control the runner; they are not SQL.
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
-- @wait
START TRANSACTION;
-- @attempt
INSERT INTO simplified_film (film_id, title, release_year, length) VALUES (@locking_film_id, 'Kagamine Rin', 2007, 2);
SELECT COUNT(*) FROM simplified_film;
ROLLBACK;
