import sqlite3
import subprocess
import re
import os
import sys
from typing import Dict, List, Set
import argparse
import logging
from pathlib import Path

# Constants
PACMAN_TIMEOUT = 30  # seconds
DB_TIMEOUT = 10  # seconds
DB_PATH = os.path.expanduser('~/.cache/pacman_packages.db')

# logger will be defined in main()
logger: logging.Logger


def get_foreign_packages(timeout: int = PACMAN_TIMEOUT) -> Set[str]:
    """
    Get the set of foreign (AUR) packages using 'pacman -Qqm'.

    Args:
        timeout: Command timeout in seconds

    Raises:
        RuntimeError: If pacman fails or times out
    """
    try:
        result = subprocess.run(
            ['pacman', '-Qqm'],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )

        if result.returncode not in (0, 1):  # 1 is OK (no foreign packages)
            raise RuntimeError(f"pacman -Qqm failed with code {result.returncode}: {result.stderr}")

        if result.returncode == 1:
            logger.info("No foreign packages found")
            return set()

        foreign_packages = set(result.stdout.strip().split('\n'))
        foreign_packages.discard('')
        logger.info(f"Found {len(foreign_packages)} foreign packages")
        return foreign_packages

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"pacman -Qqm timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError("pacman command not found. This script must run on Arch Linux.")


def parse_pacman_qi(timeout: int = PACMAN_TIMEOUT) -> List[Dict[str, str]]:
    """
    Parse output from 'pacman -Qi' and return a list of package dictionaries.

    Args:
        timeout: Command timeout in seconds

    Raises:
        RuntimeError: If pacman fails, times out, or output is malformed
    """
    try:
        result = subprocess.run(
            ['pacman', '-Qi'],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True
        )
        output = result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"pacman -Qi timed out after {timeout}s")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pacman -Qi failed with code {e.returncode}: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("pacman command not found. This script must run on Arch Linux.")

    packages = []
    package_blocks = output.strip().split('\n\n')

    if not package_blocks or not package_blocks[0]:
        raise RuntimeError("pacman -Qi returned empty output")

    for block_idx, block in enumerate(package_blocks):
        if not block.strip():
            continue

        lines = block.split('\n')
        current_package = {}

        i = 0
        while i < len(lines):
            line = lines[i]

            # Match lines with format "Label            : Value"
            match = re.match(r'^([^:]+?)\s+:\s(.*)$', line)
            if match:
                label = match.group(1).strip()
                label = label.replace(' ', '_')
                value = match.group(2).strip()

                # Handle multi-line values (continuation lines)
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    if next_line and next_line[0].isspace() and ':' not in next_line.split('\n')[0]:
                        value += '\n' + next_line.strip()
                        i += 1
                    else:
                        break

                current_package[label] = value
            else:
                i += 1

        if current_package:
            # Validate that Name field exists
            if 'Name' not in current_package:
                logger.warning(f"Skipping malformed package block {block_idx}: missing 'Name' field")
                continue
            packages.append(current_package)
        else:
            logger.info(f"Empty package data in block {block_idx}")

    logger.info(f"Parsed {len(packages)} packages from pacman -Qi")
    return packages


def convert_size_to_bytes(size_str: str) -> int:
    """
    Convert size string (e.g., "2.34 MiB", "1929.95 KiB") to bytes as integer.

    Raises:
        ValueError: If size_str format is invalid
    """
    if not size_str or size_str == 'None':
        return 0

    size_str = size_str.strip()

    # Extract number and unit
    match = re.match(r'^([\d.]+)\s*([KMGT]i?B|B)$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: '{size_str}'")

    number = float(match.group(1))
    unit = match.group(2)

    units = {
        'B': 1,
        'KiB': 1024,
        'KB': 1000,
        'MiB': 1024 ** 2,
        'MB': 1000 ** 2,
        'GiB': 1024 ** 3,
        'GB': 1000 ** 3,
        'TiB': 1024 ** 4,
        'TB': 1000 ** 4,
    }

    multiplier = units.get(unit, 1)
    return int(number * multiplier)


def ensure_db_directory(db_path: str) -> None:
    """
    Ensure parent directory exists with proper permissions.

    Raises:
        RuntimeError: If directory cannot be created
    """
    db_dir = os.path.dirname(db_path)
    if not db_dir:
        return

    try:
        Path(db_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Database directory ready: {db_dir}")
    except OSError as e:
        raise RuntimeError(f"Failed to create database directory {db_dir}: {e}")


def verify_database_integrity(db_path: str) -> None:
    """
    Verify database integrity after creation.

    Raises:
        RuntimeError: If database is corrupted
    """
    try:
        conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)
        cursor = conn.cursor()

        # Run integrity check
        cursor.execute('PRAGMA integrity_check')
        result = cursor.fetchone()[0]

        if result != 'ok':
            raise RuntimeError(f"Database integrity check failed: {result}")

        # Verify table structure
        cursor.execute("SELECT COUNT(*) FROM packages")
        count = cursor.fetchone()[0]

        conn.close()
        logger.info(f"Database integrity verified: {count} packages")

    except sqlite3.DatabaseError as e:
        raise RuntimeError(f"Database verification failed: {e}")


def create_database(input_db_path: str, verbose: bool = True) -> None:
    """
    Create SQLite database with pacman package information.

    Raises:
        RuntimeError: On any fatal error (subprocess, I/O, database)
    """
    logger.info("Starting database creation")

    # Ensure directory exists
    ensure_db_directory(input_db_path)

    try:
        # Get package data
        foreign_packages = get_foreign_packages()
        packages = parse_pacman_qi()

        if not packages:
            raise RuntimeError("No packages found from pacman -Qi")

        # Get all unique column names
        all_columns = set()
        for package in packages:
            all_columns.update(package.keys())

        all_columns = sorted(all_columns)

        if verbose:
            print(f"Found {len(packages)} packages with {len(all_columns)} unique fields.")
            print(f"Columns: {', '.join(all_columns)}\n")

        # Connect to database with WAL mode for concurrent access safety
        conn = sqlite3.connect(input_db_path, timeout=DB_TIMEOUT)

        # Enable WAL mode for safer concurrent access
        conn.execute('PRAGMA journal_mode=WAL')
        # Increase cache size for better performance
        conn.execute('PRAGMA cache_size=10000')

        cursor = conn.cursor()

        try:
            # Start transaction
            cursor.execute('BEGIN IMMEDIATE')

            # Drop existing table if it exists
            cursor.execute('DROP TABLE IF EXISTS packages')

            # Create table with appropriate column types
            columns_def_list = []
            for col in all_columns:
                if col == 'Installed_Size':
                    columns_def_list.append(f'"{col}" INTEGER')
                else:
                    columns_def_list.append(f'"{col}" TEXT')

            columns_def_list.append('"is_foreign" INTEGER')

            columns_def = ', '.join(columns_def_list)
            create_table_sql = f'''
                CREATE TABLE packages (
                    {columns_def},
                    PRIMARY KEY ("Name")
                )
            '''
            cursor.execute(create_table_sql)

            # Insert data
            all_columns_with_foreign = sorted(all_columns) + ['is_foreign']
            placeholders = ', '.join(['?' for _ in all_columns_with_foreign])
            col_names = ', '.join([f'"{col}"' for col in all_columns_with_foreign])
            insert_sql = f'INSERT INTO packages ({col_names}) VALUES ({placeholders})'

            insert_count = 0
            for pkg_idx, package in enumerate(packages):
                try:
                    values = []
                    for col in sorted(all_columns):
                        value = package.get(col, '')
                        if col == 'Installed_Size':
                            try:
                                value = convert_size_to_bytes(value)
                            except ValueError as e:
                                logger.error(f"Size conversion failed for {package.get('Name', 'unknown')}: {e}")
                                raise
                        values.append(value)

                    package_name = package.get('Name', '')
                    is_foreign = 1 if package_name in foreign_packages else 0
                    values.append(is_foreign)

                    cursor.execute(insert_sql, values)
                    insert_count += 1

                except Exception as e:
                    logger.error(f"Failed to insert package {pkg_idx}: {e}")
                    raise

            # Commit transaction
            conn.commit()
            logger.info(f"Database committed: {insert_count} packages inserted")

        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction failed, rolling back: {e}")
            raise RuntimeError(f"Failed to create database: {e}")
        finally:
            conn.close()

        # Verify database integrity
        verify_database_integrity(input_db_path)

        print(f"✓ Database created successfully: {input_db_path}")
        print(f"  Total packages inserted: {insert_count}")
        print(f"  Foreign packages marked: {len(foreign_packages)}")
        logger.info(f"Database creation completed successfully")

    except Exception as e:
        logger.error(f"Fatal error creating database: {e}")
        raise


def display_packages(input_db_path: str, limit: int = 5, verbose: bool = True) -> None:
    """
    Display sample packages from the database.
    """
    if not verbose:
        return

    try:
        conn = sqlite3.connect(input_db_path, timeout=DB_TIMEOUT)
        cursor = conn.cursor()

        cursor.execute('SELECT Name, Version, Description, is_foreign FROM packages LIMIT ?', (limit,))
        rows = cursor.fetchall()

        if not rows:
            print("No packages found in database")
            return

        print(f"\nSample of {len(rows)} packages:")
        print(f"{'Name':<30} {'Version':<20} {'Description':<40} {'Foreign':<8}")
        print("-" * 100)

        for row in rows:
            name = row[0][:30] if row[0] else ""
            version = row[1][:20] if row[1] else ""
            desc = row[2][:40] if row[2] else ""
            foreign = "Yes" if row[3] else "No"
            print(f"{name:<30} {version:<20} {desc:<40} {foreign:<8}")

        conn.close()

    except sqlite3.OperationalError as e:
        logger.error(f"Database read failed: {e}")
        print(f"Error reading database: {e}", file=sys.stderr)


def main() -> None:
    global logger

    # parse arguments
    parser = argparse.ArgumentParser(
        usage=argparse.SUPPRESS,
        description="Create and maintain pacman package database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="minimal output (WARNING level)")
    parser.add_argument("-p", "--path", help="Database path")
    args = parser.parse_args()

    # overwrite values based on given arguments
    verbose = not args.quiet
    db_path = args.path or DB_PATH

    # configure logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stderr)
    console_level = logging.INFO if verbose else logging.WARNING
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(console_handler)

    try:
        create_database(db_path, verbose)
        display_packages(db_path, 5, verbose)
    except Exception as e:
        logger.error(f"Script failed: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
