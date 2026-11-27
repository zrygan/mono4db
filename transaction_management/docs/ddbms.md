# Distributed Database Management System

This document describes how we will simulate a Distributed Database Management System (DDBMS) using PostgreSQL.

## Schema

All three nodes store one relation, `fact_stop`, with the same schema:

```sql
stop_id         BIGINT PRIMARY KEY,
rdt_id          BIGINT NOT NULL,
arrival_time    TIMESTAMP,
departure_time  TIMESTAMP,
arrival_delay   INTEGER,
departure_delay INTEGER,
station_code    TEXT   NOT NULL
```

## Summary

We assign a central node that performs the initial fragmentation of the database and hands one fragment to each leaf node. For CRUD operations we do not distinguish between central and leaf nodes: there are no favorites or biases (e.g., we don't route through the central node because *it is the central node*). Any node can receive any query.

Every row exists in exactly two places: in the central node and in exactly one of the leaf nodes. The leaf fragments are disjoint, and their union is the whole database. Each fragment is therefore a proper subset of the central node's table.

Each node runs its own independent PostgreSQL instance in its own Docker container; no storage is shared between nodes. Because every row is stored twice, a write is never applied to only one node. Every `INSERT`, `UPDATE` and `DELETE` is applied atomically to the central node **and** to the leaf that owns the row, using two-phase commit (see [Two-phase Commit](#two-phase-commit-2pc)).

The specification requires the following:

1. The central node has all rows.
2. Each leaf node has a subset of the complete dataset.
3. All nodes have the same schema (columns).

Since each node is a fully functional, independent database, we need to:

1. **Enforce a homogeneous database.** Every node has the same schema; they differ only in the rows they hold.
2. **Keep the nodes synchronized.** Every write must be applied to every copy of the affected rows, so that the central node's table is always the union of the leaves' tables. This requires a protocol for node communication (see [Node Communication](#node-communication)).
3. **Prevent PK collisions.** A node inserting a new row must not generate a `stop_id` that is already used elsewhere (see [Questions and Resolutions](#questions-and-resolutions)).

## Technical Details

### Nodes and Notation

The system has three nodes: the central node $C$ and the leaf nodes $A$ and $B$.

- $R$ is the full relation (`fact_stop`), and $R_N$ is the table stored on node $N$. Then $R_C = R = R_A \cup R_B$ and $R_A \cap R_B = \varnothing$.
- All tables have the same schema $S$.
- $N^*$ is the node where a query was submitted. That node acts as the **coordinator** for the query.
- $q$ is a query and $T(q)$ is the distributed transaction that executes it.
- $\text{frag}(q) \subseteq \{A, B\}$ is the set of leaves whose fragments contain rows that $q$ reads or writes.
- $P(q)$ is the **participant set** of a write query $q$: the nodes that must apply $q$.
- $gid$ is the ***g**lobal **id**entifier* of $T(q)$.

### Horizontal Fragmentation

The leaves hold disjoint horizontal fragments of $R$, defined by a predicate on `station_code`. Let $s_0$ be a fixed split value:

$$
R_A = \sigma_{\texttt{station\_code} < s_0}(R) \qquad R_B = \sigma_{\texttt{station\_code} \geq s_0}(R)
$$

- The predicate is total: every possible `station_code`, including one not yet in the data, falls in exactly one fragment. This guarantees $R_A \cup R_B = R$ and $R_A \cap R_B = \varnothing$.
- $C$ chooses $s_0$ during initial fragmentation so that the fragments are roughly balanced (e.g., the median `station_code` by row count). After that, $s_0$ is a fixed configuration value known to every node.
- The owning leaf of a row is $\text{leaf}(r) = A$ if $r.\texttt{station\_code} < s_0$, else $B$.
- An `UPDATE` that changes `station_code` across $s_0$ **moves** the row: it is deleted from the old leaf and inserted into the new one, in the same transaction.

### Replication and Availability

Fragmentation decides *where* rows live. Replication (every row on $C$ and on one leaf) is what lets the system tolerate the failure of a node without the user noticing:

- If a leaf fails, $C$ still holds all of its rows.
- If $C$ fails, $A$ and $B$ together still hold all rows.

**Reads** do not use 2PC. A read $q$ is routed to a minimal set of available nodes that together hold the needed rows:

$$
R(q) =
\begin{cases}
\{C\} & \text{if } C \text{ is available} \\
\text{frag}(q) & \text{otherwise}
\end{cases}
$$

If $N^*$ holds all the needed rows itself, it answers locally.

**Writes** go through 2PC over $P(q)$ (see [Two-phase Commit](#two-phase-commit-2pc)).

### Node Communication

Nodes communicate over HTTP with JSON bodies. Each web app connects only to its **own** database; it reaches other nodes' data only through the other nodes' web apps. Every request's HTTP response is its acknowledgement, so no separate acknowledgement request is ever sent.

The cases where nodes communicate:

**Case 1: two-phase commit (2PC).**

1. `PREPARE`: $N^*$ asks every $n \in P(q)$ to prepare $T(q)$. Each $n$ votes `YES` or `NO` in its response.
2. `COMMIT`: if every vote is `YES`, $N^*$ tells every $n \in P(q)$ to commit $T(q)$.
3. `ABORT`: if at least one vote is `NO`, $N^*$ tells every $n \in P(q)$ to roll back $T(q)$.

**Case 2: faults and recovery.**

1. `STATUS`: a participant that restarts with an unresolved prepared transaction asks the coordinator what was decided for that $gid$.
2. `LOG`: a node that missed writes while it was down pulls them from the replication logs of the nodes that hold copies of its rows (see [Catch-up Replication](#catch-up-replication)).
3. `SNAPSHOT`: if the log cannot bring a node up to date, it copies its rows again from a source (see [Full Resync](#full-resync)).
4. `HEALTH`: nodes check whether a peer is up before routing to it, and to detect when a failed peer has recovered.

The table below summarizes the inter-node messages and their responses:

| Request                                         | Success                        | Failure                                            |
| ----------------------------------------------- | ------------------------------ | -------------------------------------------------- |
| `POST /internal/2pc/prepare` $(gid, q, D)$      | `200` = `YES`                  | `409` = `NO`                                       |
| `POST /internal/2pc/commit` $(gid)$             | `200` = `ACK`                  | None: the coordinator retries until it gets `ACK`. |
| `POST /internal/2pc/abort` $(gid)$              | `200` = `ACK`                  | None: the coordinator retries until it gets `ACK`. |
| `GET /internal/2pc/status/:gid`                 | `200` + `commit`/`abort`/`started` | `404` = no record, treated as `abort`         |
| `GET /internal/log?dest=:d&after=:seq`          | `200` + entries for $d$ with a greater $seq$, in order | None: $d$ retries until it gets `200`. |
| `GET /internal/snapshot?dest=:d`                | `200` + $d$'s rows and the current $seq$ | None: $d$ retries until it gets `200`.   |
| `GET /internal/health`                          | `200` = up                     | `503` or timeout = down, or still catching up      |

**Notes.** For requests whose failure response is a status code, a timeout or connection error also counts as failure. For requests with no failure response, the sender keeps retrying until it gets `200`.

All 2PC requests are **idempotent with respect to $gid$**. Repeating `PREPARE` for a $gid$ that is already prepared returns `YES` again. Repeating `COMMIT` or `ABORT` for a $gid$ that has already been resolved returns `ACK`. An `ABORT` for an unknown $gid$ also returns `ACK`. Repeating a `LOG` request with the same `after` returns the same entries, and $d$'s stored position stops it from applying any of them twice.

### Two-phase Commit (2PC)

This section covers how 2PC makes **write** operations atomic across nodes. **Read** operations do not use 2PC.

#### Participant Set

For a write query $q$ (`INSERT`, `UPDATE`, `DELETE`), every copy of every affected row must be written. Otherwise the replicas diverge:

$$
P(q) = \{C\} \cup \text{frag}(q)
$$

| Write $q$                                                         | $\text{frag}(q)$ | $P(q)$        |
| ----------------------------------------------------------------- | ---------------- | ------------- |
| Affects only rows in $R_A$                                        | $\{A\}$          | $\{C, A\}$    |
| Affects only rows in $R_B$                                        | $\{B\}$          | $\{C, B\}$    |
| Affects rows in both fragments, or moves a row between fragments  | $\{A, B\}$       | $\{C, A, B\}$ |

The participant set depends only on $q$, not on $N^*$. The coordinator may or may not belong to $P(q)$. For example, if $q$ only affects $R_A$ and is submitted at $B$, then $N^* = B \notin P(q) = \{C, A\}$.

#### Global Transaction Identifier

$N^*$ generates the $gid$ once, at the start of $T(q)$:

$$
gid = \langle N^* \rangle\text{-}\langle\text{unique counter or UUID}\rangle
$$

For example, `site3-1042`. The prefix guarantees that no two coordinators generate the same $gid$, and it lets any participant work out which node coordinated a transaction. Each participant uses the $gid$ as the name of its local prepared transaction (`PREPARE TRANSACTION 'gid'`).

#### Coordinator Log

Every node keeps a durable coordinator log in its own database, since any node can be a coordinator. Every log write is committed immediately in its own local transaction. Each $gid$ moves through these states:

$$
\texttt{started} \;\longrightarrow\; \texttt{commit} \mid \texttt{abort} \;\longrightarrow\; \texttt{done}
$$

| State     | Meaning                                                                    |
| --------- | -------------------------------------------------------------------------- |
| `started` | $T(q)$ exists with participants $P(q)$, and no decision has been made yet. |
| `commit`  | The decision is to commit. This is the point of no return.                 |
| `abort`   | The decision is to abort.                                                  |
| `done`    | Every participant has acknowledged the decision.                           |

Logging is bookkeeping only: writing to the coordinator log does **not** apply $q$ to the coordinator's data.

#### 2PC Algorithm

For a write query $q$ submitted at $N^*$:

1. $N^*$ computes $P(q)$ and generates $gid$.
2. $N^*$ logs $(gid, P(q))$ as `started`.
3. **Phase 1 (prepare).** In parallel, for each $n \in P(q)$:
    1. $N^*$ sends `PREPARE(gid, q)` to $n$.
    2. $n$ begins a local transaction and applies $q$ to its own data.
    3. $n$ runs `PREPARE TRANSACTION 'gid'`. This makes the change durable while keeping its row locks, without committing.
    4. If steps 2–3 succeed, $n$ responds `YES`.
    5. If any step fails (lock timeout, serialization failure, constraint violation, missing row), $n$ rolls back locally and responds `NO`.
    6. If $n$ does not respond within the timeout, $N^*$ treats its vote as `NO`.
4. **Abort path.** If any $n \in P(q)$ voted `NO`:
    1. $N^*$ logs $gid$ as `abort`.
    2. $N^*$ sends `ABORT(gid)` to every $n \in P(q)$.
    3. Each $n$ runs `ROLLBACK PREPARED 'gid'` if it had prepared, then responds `ACK`.
    4. $N^*$ retries `ABORT(gid)` to any $n$ that does not respond with `ACK`.
    5. $N^*$ logs $gid$ as `done`.
    6. $N^*$ reports failure to the user.
    7. **Terminate.**
5. **Decision.** Otherwise every $n \in P(q)$ voted `YES`, and $N^*$ logs $gid$ as `commit`. The outcome of $T(q)$ is now fixed, and $N^*$ may report success to the user.
6. **Phase 2 (commit).** In parallel, for each $n \in P(q)$:
    1. $N^*$ sends `COMMIT(gid)` to $n$.
    2. $n$ runs `COMMIT PREPARED 'gid'`, which releases its locks and makes the change visible.
    3. $n$ responds `ACK`.
    4. If no `ACK` arrives, $N^*$ retries `COMMIT(gid)` until one does.
7. Once every $n \in P(q)$ has responded with `ACK`, $N^*$ logs $gid$ as `done`.

> If $N^* \in P(q)$, it performs its own prepare, commit or rollback directly on its local database instead of sending itself HTTP requests.

**Ordering invariants.**

- No participant commits before $N^*$ has durably logged `commit`.
- $N^*$ logs `commit` only after every participant has voted `YES`.
- A participant responds `YES` only after `PREPARE TRANSACTION` succeeds, and `ACK` only after `COMMIT PREPARED` or `ROLLBACK PREPARED` succeeds.

#### 2PC Recovery

**The coordinator $N^*$ restarts.** For every $gid$ in its log that is not `done`:

| Logged state | Action                                                                                     |
| ------------ | ------------------------------------------------------------------------------------------ |
| `started`    | No decision was made, so abort: log `abort`, then send `ABORT(gid)` to every $n \in P(q)$. |
| `abort`      | Re-send `ABORT(gid)` to every $n \in P(q)$ until each responds with `ACK`.                 |
| `commit`     | Re-send `COMMIT(gid)` to every $n \in P(q)$ until each responds with `ACK`.                |

When all acknowledgements are in, $N^*$ logs $gid$ as `done`.

**A participant $n$ restarts.** Every transaction that $n$ prepared but did not resolve remains in `pg_prepared_xacts`. This is the *in-doubt* state. For each such $gid$:

1. $n$ identifies the coordinator from the prefix of $gid$ and sends it `GET /internal/2pc/status/:gid`.
2. $n$ acts on the decision it receives:
    - `commit`: $n$ runs `COMMIT PREPARED 'gid'`.
    - `abort`, or no log entry at all: $n$ runs `ROLLBACK PREPARED 'gid'`. This is the *presumed abort* rule: a coordinator with no record of a $gid$ never decided to commit it.
    - `started`: the coordinator has not decided yet, so $n$ waits and asks again.
3. If the coordinator cannot be reached, $n$ keeps the transaction prepared and retries periodically.

An $n$ in the in-doubt state must never decide on its own. It voted `YES`, so it cannot abort alone. It also cannot commit alone, because the coordinator may have decided to abort.

### Catch-up Replication

Strict 2PC aborts $T(q)$ whenever some $n \in P(q)$ is unreachable. To keep writes available while a node is down (specification Step 4), $N^*$ runs 2PC over the **reachable** participants only. A reachable participant that holds a copy of the rows the down node missed records the changes in its **replication log**. When the down node recovers, it pulls every entry after the last position it applied.

This is **log shipping**, the idea behind PostgreSQL streaming replication and replication slots. We implement it in the web app instead of using PostgreSQL's own mechanism for two reasons:

- Web apps never connect to another node's database (see [Node Communication](#node-communication)).
- A node's WAL describes changes to its own data pages, so it cannot be replayed on a node that holds a different fragment.

#### Writing While a Node Is Down

1. Before Phase 1, $N^*$ checks each $n \in P(q)$ with `GET /internal/health`. Let $D \subset P(q)$ be the nodes that are down.
2. If every row affected by $q$ still has at least one copy among the reachable participants, $N^*$ runs 2PC over $P(q) \setminus D$ and includes $D$ in every `PREPARE`. Otherwise it aborts.
3. For each $d \in D$, the reachable participants that hold copies of $d$'s rows log the changes $d$ needs:

    | Down node $d$ | Who logs for $d$                                       |
    | ------------- | ------------------------------------------------------ |
    | $A$ or $B$    | $C$, which holds every row                             |
    | $C$           | Each reachable leaf in $\text{frag}(q)$, for its own rows |

4. A participant writes its log entries in the same local transaction that applies $q$, before `PREPARE TRANSACTION`, so they commit or roll back together with $T(q)$.
5. Each entry is a **row image** $(seq, gid, dest, op, stop\_id, payload)$, where $payload$ is the row after the change (taken from `RETURNING`), or `NULL` for a delete. To apply an entry, the receiver upserts or deletes by `stop_id`.
6. While $C$ is down, $N^*$ aborts any `UPDATE` that moves a row across $s_0$. Such a move would be logged as a delete on one leaf and an insert on the other, and $C$ could replay the two logs in either order.

**Log order.** $seq$ must follow commit order. A `BIGSERIAL` value is assigned when the row is inserted, not when the transaction commits. Without care, a transaction holding $seq = 10$ could commit after one holding $seq = 11$, and a reader that had already moved past 11 would never see 10.

To prevent this, a participant that writes to the log first runs `LOCK TABLE replication_log IN EXCLUSIVE MODE`. The lock is held until `COMMIT PREPARED` or `ROLLBACK PREPARED`, so each node appends to its log one transaction at a time. Plain `SELECT`s on the log are not blocked. Writes are serialized this way only while some node is down.

#### Catching Up

Every node $d$ stores in `replication_position` the last $seq$ it applied from each **source**: $C$ for a leaf, and both $A$ and $B$ for $C$.

1. When $d$ restarts, `GET /internal/health` returns `503` until catch-up finishes. Other nodes therefore keep treating $d$ as down: they keep logging for it and do not send it 2PC requests that could overtake older logged changes. While catching up, $d$ also does not answer reads from its own data.
2. For each source $s$, $d$ calls `GET /internal/log?dest=d&after=p`, where $p$ is its position for $s$. $s$ responds with its entries for $d$ that have $seq > p$, in $seq$ order, up to a page limit.
3. In a single local transaction, $d$ applies each entry and sets its position for $s$ to that entry's $seq$. Because the data and the position move together, a crash during catch-up resumes at the right entry and never applies an entry twice.
4. $d$ repeats until every source returns an empty page, then reports healthy.
5. After that, $d$ keeps pulling periodically. This picks up entries logged by a coordinator that checked $d$'s health just before it came back.

**Retention.** The `after` parameter is $d$'s acknowledgement. When $s$ receives it, $s$ deletes its entries for $d$ with $seq \leq p$. This is the job a replication slot does in PostgreSQL: $s$ keeps exactly the entries $d$ has not yet confirmed.

#### Full Resync

If replaying the log cannot bring $d$ up to date, $d$ discards its copy of the affected rows and copies them again from the source. This happens when:

- an entry fails to apply, or
- $d$ has no row in `replication_position` for $s$ (for example, its volume was lost). Initial fragmentation sets every position to `0`, so a missing row is never normal.

To resync from $s$:

1. $d$ calls `GET /internal/snapshot?dest=d`. In one `REPEATABLE READ` transaction, $s$ reads:
    - the rows $d$ holds a copy of: $d$'s fragment if $d$ is a leaf, or $R_s$ if $d = C$;
    - $\max(seq)$ of its log entries for $d$.

    Reading both in one snapshot guarantees that every change is either already in the rows or comes after that $seq$.
2. In one local transaction, $d$ replaces those rows with the snapshot and sets its position for $s$ to that $seq$.
3. $d$ continues with normal catch-up from that $seq$.

A resync replaces only $d$'s copy of the rows that $s$ holds. $s_0$ does not change and no other node is touched. There is no refragmentation.

### Properties and Limitations

- **Atomicity:** either every reachable $n \in P(q)$ commits $T(q)$, or none of them does. Unreachable participants receive the write later through catch-up replication.
- **Consistency of fragmentation:** because $C \in P(q)$ for every write, $C$ and the owning leaf always end up applying the same set of writes.
- **Blocking:** a participant that voted `YES` holds its row locks until it learns the decision. If $N^*$ fails after Phase 1, those rows stay locked until $N^*$ recovers. This is the main limitation of 2PC.
- **Availability:** with catch-up replication, a write succeeds as long as each affected row has one reachable copy. A node that fails *during* a 2PC (after `PREPARE` is sent) still causes that transaction to abort. While $C$ is down, updates that move a row across $s_0$ are rejected.
- **Degraded throughput:** while any node is down, appends to the replication log are serialized, so writes on the logging node run one at a time.
- **Late log entries:** a coordinator can check $d$'s health just before $d$ reports healthy, then log an entry for $d$ after $d$'s last pull. If $d$ then receives a newer 2PC write to the same row, the periodic pull later applies the older row image over it. The window is small, and closing it fully would need per-row version numbers, which we do not implement.

## Implementation Details

### Initialization

Each node runs two Docker containers: a PostgreSQL database and a web app. Executing `docker compose up` creates 6 containers:

- Three PostgreSQL containers
- Three web app containers

We then perform health checks and connectivity checks for each node.

### Configuration

- **PostgreSQL** must be started with `max_prepared_transactions > 0`; the default of `0` disables `PREPARE TRANSACTION`. For example: `command: postgres -c max_prepared_transactions=100`.
- **Each web app** receives:
  - `SITE_ID`: its own node (`site1` = $C$, `site2` = $A$, `site3` = $B$).
  - `DB_HOST`: its **own** database only. Web apps never connect to another node's database.
  - `CENTRAL_SITE_URL`, `LEAF1_SITE_URL`, `LEAF2_SITE_URL`: the HTTP base URLs of all three web apps.

### Database Tables

Every node's database has the same tables:

| Table                  | Purpose                                                                                       |
| ---------------------- | --------------------------------------------------------------------------------------------- |
| `fact_stop`            | The data: all rows on $C$, one fragment on $A$ or $B$.                                        |
| `twopc_log`            | Coordinator log: $(gid, P(q), \text{state})$.                                                 |
| `replication_log`      | Row images of writes a down node missed: $(seq, gid, dest, op, stop\_id, payload)$. Entries are deleted once $dest$ acknowledges them. |
| `replication_position` | $(source, last\_seq)$: the last log entry this node applied from each source.                  |

## Questions and Resolutions

1. **What will be our fragmentation condition/predicate?**
   **Resolution**: we fragment horizontally on `station_code` with a split value $s_0$: rows with `station_code` $< s_0$ go to $A$ and the rest to $B$ (see [Horizontal Fragmentation](#horizontal-fragmentation)). Since `station_code` is `TEXT`, the comparison is lexicographic.
2. **How will the nodes communicate with one another?**
   **Resolution**: over HTTP with JSON bodies. Writes use two-phase commit (2PC), coordinated by the node that received the query.
3. **How do we prevent PK collisions on `INSERT`?**
   **Resolution**: *open.* Options include giving each coordinator a disjoint `stop_id` range, or encoding the coordinator's site in the ID.
4. **Which isolation level do we use for local transactions?**
   **Resolution**: *open.* It must be justified using the results from Hands-on Activity 3 (`isolation_levels/`).
5. **What is the concrete value of $s_0$?**
   **Resolution**: *open.* It will be computed by $C$ during initial fragmentation.
