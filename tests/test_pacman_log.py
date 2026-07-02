import pathlib

from pacman_log import LogEvent, parse_log_lines

FIXTURES = pathlib.Path(__file__).resolve().parent / 'fixtures'


def _events():
    with open(FIXTURES / 'pacman_sample.log') as f:
        return parse_log_lines(f)


def test_total_event_count():
    # 5 [PACMAN] command lines + 12 [ALPM] install/upgrade/remove lines.
    # Every ALPM-SCRIPTLET line, hook line, transaction marker, and
    # warning line in the fixture must be skipped.
    assert len(_events()) == 17


def test_noise_lines_skipped():
    events = _events()
    assert all(e.action != 'transaction' for e in events)
    assert not any('hook' in (e.command or '') for e in events)
    assert not any((e.command or '').startswith('warning') for e in events)


def test_installed_event():
    events = _events()
    blanket = next(e for e in events if e.name == 'blanket')
    assert blanket.action == 'installed'
    assert blanket.new_version == '0.8.0-3'
    assert blanket.old_version is None
    assert blanket.timestamp == '2026-07-01T17:31:30+0200'


def test_upgraded_event_splits_versions():
    events = _events()
    firefox = next(e for e in events if e.name == 'firefox')
    assert firefox.action == 'upgraded'
    assert firefox.old_version == '139.0-1'
    assert firefox.new_version == '140.0-1'


def test_removed_event():
    events = _events()
    removed = next(e for e in events if e.name == 'old-package')
    assert removed.action == 'removed'
    assert removed.new_version == '1.0-1'
    assert removed.old_version is None


def test_command_event():
    events = _events()
    commands = [e for e in events if e.action == 'command']
    assert len(commands) == 5
    assert any('pacman -S python-textual' == c.command for c in commands)
    assert any(c.command.startswith('pacman --sync -- extra/blanket') for c in commands)


def test_multi_package_transaction_all_captured():
    # The python-textual install pulled in 5 dependencies in one
    # transaction — every one of them must show up as its own event.
    events = _events()
    names = {e.name for e in events if e.action == 'installed'}
    for pkg in ('python-mdurl', 'python-markdown-it-py', 'python-rich',
                'python-uc-micro-py', 'python-linkify-it-py', 'python-textual'):
        assert pkg in names, pkg


def test_malformed_line_ignored():
    # Not matching the [TIMESTAMP] [SOURCE] pattern at all -> silently
    # skipped, not an error.
    events = parse_log_lines(['this is not a log line', 'nor is this'])
    assert events == []


def test_empty_input():
    assert parse_log_lines([]) == []


def test_read_log_respects_monkeypatched_default_path(monkeypatch):
    # Regression: read_log's default used to be captured once at def time
    # (`log_path: str = DEFAULT_LOG_PATH`), so reassigning the module-level
    # DEFAULT_LOG_PATH afterward silently had no effect. It must actually
    # take effect for tests (and any future caller) to point read_log() at
    # a different file without passing log_path explicitly every time.
    import pacman_log
    monkeypatch.setattr(pacman_log, 'DEFAULT_LOG_PATH', str(FIXTURES / 'pacman_sample.log'))
    events = pacman_log.read_log()
    assert len(events) == 17
