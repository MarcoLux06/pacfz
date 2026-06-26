"""Test setup: point every tool at scratch copies of the fixture databases.

We set the env overrides *before* the project modules are imported anywhere,
so their module-level DB_PATH / notes path constants pick up the scratch
locations. Tests therefore never touch a real ~/.cache or ~/.local/share DB.
"""
import os
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
FIXTURES = HERE / 'fixtures'

# Make the project modules importable.
sys.path.insert(0, str(ROOT))

# Scratch copies of the fixture DBs for this test session.
_TMP = tempfile.mkdtemp(prefix='pacfz-test-')
_CACHE_DB = os.path.join(_TMP, 'packages.db')
_NOTES_DB = os.path.join(_TMP, 'notes.db')
shutil.copy(FIXTURES / 'packages.db', _CACHE_DB)
shutil.copy(FIXTURES / 'notes.db', _NOTES_DB)

os.environ['PACFZ_DB_PATH'] = _CACHE_DB
os.environ['PACFZ_NOTES_DB_PATH'] = _NOTES_DB

import pytest  # noqa: E402


@pytest.fixture
def cache_db():
    return _CACHE_DB


@pytest.fixture
def notes_db_path_fixture():
    return _NOTES_DB


@pytest.fixture
def project_root():
    return ROOT


@pytest.fixture
def fresh_notes_db():
    """A path to a notes DB that does not exist yet (for create/empty tests)."""
    d = tempfile.mkdtemp(prefix='pacfz-notes-')
    return os.path.join(d, 'sub', 'user_data.db')
