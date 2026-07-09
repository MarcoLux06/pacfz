import os
import subprocess


def _fake_fzf_path(tmp_path, selects="firefox"):
    """Create a stand-in 'fzf' that always 'selects' a specific line from
    its stdin, instead of opening a real interactive session. Same safety
    rationale as test_empty_results.py's version: this must never launch
    real fzf, regardless of what's actually installed on the machine
    running the suite.
    """
    fake_bin = tmp_path / 'fake_fzf_bin'
    fake_bin.mkdir(exist_ok=True)
    fake_fzf = fake_bin / 'fzf'
    fake_fzf.write_text(
        '#!/bin/bash\n'
        'cat > /dev/null\n'  # consume stdin so the real pipeline doesn't block
        f'echo "{selects}"\n'
    )
    fake_fzf.chmod(0o755)
    return str(fake_bin)


def run_pacfz(project_root, tmp_path, *args, selects="firefox"):
    pacfz = os.path.join(str(project_root), 'src', 'pacfz')
    env = os.environ.copy()
    env['PATH'] = f"{_fake_fzf_path(tmp_path, selects)}:{env['PATH']}"
    return subprocess.run(
        [pacfz, *args], capture_output=True, text=True, env=env, timeout=10,
    )


def test_print_selection_outputs_bare_name_only(project_root, tmp_path):
    result = run_pacfz(project_root, tmp_path, '--print-selection', selects='firefox')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'firefox'


def test_print_selection_does_not_render_a_preview(project_root, tmp_path):
    # The normal (default) path pipes the fzf selection into
    # preview_item.py for a full colorized rendering -- --print-selection
    # must skip that entirely and print only the bare name.
    result = run_pacfz(project_root, tmp_path, '--print-selection', selects='firefox')
    assert '\x1b[' not in result.stdout  # no ANSI color codes at all
    assert 'Description' not in result.stdout
    assert 'Version' not in result.stdout


def test_normal_mode_still_renders_full_preview(project_root, tmp_path):
    # Regression check: --print-selection must not have changed the
    # DEFAULT behavior when it's not passed at all.
    result = run_pacfz(project_root, tmp_path, selects='lavat-git')
    assert result.returncode == 0, result.stderr
    assert 'Name' in result.stdout
    assert 'lavat-git' in result.stdout
    # the default path DOES include color codes, unlike --print-selection
    assert '\x1b[' in result.stdout


def test_print_selection_respects_active_filters(project_root, tmp_path):
    # --print-selection must still only offer fzf whatever the active
    # filters actually matched -- it changes what happens with the
    # SELECTION, not what gets INTO the picker in the first place.
    result = run_pacfz(
        project_root, tmp_path, '-e', '--print-selection', selects='firefox',
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'firefox'


def test_print_selection_with_no_results_still_short_circuits(project_root, tmp_path):
    # The existing "No packages found." short-circuit must fire before
    # fzf is even attempted, regardless of --print-selection.
    result = run_pacfz(
        project_root, tmp_path,
        '-f', 'Name', 'this-package-definitely-does-not-exist',
        '--print-selection',
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'No packages found.'
