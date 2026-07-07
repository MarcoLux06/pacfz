import pytest

import preview_item


def test_render_preview_real_package_data(cache_db):
    data = preview_item.query_database('lavat-git', db_path=cache_db)
    assert data is not None
    rendered = preview_item.render_preview(data)

    # Real content must show up, not just "did it run without crashing".
    assert 'lavat-git' in rendered
    assert 'Explicitly installed' in rendered
    assert 'MIT' in rendered  # Licenses


def test_render_preview_is_multiline(cache_db):
    data = preview_item.query_database('lavat-git', db_path=cache_db)
    rendered = preview_item.render_preview(data)
    # LABEL_FORMAT has multiple real fields plus break markers -> many lines.
    assert rendered.count('\n') > 5


def test_render_preview_contains_ansi_color_codes(cache_db):
    # This is meant to be colorized terminal output, not plain text --
    # confirm the color escape codes are actually present.
    data = preview_item.query_database('lavat-git', db_path=cache_db)
    rendered = preview_item.render_preview(data)
    assert '\x1b[' in rendered


def test_render_preview_skips_missing_optional_field():
    # 'Note' is present in LABEL_FORMAT but is only ever added to the data
    # dict when a note actually exists (see preview_item.main() / pactui's
    # _show_preview) — when it's absent, _formatted_line_for returns None
    # and render_preview must skip it entirely, not print an empty "Note:"
    # line.
    data = {
        'Name': 'firefox', 'Version': '140.0', 'Description': 'a browser',
        'Groups': 'None', 'Depends On': 'None', 'Optional Deps': 'None',
        'Required By': 'None', 'Optional For': 'None',
        'Installed Size': 12345, 'Install Reason': 'Explicitly installed',
        'Architecture': 'x86_64', 'Licenses': 'MPL-2.0',
        'Build Date': 'x', 'Validated By': 'Signature', 'is foreign': 0,
        # deliberately no 'Note' key
    }
    rendered = preview_item.render_preview(data)
    assert 'Note' not in rendered


def test_render_preview_includes_note_when_present():
    data = {
        'Name': 'firefox', 'Version': '140.0', 'Description': 'a browser',
        'Groups': 'None', 'Depends On': 'None', 'Optional Deps': 'None',
        'Required By': 'None', 'Optional For': 'None',
        'Installed Size': 12345, 'Install Reason': 'Explicitly installed',
        'Architecture': 'x86_64', 'Licenses': 'MPL-2.0',
        'Build Date': 'x', 'Validated By': 'Signature', 'is foreign': 0,
        'Note': 'daily driver, keep on stable',
    }
    rendered = preview_item.render_preview(data)
    assert 'Note' in rendered
    assert 'daily driver, keep on stable' in rendered


@pytest.mark.parametrize("is_foreign_value,expected_word", [(1, 'Yes'), (0, 'No')])
def test_render_preview_is_foreign_int_becomes_yes_no(is_foreign_value, expected_word):
    data = {
        'Name': 'firefox', 'Version': '140.0', 'Description': 'a browser',
        'Groups': 'None', 'Depends On': 'None', 'Optional Deps': 'None',
        'Required By': 'None', 'Optional For': 'None',
        'Installed Size': 12345, 'Install Reason': 'Explicitly installed',
        'Architecture': 'x86_64', 'Licenses': 'MPL-2.0',
        'Build Date': 'x', 'Validated By': 'Signature',
        'is foreign': is_foreign_value,
    }
    rendered = preview_item.render_preview(data)
    assert expected_word in rendered


def test_render_preview_installed_size_is_human_readable():
    # Installed Size is stored as a raw byte count in the DB; render_preview
    # must show it as e.g. "12.06 KiB", not the bare integer 12345.
    data = {
        'Name': 'firefox', 'Version': '140.0', 'Description': 'a browser',
        'Groups': 'None', 'Depends On': 'None', 'Optional Deps': 'None',
        'Required By': 'None', 'Optional For': 'None',
        'Installed Size': 1024, 'Install Reason': 'Explicitly installed',
        'Architecture': 'x86_64', 'Licenses': 'MPL-2.0',
        'Build Date': 'x', 'Validated By': 'Signature', 'is foreign': 0,
    }
    rendered = preview_item.render_preview(data)
    assert '1024' not in rendered
    assert '1.00 KiB' in rendered


def test_render_preview_sanitizes_hostile_field_values():
    # Integration check for S2: render_preview is the function pactui
    # actually calls for its preview pane, so the sanitizer needs to be
    # proven to run on THIS path, not just on sanitize_terminal_value() in
    # isolation. A hostile Description embedding an OSC sequence must not
    # reach the rendered output.
    data = {
        'Name': 'evil-pkg', 'Version': '1.0',
        'Description': 'legit text\x1b]0;spoofed title\x07more text',
        'Groups': 'None', 'Depends On': 'None', 'Optional Deps': 'None',
        'Required By': 'None', 'Optional For': 'None',
        'Installed Size': 1024, 'Install Reason': 'Explicitly installed',
        'Architecture': 'x86_64', 'Licenses': 'MIT',
        'Build Date': 'x', 'Validated By': 'Signature', 'is foreign': 0,
    }
    rendered = preview_item.render_preview(data)
    assert '\x1b]' not in rendered
    assert '\x07' not in rendered
    assert 'legit text' in rendered
    assert 'more text' in rendered
