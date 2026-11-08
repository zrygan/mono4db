# Measured locking results

Run started: 2026-11-08 23:15:17 UTC+08:00 (Asia/Manila)

Elapsed statement times include server execution, lock waiting, and client overhead.
Blocking is inferred from controlled overlap and completion after lock release.
Exact server lock-wait duration and throughput were not measured.

| Case | Pass | Blocked statement (s) | Total (s) | Table unchanged |
|---|---|---|---|---|
| ru_dirty | True | 3.015414 | 3.048916 | True |
| rc_repeatable | True | 3.008785 | 3.044720 | True |
| rr_phantom | True | 3.005767 | 3.044613 | True |
| serial_table | True | 3.010605 | 3.047851 | True |

## ru_dirty (run 1)

| Time | Transaction A | Transaction B |
|---|---|---|
| t1, 0.019535s |  | SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED [0.000118s]  |
| t2, 0.019785s | SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED [0.000159s]  |  |
| t3, 0.019947s | START TRANSACTION [0.000097s]  |  |
| t4, 0.020045s | UPDATE simplified_film SET length = 5 WHERE film_id = 1 [0.000740s]  |  |
| t5, 0.020867s |  | START TRANSACTION [0.000278s]  |
| t6, 0.021150s |  | SELECT length FROM simplified_film WHERE film_id = 1 FOR UPDATE -> [(86,)] [3.015414s]  |
| t7, 3.035504s | ROLLBACK [0.012013s]  |  |
| t8, 3.036569s |  | SELECT length FROM simplified_film WHERE film_id = 1 FOR UPDATE -> [(86,)] [0.000347s]  |
| t9, 3.036920s |  | ROLLBACK [0.000179s]  |

## rc_repeatable (run 1)

| Time | Transaction A | Transaction B |
|---|---|---|
| t1, 0.032454s |  | SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED [0.000237s]  |
| t2, 0.032528s | SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED [0.000273s]  |  |
| t3, 0.032806s | START TRANSACTION [0.000197s]  |  |
| t4, 0.033007s | SELECT length FROM simplified_film WHERE film_id = 1 FOR SHARE -> [(86,)] [0.000512s]  |  |
| t5, 0.033569s |  | START TRANSACTION [0.000209s]  |
| t6, 0.033784s |  | UPDATE simplified_film SET length = 5 WHERE film_id = 1 [3.008785s]  |
| t7, 3.041381s | SELECT length FROM simplified_film WHERE film_id = 1 FOR SHARE -> [(86,)] [0.000661s]  |  |
| t8, 3.042048s | ROLLBACK [0.000200s]  |  |
| t9, 3.042572s |  | SELECT length FROM simplified_film WHERE film_id = 1 -> [(5,)] [0.000228s]  |
| t10, 3.042805s |  | ROLLBACK [0.001230s]  |

## rr_phantom (run 1)

| Time | Transaction A | Transaction B |
|---|---|---|
| t1, 0.022613s | SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ [0.000105s]  |  |
| t2, 0.022649s |  | SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ [0.000132s]  |
| t3, 0.022723s | START TRANSACTION [0.000093s]  |  |
| t4, 0.022818s | SELECT film_id FROM simplified_film FORCE INDEX (PRIMARY) WHERE film_id >= 1 ORDER BY film_id FOR UPDATE -> [(1,), (2,), (3,), (4,), (5,)] (1001 rows total) [0.002365s]  |  |
| t5, 0.025230s |  | START TRANSACTION [0.000303s]  |
| t6, 0.025538s |  | INSERT INTO simplified_film (film_id, title, release_year, length) VALUES (@locking_film_id, 'Kagamine Rin', 2007, 2) [3.005767s]  |
| t7, 3.028635s | SELECT film_id FROM simplified_film FORCE INDEX (PRIMARY) WHERE film_id >= 1 ORDER BY film_id FOR UPDATE -> [(1,), (2,), (3,), (4,), (5,)] (1001 rows total) [0.002217s]  |  |
| t8, 3.030857s | ROLLBACK [0.000209s]  |  |
| t9, 3.031309s |  | SELECT COUNT(*) FROM simplified_film -> [(1002,)] [0.001981s]  |
| t10, 3.033292s |  | ROLLBACK [0.010150s]  |

## serial_table (run 1)

| Time | Transaction A | Transaction B |
|---|---|---|
| t1, 0.005053s | SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE [0.000184s]  |  |
| t2, 0.005240s | SET autocommit = 0 [0.000112s]  |  |
| t3, 0.005354s | LOCK TABLES simplified_film READ [0.000160s]  |  |
| t4, 0.005515s | SELECT COUNT(*) FROM simplified_film -> [(1001,)] [0.000500s]  |  |
| t5, 0.027115s |  | SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE [0.000320s]  |
| t6, 0.027448s |  | START TRANSACTION [0.000141s]  |
| t7, 0.027591s |  | INSERT INTO simplified_film (film_id, title, release_year, length) VALUES (@locking_film_id, 'Kagamine Rin', 2007, 2) [3.010605s]  |
| t8, 3.036670s | SELECT COUNT(*) FROM simplified_film -> [(1001,)] [0.000808s]  |  |
| t9, 3.037482s | COMMIT [0.000127s]  |  |
| t10, 3.037611s | UNLOCK TABLES [0.000094s]  |  |
| t11, 3.038199s |  | SELECT COUNT(*) FROM simplified_film -> [(1002,)] [0.000471s]  |
| t12, 3.038673s |  | ROLLBACK [0.008427s]  |
