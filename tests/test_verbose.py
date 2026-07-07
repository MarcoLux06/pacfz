import os
import subprocess
import sys


def run_list_raw(lib_dir, *args):
    """Run list_packages.py as a subprocess, returning the full
    CompletedProcess (stdout AND stderr) — --verbose's output goes to
    stderr, which the other test files' run_list() helper discards.
    """
    script = os.path.join(str(lib_dir), 'list_packages.py')
    return subprocess.run(
        [sys.executable, script, *args],
        capture_output=True, text=True, env=os.environ.copy(),
    )


def run_pacq_raw(project_root, *args):
    pacq = os.path.join(str(project_root), 'src', 'pacq')
    return subprocess.run(
        [pacq, *args], capture_output=True, text=True, env=os.environ.copy(),
    )


# ---------------------------------------------------------------------------
# list_packages.py --verbose
# ---------------------------------------------------------------------------
def test_verbose_prints_query_to_stderr_not_stdout(lib_dir):
    result = run_list_raw(lib_dir, '-e', '--verbose')
    assert result.returncode == 0, result.stderr
    assert '[verbose] query:' in result.stderr
    assert '[verbose] params:' in result.stderr
    # stdout must stay clean (just package names) — verbose output belongs
    # on stderr exclusively, so it never contaminates scriptable output.
    assert '[verbose]' not in result.stdout


def test_verbose_query_reflects_actual_filters(lib_dir):
    result = run_list_raw(lib_dir, '-e', '-m', '--verbose')
    assert result.returncode == 0, result.stderr
    assert "Install_Reason = 'Explicitly installed'" in result.stderr
    assert 'is_foreign = 1' in result.stderr


def test_verbose_off_by_default_no_stderr_noise(lib_dir):
    result = run_list_raw(lib_dir, '-e')
    assert result.returncode == 0, result.stderr
    assert '[verbose]' not in result.stderr


def test_verbose_with_totalsize_prints_the_summing_query(lib_dir):
    result = run_list_raw(lib_dir, '-e', '-t', '--verbose')
    assert result.returncode == 0, result.stderr
    assert '[verbose] query:' in result.stderr
    assert 'SUM(' in result.stderr
    assert "Install_Reason = 'Explicitly installed'" in result.stderr
    # the actual total must still print normally on stdout
    assert 'GiB' in result.stdout or 'MiB' in result.stdout or 'KiB' in result.stdout


def test_verbose_does_not_change_actual_results(lib_dir):
    # --verbose must be purely additive (extra stderr output) and never
    # change what's actually returned on stdout.
    plain = run_list_raw(lib_dir, '-e', '-m')
    verbose = run_list_raw(lib_dir, '-e', '-m', '--verbose')
    assert plain.stdout == verbose.stdout


# ---------------------------------------------------------------------------
# create_db.py's three verbosity states
# ---------------------------------------------------------------------------
SAMPLE_PACKAGES = [
    {
        'Name': 'firefox', 'Version': '1.0-1', 'Description': 'browser',
        'Install_Reason': 'Explicitly installed', 'Installed_Size': '2.34 MiB',
        'Required_By': 'None', 'Optional_For': 'None',
    },
]


def _run_create_db_main(lib_dir, tmp_path, extra_args):
    """Run create_db.py's real CLI as a subprocess against injected fake
    pacman output, so main()'s actual argument parsing/logging setup is
    exercised end-to-end rather than just calling create_database() directly.
    """
    fake_bin = tmp_path / 'fakebin'
    fake_bin.mkdir()
    fake_pacman = fake_bin / 'pacman'
    fake_pacman.write_text(
        '#!/bin/bash\n'
        'if [[ "$1" == "-Qi" ]]; then\n'
        '  echo "Name            : firefox"\n'
        '  echo "Version         : 1.0-1"\n'
        '  echo "Description     : browser"\n'
        '  echo "Install Reason  : Explicitly installed"\n'
        '  echo "Installed Size  : 2.34 MiB"\n'
        '  echo "Required By     : None"\n'
        '  echo "Optional For    : None"\n'
        'elif [[ "$1" == "-Qqm" ]]; then\n'
        '  exit 1\n'
        'fi\n'
    )
    fake_pacman.chmod(0o755)

    script = os.path.join(str(lib_dir), 'create_db.py')
    db_path = tmp_path / 'test.db'
    env = os.environ.copy()
    env['PATH'] = f"{fake_bin}:{env['PATH']}"
    return subprocess.run(
        [sys.executable, script, '--path', str(db_path), *extra_args],
        capture_output=True, text=True, env=env,
    )


def test_create_db_default_shows_summary_only(lib_dir, tmp_path):
    result = _run_create_db_main(lib_dir, tmp_path, [])
    assert result.returncode == 0, result.stderr
    assert 'Database created successfully' in result.stdout
    assert 'Total packages inserted' in result.stdout
    # Only the 3-line summary belongs in the default state — no INFO logs,
    # no sample table, and no "Found N packages.../Columns:" preview block
    # (that block is noisy and only meant for the true --verbose state).
    assert '[INFO]' not in result.stderr
    assert 'Sample of' not in result.stdout
    assert 'unique fields' not in result.stdout
    assert 'Columns:' not in result.stdout


def test_create_db_quiet_shows_nothing(lib_dir, tmp_path):
    result = _run_create_db_main(lib_dir, tmp_path, ['--quiet'])
    assert result.returncode == 0, result.stderr
    assert result.stdout == ''
    assert '[INFO]' not in result.stderr


def test_create_db_verbose_shows_everything(lib_dir, tmp_path):
    result = _run_create_db_main(lib_dir, tmp_path, ['--verbose'])
    assert result.returncode == 0, result.stderr
    assert '[INFO]' in result.stderr
    assert 'Database created successfully' in result.stdout
    assert 'Total packages inserted' in result.stdout
    assert 'Sample of' in result.stdout
    assert 'unique fields' in result.stdout
    assert 'Columns:' in result.stdout


def test_create_db_quiet_and_verbose_together_rejected(lib_dir, tmp_path):
    result = _run_create_db_main(lib_dir, tmp_path, ['--quiet', '--verbose'])
    assert result.returncode != 0
    assert 'not allowed with argument' in result.stderr


# ---------------------------------------------------------------------------
# pacq explicitly rejects --verbose
# ---------------------------------------------------------------------------
def test_pacq_verbose_is_rejected(project_root):
    result = run_pacq_raw(project_root, '--verbose')
    assert result.returncode != 0
    assert 'not supported' in result.stderr.lower()


def test_pacq_verbose_rejected_regardless_of_position(project_root):
    result = run_pacq_raw(project_root, '-e', '--verbose')
    assert result.returncode != 0
    assert 'not supported' in result.stderr.lower()


def test_pacq_normal_operation_unaffected(project_root):
    result = run_pacq_raw(project_root, '-e')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()  # some real output, unaffected by the change
