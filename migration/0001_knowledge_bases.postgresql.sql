CREATE TABLE IF NOT EXISTS knowledge_bases (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    embedding_model VARCHAR(128) NOT NULL DEFAULT '',
    collection VARCHAR(128) NOT NULL DEFAULT 'verso_chunks',
    storage_profile_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT knowledge_bases_user_name UNIQUE (user_id, name)
);

ALTER TABLE user_articles
    ADD COLUMN IF NOT EXISTS knowledge_base_id UUID;

INSERT INTO knowledge_bases (id, user_id, name, embedding_model, collection)
SELECT md5(random()::text || clock_timestamp()::text || user_id::text)::uuid,
       user_id,
       'Default',
       '',
       'verso_chunks'
FROM user_articles
WHERE knowledge_base_id IS NULL
GROUP BY user_id
ON CONFLICT (user_id, name) DO NOTHING;

UPDATE user_articles
SET knowledge_base_id = knowledge_bases.id
FROM knowledge_bases
WHERE user_articles.user_id = knowledge_bases.user_id
  AND knowledge_bases.name = 'Default'
  AND user_articles.knowledge_base_id IS NULL;

ALTER TABLE user_articles
    ALTER COLUMN knowledge_base_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'user_articles_knowledge_base_id_fkey'
    ) THEN
        ALTER TABLE user_articles
            ADD CONSTRAINT user_articles_knowledge_base_id_fkey
            FOREIGN KEY (knowledge_base_id)
            REFERENCES knowledge_bases(id)
            ON DELETE RESTRICT;
    END IF;
END $$;
