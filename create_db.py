import argparse
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set

from config import cache_db_path

# Constants
PACMAN_TIMEOUT = 30  # seconds
DB_TIMEOUT = 10  # seconds
DB_PATH = cache_db_path()

# logger is configured in main()
logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# pacman I/O
# ---------------------------------------------------------------------------
def get_foreign_packages(timeout: int = PACMAN_TIMEOUT) -> Set[str]:
    """Return the set of foreign (AUR) packages via `pacman -Qqm`.

    Raises:
        RuntimeError: if pacman fails or times out.
    """
    try:
        result = subprocess.run(
            ['pacman', '-Qqm'],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        if result.returncode not in (0, 1):  # 1 == no foreign packages
            raise RuntimeError(
                f"pacman -Qqm failed with code {result.returncode}: {result.stderr}"
            )
        if result.returncode == 1:
            logger.info("No foreign packages found")
            return set()

        foreign = set(result.stdout.strip().split('\n'))
        foreign.discard('')
        logger.info(f"Found {len(foreign)} foreign packages")
        return foreign
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"pacman -Qqm timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError("pacman command not found. This script must run on Arch Linux.")


def run_pacman_qi(timeout: int = PACMAN_TIMEOUT) -> str:
    """Return raw `pacman -Qi` output.

    Raises:
        RuntimeError: if pacman fails or times out.
    """
    try:
        result = subprocess.run(
            ['pacman', '-Qi'],
            capture_output=True, text=True, timeout=timeout, check=True,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"pacman -Qi timed out after {timeout}s")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pacman -Qi failed with code {e.returncode}: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("pacman command not found. This script must run on Arch Linux.")


def parse_qi_output(output: str) -> List[Dict[str, str]]:
    """Parse `pacman -Qi` text into a list of package dicts.

    This is pure (no I/O) so it can be unit-tested with crafted input — in
    particular the wrapped-field handling below.
    """
    packages: List[Dict[str, str]] = []
    package_blocks = output.strip().split('\n\n')

    if not package_blocks or not package_blocks[0]:
        raise RuntimeError("pacman -Qi returned empty output")

    for block_idx, block in enumerate(package_blocks):
        if not block.strip():
            continue

        lines = block.split('\n')
        current_package: Dict[str, str] = {}

        i = 0
        while i < len(lines):
            line = lines[i]
            # A new field is "Label   : value". pacman pads the label so there
            # is always whitespace before the ':' — a wrapped value fragment
            # like "libnotify: notifications" has no space before its colon and
            # therefore won't match here.
            match = re.match(r'^([^:]+?)\s+:\s?(.*)$', line)
            if match:
                label = match.group(1).strip().replace(' ', '_')
                value = match.group(2).strip()

                # Continuation lines are simply indented. We must NOT also test
                # for the absence of a colon: optional-dep descriptions
                # ("libnotify: desktop notifications") legitimately contain one,
                # and the old code dropped every such wrapped line.
                i += 1
                while i < len(lines) and lines[i][:1].isspace():
                    value += '\n' + lines[i].strip()
                    i += 1

                current_package[label] = value
            else:
                i += 1

        if current_package:
            if 'Name' not in current_package:
                logger.warning(
                    f"Skipping malformed package block {block_idx}: missing 'Name'"
                )
                continue
            packages.append(current_package)
        else:
            logger.info(f"Empty package data in block {block_idx}")

    logger.info(f"Parsed {len(packages)} packages from pacman -Qi")
    return packages


def parse_pacman_qi(timeout: int = PACMAN_TIMEOUT) -> List[Dict[str, str]]:
    """Run `pacman -Qi` and parse it. Raises RuntimeError on failure."""
    return parse_qi_output(run_pacman_qi(timeout))


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------
def convert_size_to_bytes(size_str: str) -> int:
    """Convert a size string (e.g. "2.34 MiB") to bytes.

    pacman formats numbers using the system locale, so on a machine set to a
    locale that uses a comma as the decimal separator (e.g. de_DE, fr_FR),
    `pacman -Qi` prints sizes like "56,72 KiB" instead of "56.72 KiB". Both
    are accepted here and normalized to a dot before parsing as a float.

    Raises:
        ValueError: if the format is invalid.
    """
    if not size_str or size_str == 'None':
        return 0

    size_str = size_str.strip()
    match = re.match(r'^([\d.,]+)\s*([KMGT]i?B|B)$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: '{size_str}'")

    number = float(match.group(1).replace(',', '.'))
    unit = match.group(2)
    units = {
        'B': 1,
        'KiB': 1024, 'KB': 1000,
        'MiB': 1024 ** 2, 'MB': 1000 ** 2,
        'GiB': 1024 ** 3, 'GB': 1000 ** 3,
        'TiB': 1024 ** 4, 'TB': 1000 ** 4,
    }
    return int(number * units.get(unit, 1))


# ---------------------------------------------------------------------------
# Database build
# ---------------------------------------------------------------------------
def ensure_db_directory(db_path: str) -> None:
    """Ensure the parent directory of ``db_path`` exists."""
    db_dir = os.path.dirname(db_path)
    if not db_dir:
        return
    try:
        Path(db_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Database directory ready: {db_dir}")
    except OSError as e:
        raise RuntimeError(f"Failed to create database directory {db_dir}: {e}")


def verify_database_integrity(db_path: str) -> int:
    """Run PRAGMA integrity_check and return the package count.

    Raises:
        RuntimeError: if the database is corrupted.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)
        try:
            result = conn.execute('PRAGMA integrity_check').fetchone()[0]
            if result != 'ok':
                raise RuntimeError(f"Database integrity check failed: {result}")
            count = conn.execute('SELECT COUNT(*) FROM packages').fetchone()[0]
        finally:
            conn.close()
        logger.info(f"Database integrity verified: {count} packages")
        return count
    except sqlite3.DatabaseError as e:
        raise RuntimeError(f"Database verification failed: {e}")


def _write_packages(target_path: str, packages: List[Dict[str, str]],
                    foreign_packages: Set[str]) -> int:
    """Create the packages table in ``target_path`` and insert rows.

    Returns the number of rows inserted. Raises RuntimeError on failure.
    """
    all_columns = sorted({col for pkg in packages for col in pkg.keys()})

    conn = sqlite3.connect(target_path, timeout=DB_TIMEOUT)
    conn.execute('PRAGMA cache_size=10000')
    cursor = conn.cursor()
    try:
        cursor.execute('BEGIN IMMEDIATE')
        cursor.execute('DROP TABLE IF EXISTS packages')

        columns_def = ', '.join(
            f'"{col}" INTEGER' if col == 'Installed_Size' else f'"{col}" TEXT'
            for col in all_columns
        )
        cursor.execute(
            f'CREATE TABLE packages ({columns_def}, "is_foreign" INTEGER, '
            f'PRIMARY KEY ("Name"))'
        )

        columns_with_foreign = all_columns + ['is_foreign']
        placeholders = ', '.join('?' for _ in columns_with_foreign)
        col_names = ', '.join(f'"{c}"' for c in columns_with_foreign)
        insert_sql = f'INSERT INTO packages ({col_names}) VALUES ({placeholders})'

        insert_count = 0
        for pkg_idx, package in enumerate(packages):
            values = []
            for col in all_columns:
                value = package.get(col, '')
                if col == 'Installed_Size':
                    try:
                        value = convert_size_to_bytes(value)
                    except ValueError as e:
                        logger.error(
                            f"Size conversion failed for "
                            f"{package.get('Name', 'unknown')}: {e}"
                        )
                        raise
                values.append(value)
            values.append(1 if package.get('Name', '') in foreign_packages else 0)
            cursor.execute(insert_sql, values)
            insert_count += 1

        conn.commit()
        logger.info(f"Database committed: {insert_count} packages inserted")
        return insert_count
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Failed to create database: {e}")
    finally:
        conn.close()


def create_database(db_path: str, *, packages: Optional[List[Dict[str, str]]] = None,
                    foreign_packages: Optional[Set[str]] = None,
                    verbose: bool = True) -> None:
    """Create the package cache DB.

    The DB is built in a temp file in the same directory and then atomically
    swapped into place with os.replace (M5): concurrent readers — e.g. the fzf
    preview pane during a ctrl-r refresh — only ever see the old complete file
    or the new complete file, never a half-built one.

    ``packages`` and ``foreign_packages`` can be supplied to bypass pacman
    (used by the tests); otherwise they're fetched live.

    Raises:
        RuntimeError: on any fatal error.
    """
    logger.info("Starting database creation")
    ensure_db_directory(db_path)

    if foreign_packages is None:
        foreign_packages = get_foreign_packages()
    if packages is None:
        packages = parse_pacman_qi()
    if not packages:
        raise RuntimeError("No packages found from pacman -Qi")

    all_columns = sorted({col for pkg in packages for col in pkg.keys()})
    if verbose:
        print(f"Found {len(packages)} packages with {len(all_columns)} unique fields.")
        print(f"Columns: {', '.join(all_columns)}\n")

    db_dir = os.path.dirname(db_path) or '.'
    fd, tmp_path = tempfile.mkstemp(prefix='.pkgdb-', suffix='.tmp', dir=db_dir)
    os.close(fd)

    try:
        insert_count = _write_packages(tmp_path, packages, foreign_packages)
        # Verify the freshly-built temp DB *before* swapping it in, so a corrupt
        # build can never replace a good cache.
        verify_database_integrity(tmp_path)
        os.replace(tmp_path, db_path)
        # Remove stale sidecars left by any previous WAL-mode DB at the
        # destination; they'd otherwise be misread as belonging to the new file.
        for ext in ('-wal', '-shm', '-journal'):
            try:
                os.remove(db_path + ext)
            except FileNotFoundError:
                pass
    except BaseException:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
        logger.error("Fatal error creating database; temp file cleaned up")
        raise

    if verbose:
        print(f"\u2713 Database created successfully: {db_path}")
        print(f"  Total packages inserted: {insert_count}")
        print(f"  Foreign packages marked: {len(foreign_packages)}")
    logger.info("Database creation completed successfully")


def display_packages(db_path: str, limit: int = 5, verbose: bool = True) -> None:
    """Print a small sample of packages for a sanity check."""
    if not verbose:
        return
    try:
        conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)
        rows = conn.execute(
            'SELECT Name, Version, Description, is_foreign FROM packages LIMIT ?',
            (limit,),
        ).fetchall()
        conn.close()
    except sqlite3.OperationalError as e:
        logger.error(f"Database read failed: {e}")
        print(f"Error reading database: {e}", file=sys.stderr)
        return

    if not rows:
        print("No packages found in database")
        return

    print(f"\nSample of {len(rows)} packages:")
    print(f"{'Name':<30} {'Version':<20} {'Description':<40} {'Foreign':<8}")
    print("-" * 100)
    for name, version, desc, foreign in rows:
        print(
            f"{(name or '')[:30]:<30} {(version or '')[:20]:<20} "
            f"{(desc or '')[:40]:<40} {('Yes' if foreign else 'No'):<8}"
        )


def main() -> None:
    global logger

    parser = argparse.ArgumentParser(
        usage=argparse.SUPPRESS,
        description="Create and maintain the pacman package database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="minimal output (WARNING level)")
    parser.add_argument("-p", "--path", help="database path")
    args = parser.parse_args()

    verbose = not args.quiet
    db_path = args.path or DB_PATH

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO if verbose else logging.WARNING)
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(handler)

    try:
        create_database(db_path, verbose=verbose)
        display_packages(db_path, 5, verbose)
    except Exception as e:
        logger.error(f"Script failed: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
