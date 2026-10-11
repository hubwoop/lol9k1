"""
Versioned, forward-only schema migrations.

Migrations are the files ``migrations/NNNN_description.sql``, applied in order.
The version of a database is the number of the last migration applied to it,
stored in SQLite's ``PRAGMA user_version`` (0 for a new, empty database).
Each migration runs in its own transaction together with its version bump,
so a failing migration leaves the database at the previous version.

See docs/migrations.md for how to write migrations that are safe to deploy.
"""
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / 'migrations'
BACKUPS_TO_KEEP = 3

_FILENAME = re.compile(r'^(\d{4})_(\w+)\.sql$')


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    def sql(self) -> str:
        return self.path.read_text()


def load_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations = []
    for path in sorted(directory.iterdir()):
        if path.suffix != '.sql':
            continue
        match = _FILENAME.match(path.name)
        if not match:
            raise MigrationError(f'Invalid migration file name: {path.name} (expected NNNN_description.sql)')
        migrations.append(Migration(version=int(match[1]), name=match[2], path=path))
    for expected, migration in enumerate(migrations, start=1):
        if migration.version != expected:
            raise MigrationError(f'Migration versions must be consecutive, expected {expected:04d} '
                                 f'but found {migration.path.name}')
    return migrations


def current_version(db: sqlite3.Connection) -> int:
    return db.execute('pragma user_version').fetchone()[0]


def _tables(db: sqlite3.Connection) -> set[str]:
    rows = db.execute("select name from sqlite_master where type = 'table' and name not like 'sqlite_%'")
    return {row[0] for row in rows}


def _legacy_version(db: sqlite3.Connection) -> int:
    """
    Databases created by ``init-db`` before migrations existed have tables but
    no version. Returns the migration their schema corresponds to, 0 if empty.
    """
    tables = _tables(db)
    if not tables:
        return 0
    if 'invites' not in tables:
        raise MigrationError(f'Unversioned database with unknown tables {sorted(tables)}, refusing to migrate')
    invite_columns = {row[1] for row in db.execute('pragma table_info(invites)')}
    return 2 if 'admin' in invite_columns else 1


def _backup(db: sqlite3.Connection, db_path: Path, version: int) -> Path:
    """Snapshots the database next to itself and prunes all but the newest snapshots."""
    backup_path = db_path.with_name(f'{db_path.name}.v{version}-{time.strftime("%Y%m%dT%H%M%S")}.bak')
    with sqlite3.connect(backup_path) as target:
        db.backup(target)
    target.close()
    backups = sorted(db_path.parent.glob(f'{db_path.name}.v*.bak'), key=lambda p: (p.stat().st_mtime, p.name))
    for old in backups[:-BACKUPS_TO_KEEP]:
        old.unlink()
    return backup_path


@dataclass(frozen=True)
class UpgradeResult:
    from_version: int
    to_version: int
    applied: list[Migration]
    backup: Path | None
    # the database is newer than this code, e.g. after rolling back the app
    ahead: bool = False


def upgrade(db_path: str | Path, migrations: list[Migration] | None = None, log=print) -> UpgradeResult:
    db_path = Path(db_path)
    migrations = load_migrations() if migrations is None else migrations
    latest = len(migrations)

    # autocommit mode: the transactions are opened and committed by the scripts below
    db = sqlite3.connect(db_path, isolation_level=None)
    try:
        version = current_version(db)
        if version == 0:
            version = _legacy_version(db)
            if version:
                log(f'Unversioned database matches migration {version:04d}, stamping it.')
                db.execute(f'pragma user_version = {version}')
        from_version = version

        if version > latest:
            log(f'Database is at version {version}, newer than the latest known migration {latest}. '
                'Leaving it untouched.')
            return UpgradeResult(from_version, version, [], None, ahead=True)

        pending = migrations[version:]
        backup = _backup(db, db_path, version) if pending and version > 0 else None
        if backup:
            log(f'Backed up database to {backup}')

        # Migrations that rebuild tables must not trigger foreign key actions.
        # Foreign keys are off by default, this keeps it that way. The pragma is
        # a no-op inside a transaction, so it has to be set here.
        db.execute('pragma foreign_keys = off')
        for migration in pending:
            log(f'Applying migration {migration.path.name}')
            try:
                # executescript() would commit a transaction opened by execute(),
                # so the whole transaction is part of the script
                db.executescript(f'begin immediate;\n{migration.sql()}\n;\n'
                                 f'pragma user_version = {migration.version};\ncommit;')
            except sqlite3.Error as e:
                if db.in_transaction:
                    db.execute('rollback')
                raise MigrationError(f'Migration {migration.path.name} failed, database left at '
                                     f'version {current_version(db)}: {e}') from e
        return UpgradeResult(from_version, latest, pending, backup)
    finally:
        db.close()


def status(db_path: str | Path, migrations: list[Migration] | None = None) -> tuple[int, list[Migration]]:
    """Returns the database version and the migrations still pending for it."""
    migrations = load_migrations() if migrations is None else migrations
    if not Path(db_path).exists():
        return 0, migrations
    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        version = current_version(db) or _legacy_version(db)
    finally:
        db.close()
    return version, migrations[version:]
