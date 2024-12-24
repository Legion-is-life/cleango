DROP TABLE IF EXISTS deleted_torrents;
CREATE TABLE deleted_torrents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    tracker_message TEXT NOT NULL,
    deletion_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
