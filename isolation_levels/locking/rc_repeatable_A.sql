-- Run with run_locking_experiments.py for synchronized timing.
-- Synchronization directives control the runner; they are not SQL.
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
SELECT length FROM simplified_film WHERE film_id = 1 FOR SHARE;
-- @ready
-- @hold
SELECT length FROM simplified_film WHERE film_id = 1 FOR SHARE;
ROLLBACK;
-- @released
