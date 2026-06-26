import pathlib

from create_db import parse_qi_output

FIXTURES = pathlib.Path(__file__).resolve().parent / 'fixtures'


def _packages():
    text = (FIXTURES / 'qi_sample.txt').read_text()
    pkgs = parse_qi_output(text)
    return {p['Name']: p for p in pkgs}


def test_parses_all_packages():
    pkgs = _packages()
    assert set(pkgs) == {'firefox', 'libnotify'}


def test_basic_fields():
    pkgs = _packages()
    ff = pkgs['firefox']
    assert ff['Version'] == '1.0-1'
    assert ff['Install_Reason'] == 'Explicitly installed'
    assert ff['Installed_Size'] == '2.34 MiB'


def test_wrapped_optional_deps_kept():
    # H3: every wrapped Optional Deps line must survive, including ones that
    # contain a colon. The old parser silently dropped these.
    ff = _packages()['firefox']
    opt = ff['Optional_Deps']
    assert 'ffmpeg: H.264/AAC video support' in opt
    assert 'libnotify: desktop notifications' in opt
    assert 'speech-dispatcher: text-to-speech' in opt
    # Three entries -> two newlines joining them.
    assert opt.count('\n') == 2


def test_next_field_not_swallowed():
    # The field after a wrapped block must still parse independently.
    ff = _packages()['firefox']
    assert ff['Required_By'] == 'None'
    assert ff['Install_Reason'] == 'Explicitly installed'
