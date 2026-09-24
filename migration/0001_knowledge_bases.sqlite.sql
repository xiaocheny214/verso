CREATE TABLE IF NOT EXISTS knowledge_bases (
    id CHAR(32) NOT NULL PRIMARY KEY,
    user_id CHAR(32) NOT NULL,
    name TEXT NOT NULL,
    embedding_model VARCHAR(128) NOT NULL DEFAULT '',
    collection VARCHAR(128) NOT NULL DEFAULT 'verso_chunks',
    storage_profile_id CHAR(32),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT knowledge_bases_user_name UNIQUE (user_id, name),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

ALTER TABLE user_articles
    ADD COLUMN knowledge_base_id CHAR(32);

INSERT OR IGNORE INTO knowledge_bases (id, user_id, name, embedding_model, collection)
SELECT lower(hex(randomblob(16))), user_id, 'Default', '', 'verso_chunks'
FROM user_articles
WHERE knowledge_base_id IS NULL
GROUP BY user_id;

UPDATE user_articles
SET knowledge_base_id = (
    SELECT id
    FROM knowledge_bases
    WHERE knowledge_bases.user_id = user_articles.user_id
      AND knowledge_bases.name = 'Default'
)
WHERE knowledge_base_id IS NULL;

CREATE TABLE user_articles__migration (
    id CHAR(32) NOT NULL PRIMARY KEY,
    user_id CHAR(32) NOT NULL,
    knowledge_base_id CHAR(32) NOT NULL,
    source_url TEXT NOT NULL,
    content_type VARCHAR(32) NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    object_key TEXT NOT NULL UNIQUE,
    content_hash VARCHAR(64),
    byte_size INTEGER,
    status VARCHAR(16) NOT NULL,
    error_class VARCHAR(64),
    fetched_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT user_articles_user_source_url UNIQUE (user_id, source_url),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases (id) ON DELETE RESTRICT
);

INSERT INTO user_articles__migration
    (id, user_id, knowledge_base_id, source_url, content_type, title, summary,
     object_key, content_hash, byte_size, status, error_class, fetched_at,
     created_at, updated_at)
SELECT id, user_id, knowledge_base_id, source_url, content_type, title, summary,
       object_key, content_hash, byte_size, status, error_class, fetched_at,
       created_at, updated_at
FROM user_articles;

DROP TABLE user_articles;

ALTER TABLE user_articles__migration
    RENAME TO user_articles;
