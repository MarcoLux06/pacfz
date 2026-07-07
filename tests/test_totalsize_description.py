from types import SimpleNamespace

import list_packages as lp


def _args(**overrides):
    """A minimal stand-in for the argparse namespace build_totalsize_description
    reads from — only the attributes it actually looks at (via getattr with
    a default), so tests don't need to construct a real ArgumentParser.
    """
    defaults = dict(
        foreign=False, orphans=False, explicit=False, deps=False,
        notadep=False, notoptdep=False, has_note=False, no_note=False,
        field_searches=None, any_field_searches=None, invert_args=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_default_description_no_filters():
    assert lp.build_totalsize_description(_args()) == "total package size"


def test_single_boolean_filter():
    assert (
            lp.build_totalsize_description(_args(foreign=True))
            == "total size of foreign packages"
    )


def test_multiple_boolean_filters_combine_in_stable_order():
    # Order follows _describe_active_filters' own iteration order
    # (foreign, orphan, explicit, deps, notadep, notoptdep), regardless of
    # which order the flags happened to be passed on the command line.
    desc = lp.build_totalsize_description(_args(explicit=True, foreign=True))
    assert desc == "total size of foreign, explicitly installed packages"


def test_all_six_boolean_filters_have_phrases():
    # Every canned filter must produce SOME phrase, not silently vanish.
    for attr in ('foreign', 'orphans', 'explicit', 'deps', 'notadep', 'notoptdep'):
        desc = lp.build_totalsize_description(_args(**{attr: True}))
        assert desc != "total package size", f"{attr} produced no phrase"
        assert "packages" in desc


def test_has_note_reads_as_trailing_qualifier_not_adjective():
    # Regression: "with a note" must NOT be squeezed in before "packages"
    # as if it were an adjective (that reads as "total size of with a note
    # packages", which is grammatically broken) — it belongs after.
    desc = lp.build_totalsize_description(_args(has_note=True))
    assert desc == "total package size with a note"
    assert "of with a note packages" not in desc


def test_no_note_reads_as_trailing_qualifier():
    desc = lp.build_totalsize_description(_args(no_note=True))
    assert desc == "total package size without a note"


def test_boolean_filter_and_notes_filter_combine():
    desc = lp.build_totalsize_description(_args(explicit=True, has_note=True))
    assert desc == "total size of explicitly installed packages with a note"


def test_field_search_phrase():
    desc = lp.build_totalsize_description(
        _args(field_searches=[('Name', 'vim')])
    )
    assert desc == 'total package size where Name matches "vim"'


def test_any_field_search_phrase():
    desc = lp.build_totalsize_description(_args(any_field_searches=['vim']))
    assert desc == 'total package size where any field matches "vim"'


def test_multiple_field_searches_join_with_and():
    desc = lp.build_totalsize_description(
        _args(field_searches=[('Name', 'vim'), ('Licenses', 'GPL')])
    )
    assert desc == (
        'total package size where Name matches "vim" '
        'and where Licenses matches "GPL"'
    )


def test_boolean_filter_and_field_search_combine():
    desc = lp.build_totalsize_description(
        _args(explicit=True, field_searches=[('Licenses', 'GPL')])
    )
    assert desc == 'total size of explicitly installed packages where Licenses matches "GPL"'


def test_bare_invert_notes_the_negation():
    desc = lp.build_totalsize_description(
        _args(foreign=True, invert_args=['__ALL__'])
    )
    assert desc == "total size of packages NOT matching: foreign"


def test_bare_invert_with_no_other_filters_falls_back_gracefully():
    # Bare -v with nothing else active is actually rejected earlier in
    # main() (build_query raises ValueError for "-v has nothing to
    # invert"), but the description builder itself should not crash if
    # ever called this way — it should degrade to a sensible default
    # rather than producing a blank or malformed descriptor.
    desc = lp.build_totalsize_description(_args(invert_args=['__ALL__']))
    assert "NOT matching" in desc
    assert desc.strip().endswith("the above") or "the above" in desc
