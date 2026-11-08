-- Run with run_locking_experiments.py for synchronized timing.
-- Synchronization directives control the runner; they are not SQL.
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;
UPDATE simplified_film SET length = 5 WHERE film_id = 1;
-- @ready
-- @hold
ROLLBACK;
-- @released
