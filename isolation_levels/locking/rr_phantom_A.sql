-- Run with run_locking_experiments.py for synchronized timing.
-- Synchronization directives control the runner; they are not SQL.
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
SELECT film_id FROM simplified_film FORCE INDEX (PRIMARY) WHERE film_id >= 1 ORDER BY film_id FOR UPDATE;
-- @ready
-- @hold
SELECT film_id FROM simplified_film FORCE INDEX (PRIMARY) WHERE film_id >= 1 ORDER BY film_id FOR UPDATE;
ROLLBACK;
-- @released
