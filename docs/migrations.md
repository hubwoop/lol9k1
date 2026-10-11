# Database migrations

The schema is versioned. Every change to it is a migration in
[`lol9k1/migrations/`](../lol9k1/migrations), and `flask db upgrade` brings a
database to the latest version. The Docker image runs it on every start, so
deploying a new image is all it takes to roll out a schema change.

## How it works

- Migrations are plain SQL files named `NNNN_description.sql`, numbered
  consecutively from `0001`. They run in order and only forward.
- A database's version is the number of the last migration applied to it,
  stored in SQLite's [`PRAGMA user_version`](https://www.sqlite.org/pragma.html#pragma_user_version).
  `flask db status` shows it along with the pending migrations.
- Each migration runs in its own transaction together with its version bump.
  If it fails, it is rolled back, the database stays at the previous version
  and the container does not start.
- Before migrating an existing database, a snapshot `lol9k1.db.v<version>-<timestamp>.bak`
  is written next to it. The newest three are kept.
- A database that is *newer* than the code (after rolling back to an older
  image) is left untouched, and the app starts anyway.
- Databases created by `init-db` before migrations existed have no version.
  They are recognized by their schema and stamped with version 1 or 2.
- `flask init-db` is an alias for `flask db upgrade`, so it is safe to run on
  an existing database.

## Adding a migration

1. Add the next file, e.g. `lol9k1/migrations/0003_games_cover_url.sql`.
2. Run `flask db upgrade` locally and adapt the code.
3. Run the tests. The e2e tests build their database from the migrations.

Never edit a migration that has been released. Every database that already
ran it would silently disagree with every new one. Fix it with a new migration.

Don't put `begin`/`commit` in a migration, the runner wraps it in a transaction.
Foreign key enforcement is off while migrating, so tables can be rebuilt.

## Writing migrations that are safe to deploy continuously

The new schema has to work with the code that is running *before* the
deployment, and with the old image if the deployment is rolled back.
So every migration should be backwards compatible:

- **Fine:** adding a table, adding a nullable column or one with a default,
  adding an index.
- **Needs two releases (expand/contract):** renaming or dropping a column or
  table, adding a `not null` constraint, changing a column's meaning.
  1. *Expand:* add the new structure, write to both, read from the new one.
     Backfill existing rows in the same migration.
  2. *Contract:* once that release has been running for a while and no rollback
     to before it is expected, drop the old structure in a later migration.

SQLite cannot alter most constraints in place. Rebuild the table instead:
create `new_x`, `insert into new_x select … from x`, `drop table x`,
`alter table new_x rename to x`, then recreate its indexes
(see [SQLite: making other kinds of table schema changes](https://www.sqlite.org/lang_altertable.html#otheralter)).

## Restoring

Rolling back a migration means restoring a snapshot. Stop the app, copy the
`.bak` file over `lol9k1.db` and start an image that matches its version.
