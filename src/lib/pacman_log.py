"""Parses /var/log/pacman.log into structured events.

This deliberately reads pacman's own built-in log rather than maintaining a
separate history table — see the project's design notes: it's the
authoritative source (pacman already writes it, so pacfz invents no new
tracking), at the cost of being bounded by whatever pacman.log rotation
policy is in effect on the machine.

Kept as pure, testable functions (parse_log_lines) separate from the actual
file read (read_log), same pattern as create_db.py's run_pacman_qi() /
parse_qi_output() split — so the parsing logic can be tested against
captured real log fixtures without needing a live pacman.log on disk.
"""
import re
from dataclasses import dataclass
from typing import Iterator, List, Optional

DEFAULT_LOG_PATH = "/var/log/pacman.log"

# Real captured pacman.log lines look like:
#   [2026-07-01T17:31:30+0200] [ALPM] installed blanket (0.8.0-3)
#   [2026-07-01T17:31:30+0200] [ALPM] upgraded firefox (139.0-1 -> 140.0-1)
#   [2026-06-15T09:00:05+0200] [ALPM] removed old-package (1.0-1)
#   [2026-07-01T17:31:28+0200] [PACMAN] Running 'pacman --sync -- extra/blanket'
#
# Deliberately skipped (verified against a real log, not guessed):
#   [ALPM-SCRIPTLET] ...        - install-script output, often locale/perl
#                                  warning noise, sometimes hundreds of lines
#                                  per package
#   [ALPM] running '...hook'... - hook execution, not a package event
#   [ALPM] transaction started/completed
#   [ALPM] warning: ...          - pacnew/permission notices, not events
LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s+\[(?P<source>ALPM|PACMAN)\]\s+(?P<rest>.*)$"
)
EVENT_RE = re.compile(
    r"^(?P<action>installed|upgraded|removed)\s+(?P<name>\S+)\s+"
    r"\((?P<versions>.+)\)$"
)
COMMAND_RE = re.compile(r"^Running\s+'(?P<command>.*)'$")


@dataclass(frozen=True)
class LogEvent:
    timestamp: str  # raw string, e.g. "2026-07-01T17:31:30+0200"
    action: str  # 'installed' | 'upgraded' | 'removed' | 'command'
    name: Optional[str] = None  # package name, for install/upgrade/remove
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    command: Optional[str] = None  # raw command string, for action='command'


def _parse_versions(action: str, versions: str):
    if action == "upgraded" and "->" in versions:
        old, new = (v.strip() for v in versions.split("->", 1))
        return old, new
    # installed / removed only ever have one version in the parens
    return None, versions.strip()


def parse_log_lines(lines: Iterator[str]) -> List[LogEvent]:
    """Parse an iterable of raw pacman.log lines into LogEvents.

    Pure — takes any iterable of strings, so it can be tested against a
    captured log fixture or fed a live file handle without duplicating
    logic between the two.
    """
    events: List[LogEvent] = []
    for line in lines:
        line = line.rstrip("\n")
        match = LINE_RE.match(line)
        if not match:
            continue

        ts = match.group("ts")
        source = match.group("source")
        rest = match.group("rest")

        if source == "ALPM":
            event_match = EVENT_RE.match(rest)
            if not event_match:
                continue  # transaction started/completed, hooks, warnings, etc.
            action = event_match.group("action")
            name = event_match.group("name")
            old_version, new_version = _parse_versions(
                action, event_match.group("versions")
            )
            events.append(LogEvent(
                timestamp=ts, action=action, name=name,
                old_version=old_version, new_version=new_version,
            ))
        elif source == "PACMAN":
            cmd_match = COMMAND_RE.match(rest)
            if not cmd_match:
                continue
            events.append(LogEvent(
                timestamp=ts, action="command", command=cmd_match.group("command"),
            ))

    return events


def read_log(log_path: Optional[str] = None) -> List[LogEvent]:
    """Read and parse the real pacman.log.

    ``log_path`` defaults to DEFAULT_LOG_PATH, resolved at call time (not at
    def time) so tests can monkeypatch the module-level DEFAULT_LOG_PATH and
    have it actually take effect.

    Raises:
        OSError: if the log can't be read (missing, permissions, etc.) —
            callers decide how to present that (e.g. the History screen
            shows a message rather than crashing).
    """
    if log_path is None:
        log_path = DEFAULT_LOG_PATH
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        return parse_log_lines(f)
