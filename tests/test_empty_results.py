import os
import subprocess
import sys


def _fake_fzf_path(tmp_path):
    """Create a harmless stand-in 'fzf' binary and return its directory.

    CRITICAL: the real pacfz launches real fzf as an interactive,
    blocking, full-terminal program. If the machine running these tests
    actually has fzf installed, tests that deliberately exercise the
    non-empty path (i.e. anything that's SUPPOSED to reach fzf) would
    otherwise launch a real interactive session and hang the test run
    waiting for keyboard input -- which is exactly what happened before
    this fix. Every subprocess call in this file must have this fake
    binary shadowing the real one on PATH, regardless of whether fzf is
    actually installed on the machine running the suite.
    """
    fake_bin = tmp_path / 'fake_fzf_bin'
    fake_bin.mkdir(exist_ok=True)
    fake_fzf = fake_bin / 'fzf'
    # Reads whatever's piped to it and exits immediately -- never
    # interactive, never blocks, never touches the real terminal.
    fake_fzf.write_text('#!/bin/bash\ncat > /dev/null\nexit 0\n')
    fake_fzf.chmod(0o755)
    return str(fake_bin)


def run_pacfz(project_root, tmp_path, *args):
    pacfz = os.path.join(str(project_root), 'src', 'pacfz')
    env = os.environ.copy()
    env['PATH'] = f"{_fake_fzf_path(tmp_path)}:{env['PATH']}"
    return subprocess.run(
        [pacfz, *args], capture_output=True, text=True, env=env, timeout=10,
    )


def test_empty_query_prints_no_packages_found(project_root, tmp_path):
    # A field search matching nothing real must short-circuit before fzf
    # is even attempted, printing a clear message instead.
    result = run_pacfz(
        project_root, tmp_path, '-f', 'Name', 'this-package-definitely-does-not-exist',
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'No packages found.'


def test_empty_query_does_not_report_fzf_as_the_problem(project_root, tmp_path):
    # Even with fzf genuinely available (the fake binary makes it always
    # "available" here, matching a real machine that has it installed),
    # the empty-query message must win -- it's the more specific, more
    # useful explanation, checked BEFORE pacfz even looks for fzf.
    result = run_pacfz(
        project_root, tmp_path, '-f', 'Name', 'this-package-definitely-does-not-exist',
    )
    assert 'fzf' not in result.stdout
    assert 'fzf' not in result.stderr


def test_nonempty_query_proceeds_to_fzf_not_the_empty_message(project_root, tmp_path):
    # A query that genuinely matches something must NOT print the empty
    # message -- it should proceed toward fzf. Uses the fake fzf binary so
    # this is safe to run even on a machine with real fzf installed: the
    # fake one just reads stdin and exits, never opening a real
    # interactive session.
    result = run_pacfz(project_root, tmp_path, '-e')
    assert 'No packages found.' not in result.stdout
    assert result.returncode == 0, result.stderr


def test_bare_invocation_with_results_is_unaffected(project_root, tmp_path):
    # Sanity check: running with no filters at all (matches everything)
    # must never trigger the empty-results path. Same fake-fzf safety as
    # above.
    result = run_pacfz(project_root, tmp_path)
    assert 'No packages found.' not in result.stdout
    assert result.returncode == 0, result.stderr
