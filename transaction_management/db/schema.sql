CREATE TABLE IF NOT EXISTS fact_stop (
    stop_id         BIGINT PRIMARY KEY,
    rdt_id          BIGINT NOT NULL,
    arrival_time    SMALLINT,
    departure_time  SMALLINT,
    arrival_delay   INTEGER,
    departure_delay INTEGER,
    station_code    TEXT   NOT NULL
);

-- Persistent messaging, sending site (Silberschatz 19.33)
CREATE TABLE IF NOT EXISTS messages_to_send (
    message_id  TEXT        PRIMARY KEY,   -- unique: e.g. '<node_id>-<seq>'
    seq         BIGSERIAL,                 -- send order
    destination TEXT        NOT NULL,      -- 'node1' | 'node2' | 'node3'
    op          TEXT        NOT NULL CHECK (op IN ('insert', 'update', 'delete')),
    stop_id     BIGINT      NOT NULL,
    payload     JSONB,                     -- row after the change; NULL for delete
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);  -- a row is DELETED once the destination acknowledges it

-- Persistent messaging, receiving site (Silberschatz 19.34)
CREATE TABLE IF NOT EXISTS received_messages (
    message_id  TEXT        PRIMARY KEY,   -- duplicates are ignored, then acknowledged
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2PC coordinator log (every site can coordinate, so every site has one)
CREATE TABLE IF NOT EXISTS twopc_log (
    gid          TEXT        PRIMARY KEY,   -- '<site_id>-<unique>', e.g. 'site3-1042'
    participants TEXT[]      NOT NULL,      -- e.g. {site1,site2}
    state        TEXT        NOT NULL CHECK (state IN ('started', 'commit', 'abort', 'done')),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
