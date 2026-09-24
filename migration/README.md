# Migrations

ORM models are the only definition of application tables. When `VERSO_CREATE_TABLES=true`, startup calls `Base.metadata.create_all` before any file in this directory.

SQL here only changes tables that already exist: add or alter columns, backfill rows, and add constraints that `create_all` will not apply to an existing table. Do not put `CREATE TABLE` for application tables in these files.

## Order

Each change is one version. Ship both dialect files together:

- `NNNN_action_table_column.postgresql.sql`
- `NNNN_action_table_column.sqlite.sql`

Name the version after the column or constraint change, for example `0001_rename_user_articles_to_article_collection_records`. Do not name it after a table the ORM creates.

`NNNN` is a zero-padded sequence. The runner loads `*.{dialect}.sql` in filename order and records the version stem (the name without the dialect suffix) in `schema_migrations`. A version already recorded is skipped.

A database with neither `user_articles` nor `article_collection_records` is treated as new. `create_all` builds the current schema, and every version is recorded without being executed. An existing `user_articles` table is renamed before `create_all`, so the new name is not created empty beside the old one.

## Startup

`create_all` runs first, then pending migrations. A migration may insert into a table the ORM just created, then alter an older table.
