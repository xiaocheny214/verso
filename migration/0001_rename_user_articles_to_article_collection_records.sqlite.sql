-- user_articles already exists from the earlier ORM archive.
-- It is a Zhihu collection record, not a knowledge-base document.

ALTER TABLE user_articles RENAME TO article_collection_records;

ALTER TABLE article_collection_records
    RENAME COLUMN summary TO description;
