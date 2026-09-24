UPDATE knowledge_bases
SET collection = CASE
    WHEN name = 'Default' THEN 'default'
    ELSE 'kb_' || replace(id, '-', '')
END;

CREATE UNIQUE INDEX IF NOT EXISTS knowledge_bases_user_collection
ON knowledge_bases (user_id, collection);
