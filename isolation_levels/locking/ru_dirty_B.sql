-- Run with run_locking_experiments.py for synchronized timing.
-- Synchronization directives control the runner; they are not SQL.
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
-- @wait
START TRANSACTION;
-- @attempt
SELECT length FROM simplified_film WHERE film_id = 1 FOR UPDATE;
SELECT length FROM simplified_film WHERE film_id = 1 FOR UPDATE;
ROLLBACK;
