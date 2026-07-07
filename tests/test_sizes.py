import pytest

from create_db import convert_size_to_bytes
from preview_item import bytes_to_human


@pytest.mark.parametrize("text,expected", [
    ("2.34 MiB", int(2.34 * 1024 ** 2)),
    ("1929.95 KiB", int(1929.95 * 1024)),
    ("100.00 KiB", 100 * 1024),
    ("1.00 GiB", 1024 ** 3),
    ("512 B", 512),
    ("None", 0),
    ("", 0),
])
def test_convert_size_to_bytes(text, expected):
    assert convert_size_to_bytes(text) == expected


def test_convert_size_to_bytes_invalid():
    with pytest.raises(ValueError):
        convert_size_to_bytes("not a size")


@pytest.mark.parametrize("text,expected", [
    ("56,72 KiB", int(56.72 * 1024)),
    ("2,34 MiB", int(2.34 * 1024 ** 2)),
    ("1,00 GiB", 1024 ** 3),
])
def test_convert_size_to_bytes_comma_locale(text, expected):
    # pacman formats numbers per the system locale; de_DE/fr_FR etc. use a
    # comma decimal separator instead of a dot.
    assert convert_size_to_bytes(text) == expected


@pytest.mark.parametrize("value,expected", [
    (0, "0 B"),
    (512, "512 B"),
    (1024, "1.00 KiB"),
    (1024 ** 2, "1.00 MiB"),
    (1024 ** 3, "1.00 GiB"),
    (None, ""),
    ("", ""),
])
def test_bytes_to_human(value, expected):
    assert bytes_to_human(value) == expected


@pytest.mark.parametrize("text", ["2.34 MiB", "100.00 KiB", "1.00 GiB"])
def test_round_trip(text):
    # human -> bytes -> human is stable for two-decimal binary values.
    assert bytes_to_human(convert_size_to_bytes(text)) == text
