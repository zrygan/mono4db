-- Run with run_locking_experiments.py for synchronized timing.
-- Synchronization directives control the runner; they are not SQL.
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET autocommit = 0;
LOCK TABLES simplified_film READ;
SELECT COUNT(*) FROM simplified_film;
-- @ready
-- @hold
SELECT COUNT(*) FROM simplified_film;
COMMIT;
UNLOCK TABLES;
-- @released
