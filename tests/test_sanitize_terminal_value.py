from preview_item import format_line, sanitize_terminal_value


def test_plain_text_passes_through_unchanged():
    text = "A web browser built by Mozilla"
    assert sanitize_terminal_value(text) == text


def test_strips_csi_color_sequence():
    # e.g. embedding a raw ANSI color code to spoof pacfz's own coloring
    hostile = "hello\x1b[31mRED\x1b[0mworld"
    assert sanitize_terminal_value(hostile) == "helloREDworld"


def test_strips_csi_sequence_with_multiple_params():
    hostile = "text\x1b[1;33;44mstyled\x1b[0mtext"
    assert sanitize_terminal_value(hostile) == "textstyledtext"


def test_strips_osc_sequence_terminated_by_bel():
    # classic terminal-title-spoofing payload, BEL (\x07) terminated
    hostile = "pkg\x1b]0;fake title\x07description"
    assert sanitize_terminal_value(hostile) == "pkgdescription"


def test_strips_osc_sequence_terminated_by_st():
    # OSC can also be terminated by the "String Terminator" ESC \\ form
    hostile = "pkg\x1b]2;window title\x1b\\rest of text"
    assert sanitize_terminal_value(hostile) == "pkgrest of text"


def test_strips_bare_c0_control_characters():
    hostile = "bad\x07bell\x08backspace\x1fus"
    assert sanitize_terminal_value(hostile) == "badbellbackspaceus"


def test_preserves_newlines():
    # Real, legitimate field content is multi-line (wrapped Optional Deps),
    # so \n must NOT be treated as a control character to strip.
    text = "ffmpeg: H.264/AAC video support\nlibnotify: desktop notifications"
    assert sanitize_terminal_value(text) == text


def test_preserves_tabs():
    text = "column1\tcolumn2"
    assert sanitize_terminal_value(text) == text


def test_empty_string():
    assert sanitize_terminal_value("") == ""


def test_multiple_hostile_sequences_in_one_value():
    hostile = "\x1b[31mred\x1b[0m normal \x1b]0;title\x07 more \x07bell"
    assert sanitize_terminal_value(hostile) == "red normal  more bell"


def test_format_line_applies_sanitization():
    # Integration point: format_line() is where every preview line actually
    # gets built, so the sanitizer must run there, not just be callable in
    # isolation. Confirms the CSI bytes never reach the returned line even
    # though format_line wraps the value in its OWN color codes.
    hostile_value = "legit\x1b[35mfake-color\x1b[0mtext"
    line = format_line("Description", hostile_value)
    # the hostile escape sequence must be gone...
    assert "\x1b[35m" not in line
    # ...but format_line's own coloring is still applied normally
    assert "legitfake-colortext" in line
    assert "\x1b[" in line  # format_line's own color codes are still present
