CREATE TABLE IF NOT EXISTS stop (
    stop_id         BIGINT PRIMARY KEY,
    rdt_id          BIGINT NOT NULL,
    arrival_time    TIMESTAMP,
    departure_time  TIMESTAMP,
    arrival_delay   INTEGER,
    departure_delay INTEGER,
    station_code    TEXT   NOT NULL
);

-- Catch-up replication, source side: row images of writes a down node missed.
-- Appends take LOCK TABLE replication_log IN EXCLUSIVE MODE (held until
-- COMMIT/ROLLBACK PREPARED) so that seq follows commit order.
CREATE TABLE IF NOT EXISTS replication_log (
    seq         BIGSERIAL   PRIMARY KEY,   -- pull order
    gid         TEXT        NOT NULL,      -- 2PC transaction that produced the change
    dest        TEXT        NOT NULL CHECK (dest IN ('site1', 'site2', 'site3')),
    op          TEXT        NOT NULL CHECK (op IN ('upsert', 'delete')),
    stop_id     BIGINT      NOT NULL,
    payload     JSONB,                     -- row after the change; NULL for delete
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((op = 'delete') = (payload IS NULL))
);  -- rows with seq <= p are DELETED when dest pulls with after = p

CREATE INDEX IF NOT EXISTS replication_log_dest_seq ON replication_log (dest, seq);

-- Catch-up replication, receiving side: last entry applied from each source.
-- Updated in the same transaction that applies the entry.
-- Initial fragmentation inserts a row with last_seq = 0 for every source;
-- a missing row means the node lost its data and must do a full resync.
CREATE TABLE IF NOT EXISTS replication_position (
    source      TEXT        PRIMARY KEY CHECK (source IN ('site1', 'site2', 'site3')),
    last_seq    BIGINT      NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2PC coordinator log (every site can coordinate, so every site has one)
CREATE TABLE IF NOT EXISTS twopc_log (
    gid          TEXT        PRIMARY KEY,   -- '<site_id>-<unique>', e.g. 'site3-1042'
    participants TEXT[]      NOT NULL,      -- e.g. {site1,site2}
    state        TEXT        NOT NULL CHECK (state IN ('started', 'commit', 'abort', 'done')),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
