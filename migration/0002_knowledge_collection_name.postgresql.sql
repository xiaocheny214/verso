UPDATE knowledge_bases
SET collection = CASE
    WHEN name = 'Default' THEN 'default'
    ELSE 'kb_' || replace(id::text, '-', '')
END;

ALTER TABLE knowledge_bases
    ALTER COLUMN collection SET DEFAULT 'default';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'knowledge_bases_user_collection'
    ) THEN
        ALTER TABLE knowledge_bases
            ADD CONSTRAINT knowledge_bases_user_collection UNIQUE (user_id, collection);
    END IF;
END $$;
