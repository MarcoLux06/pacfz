"""Shared path configuration for the pacfz toolset.

Every path honors the XDG base-directory variables and can additionally be
overridden with an environment variable. The overrides exist mainly so the
test suite (and unusual setups) can point the tools at a scratch database
without touching the user's real one:

    PACFZ_DB_PATH        cache DB built from `pacman -Qi`
                         (default: $XDG_CACHE_HOME/pacman_packages.db)
    PACFZ_NOTES_DB_PATH  per-package user notes DB
                         (default: $XDG_DATA_HOME/pacfz/user_data.db)
"""
import os

# version tag
__version__ = "1.0.6"


def _xdg(env_var: str, default: str) -> str:
    """Return $env_var if set, else the expanded default (e.g. ~/.cache)."""
    return os.environ.get(env_var) or os.path.expanduser(default)


def cache_db_path() -> str:
    """Path to the pacman package cache DB."""
    override = os.environ.get('PACFZ_DB_PATH')
    if override:
        return override
    return os.path.join(_xdg('XDG_CACHE_HOME', '~/.cache'), 'pacman_packages.db')


def notes_db_path() -> str:
    """Path to the user-notes DB."""
    override = os.environ.get('PACFZ_NOTES_DB_PATH')
    if override:
        return override
    return os.path.join(
        _xdg('XDG_DATA_HOME', '~/.local/share'), 'pacfz', 'user_data.db'
    )
