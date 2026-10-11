"""Schema migrations, see lol9k1/migrate.py."""
import sqlite3
from pathlib import Path

import pytest

from lol9k1 import migrate

MIGRATIONS = migrate.load_migrations()
LATEST = len(MIGRATIONS)


def quiet(*_):
    pass


def version_of(db_path: Path) -> int:
    with sqlite3.connect(db_path) as db:
        return migrate.current_version(db)


def schema_of(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as db:
        tables = [row[0] for row in db.execute(
            "select name from sqlite_master where type = 'table' and name not like 'sqlite_%' order by name")]
        return {table: [tuple(column) for column in db.execute(f'pragma table_info({table})')]
                for table in tables}


def unversioned_db(db_path: Path, up_to: int) -> Path:
    """A database as created by ``init-db`` before migrations existed: tables, but no version."""
    with sqlite3.connect(db_path) as db:
        for migration in MIGRATIONS[:up_to]:
            db.executescript(migration.sql())
    assert version_of(db_path) == 0
    return db_path


def add_user_and_game(db_path: Path) -> None:
    with sqlite3.connect(db_path) as db:
        db.execute("insert into invites (token, used, added_by) values ('t1', 1, 0)")
        db.execute("insert into users (name, password, token_used) values ('alice', 'x', 't1')")
        db.execute("insert into games (name, slug, added_by) values ('Quake', 'quake', 1)")


def test_new_database_is_migrated_to_latest_version(tmp_path):
    db_path = tmp_path / 'new.db'

    result = migrate.upgrade(db_path, log=quiet)

    assert result.from_version == 0
    assert [m.version for m in result.applied] == list(range(1, LATEST + 1))
    assert result.backup is None
    assert version_of(db_path) == LATEST
    assert 'admin' in [column[1] for column in schema_of(db_path)['invites']]


def test_upgrade_is_idempotent(tmp_path):
    db_path = tmp_path / 'db.db'
    migrate.upgrade(db_path, log=quiet)

    result = migrate.upgrade(db_path, log=quiet)

    assert result.applied == []
    assert result.backup is None
    assert version_of(db_path) == LATEST


@pytest.mark.parametrize('legacy_version', [1, 2])
def test_unversioned_database_is_stamped_and_keeps_its_data(tmp_path, legacy_version):
    db_path = unversioned_db(tmp_path / 'legacy.db', up_to=legacy_version)
    add_user_and_game(db_path)

    result = migrate.upgrade(db_path, log=quiet)

    assert result.from_version == legacy_version
    assert [m.version for m in result.applied] == list(range(legacy_version + 1, LATEST + 1))
    assert version_of(db_path) == LATEST
    migrate.upgrade(tmp_path / 'fresh.db', log=quiet)
    assert schema_of(db_path) == schema_of(tmp_path / 'fresh.db')
    with sqlite3.connect(db_path) as db:
        assert db.execute('select name from users').fetchall() == [('alice',)]
        assert db.execute('select admin from invites').fetchall() == [(0,)]


def test_unversioned_database_with_unknown_tables_is_refused(tmp_path):
    db_path = tmp_path / 'other.db'
    with sqlite3.connect(db_path) as db:
        db.execute('create table something_else (id integer)')

    with pytest.raises(migrate.MigrationError, match='unknown tables'):
        migrate.upgrade(db_path, log=quiet)
    assert version_of(db_path) == 0


def write_migrations(directory: Path, *scripts: str) -> list[migrate.Migration]:
    directory.mkdir()
    for version, script in enumerate(scripts, start=1):
        (directory / f'{version:04d}_step{version}.sql').write_text(script)
    return migrate.load_migrations(directory)


def test_failing_migration_is_rolled_back(tmp_path):
    db_path = tmp_path / 'db.db'
    migrations = write_migrations(
        tmp_path / 'migrations',
        'create table invites (token text);',
        "insert into invites values ('a');\n"
        'alter table invites add column admin integer;\n'
        'this is not sql;',
    )
    migrate.upgrade(db_path, migrations[:1], log=quiet)

    with pytest.raises(migrate.MigrationError, match='0002_step2.sql failed, database left at version 1'):
        migrate.upgrade(db_path, migrations, log=quiet)

    assert version_of(db_path) == 1
    with sqlite3.connect(db_path) as db:
        assert db.execute('select count(*) from invites').fetchone()[0] == 0
        assert [row[1] for row in db.execute('pragma table_info(invites)')] == ['token']


def test_existing_database_is_backed_up_before_migrating(tmp_path):
    db_path = tmp_path / 'db.db'
    migrations = write_migrations(
        tmp_path / 'migrations',
        "create table invites (token text); insert into invites values ('before');",
        'drop table invites;',
    )
    migrate.upgrade(db_path, migrations[:1], log=quiet)

    result = migrate.upgrade(db_path, migrations, log=quiet)

    assert result.backup.name.startswith('db.db.v1-')
    with sqlite3.connect(result.backup) as backup:
        assert migrate.current_version(backup) == 1
        assert backup.execute('select token from invites').fetchall() == [('before',)]


def test_only_the_newest_backups_are_kept(tmp_path):
    db_path = tmp_path / 'db.db'
    migrations = write_migrations(tmp_path / 'migrations', *['create table invites (token text);'] +
                                  [f'create table t{i} (id integer);' for i in range(5)])
    for version in range(1, len(migrations) + 1):
        migrate.upgrade(db_path, migrations[:version], log=quiet)

    backups = sorted(path.name.split('-')[0] for path in tmp_path.glob('db.db.v*.bak'))
    assert backups == ['db.db.v3', 'db.db.v4', 'db.db.v5']


def test_database_newer_than_the_code_is_left_untouched(tmp_path):
    """Rolling back to an older image must not fail on a schema it does not know yet."""
    db_path = tmp_path / 'db.db'
    migrate.upgrade(db_path, log=quiet)
    with sqlite3.connect(db_path) as db:
        db.execute(f'pragma user_version = {LATEST + 1}')

    result = migrate.upgrade(db_path, log=quiet)

    assert result.ahead
    assert result.applied == []
    assert version_of(db_path) == LATEST + 1


def test_status_reports_pending_migrations(tmp_path):
    db_path = unversioned_db(tmp_path / 'legacy.db', up_to=1)

    assert migrate.status(db_path) == (1, MIGRATIONS[1:])
    assert migrate.status(tmp_path / 'missing.db') == (0, MIGRATIONS)
    assert not (tmp_path / 'missing.db').exists()


@pytest.mark.parametrize('names, error', [
    (['0001_a.sql', '0003_c.sql'], 'expected 0002'),
    (['0001_a.sql', '0001_b.sql'], 'expected 0002'),
    (['1_a.sql'], 'Invalid migration file name'),
])
def test_migration_files_must_be_numbered_consecutively(tmp_path, names, error):
    for name in names:
        (tmp_path / name).write_text('')

    with pytest.raises(migrate.MigrationError, match=error):
        migrate.load_migrations(tmp_path)
