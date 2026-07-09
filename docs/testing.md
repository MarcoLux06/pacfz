# Testing philosophy

This covers what the test suite actually verifies, what it can't, and where the fixture data came from. If you're
adding a feature and wondering how much testing is "enough," this is the doc to check first.

## Running it

```sh
make test
```

which is just `python3 -m pytest tests/ -q`. 157 tests as of writing, all of them fast (a few seconds total), since
none of them touch the network or a real Arch machine.

## What "100% coverage" wouldn't actually mean

Worth saying up front, since it's tempting to chase the number: even a hypothetical 100%-covered version of this
codebase couldn't promise "works flawlessly." Line coverage only proves a line *executed*, not that its result was
*checked* correctly, a test that calls a function and asserts nothing still counts as "covered." It also can't cover
input you didn't think to test, the comma-decimal locale bug (`56,72 KiB` vs `56.72 KiB`) lived in code that already
had tests, just not that specific case, until a real bug report surfaced it. So the actual goal here isn't a
coverage percentage, it's covering the things that matter: real filter combinations, real parsing edge cases, and
the handful of genuinely subtle bugs this project has already hit once.

## What's actually well covered

The query engine (`list_packages.py`'s `build_query()`, the tri-state invert logic, the totalsize description
builder) is tested heavily and mostly through subprocess calls against a real fixture DB, not mocked internals, with
expected values computed independently via direct SQL rather than hand-picked numbers. Same for the `pacman -Qi`
parser (`create_db.py`'s `parse_qi_output()`), which has a dedicated regression test for the wrapped-optional-deps
bug (a continuation line containing a colon, like `libnotify: desktop notifications`, used to get silently dropped).

`note_manager.py` and `render_preview()` both used to have zero direct coverage, worth mentioning since it's exactly
the kind of gap that's easy to miss until you go looking, they're covered now, including a real bug the writing of
those tests turned up: setting a note whose text happens to match an existing flag (like `-d`) silently deletes the
note instead of setting it, since `note_manager.py` has no `--` separator handling. That's `test_note_manager.py`'s
`test_note_text_matching_a_real_flag_is_misparsed`, deliberately written to document the current (broken) behavior
so a future fix is a visible, deliberate change to the test rather than a silent one.

## What's structurally hard to test, and why that's fine

`create_db.py`'s functions that actually shell out to real `pacman` (`get_foreign_packages()`, the timeout/
`FileNotFoundError` handling) sit around 80% coverage, and that's about as high as it can reasonably go without a
real Arch machine in CI. You can't unit-test "did this correctly invoke a binary that doesn't exist on the test
machine." The tests work around this the honest way: `create_database()` accepts injected `packages=`/
`foreign_packages=` so the parsing and atomic-write logic (the part that actually matters) gets exercised with real
or crafted data, without ever needing pacman itself to be present.

`pactui` is the least-tested part of the project, on purpose for now. It's a Textual app, and while Textual ships a
real headless test harness (used during development to drive actual keypresses and clicks and check rendered
output), formal pinned regression tests for it haven't been written yet. Anything you change there should still be
manually exercised the way it was built, `python3 src/pactui` and actually clicking around, until that gap gets
closed.

## Fixture data

`tests/fixtures/` has two different kinds of thing in it, worth telling apart:

- `qi_sample.txt` is hand-crafted, a fictional `firefox` package block specifically constructed to test one parser
  edge case (a continuation line with a colon in it). Nothing in it needs to resemble a real system.
- `packages.db`, `notes.db`, and `pacman_sample.log` are real data, captured from an actual Arch install and
  anonymized (a literal home directory path got swapped to `/home/me/...` before it was added here). These exist
  specifically because synthetic data kept missing real-world shapes, an actual `pacman.log` spans timezone changes
  across a fresh-install chroot in a way a hand-written fixture never would have thought to include, and that's
  exactly what surfaced a real sorting bug in `pactui`'s Overview screen (naive string comparison of
  `+0000`/`+0200` timestamps isn't timezone-aware). If you're ever tempted to regenerate these fixtures from your
  own machine, that's fine, just anonymize any real filesystem paths first the same way.

## Writing new tests

A few patterns worth following, all already established in the existing suite:

- Prefer running the real script as a subprocess over importing internals directly, especially for anything in
  `pacfz`/`pacq` (bash) or the interaction between bash and Python. `test_cli.py` and `test_invert_cli.py` are good
  examples.
- If a test needs `fzf`, it must never risk launching the real thing. `test_empty_results.py`'s `_fake_fzf_path()`
  helper shadows `fzf` on `PATH` with a harmless stand-in that reads stdin and exits immediately, this exists
  because a test that "happens" to work when fzf isn't installed can still hang a real machine that has it. Reuse
  that pattern rather than writing a new one.
- Compute expected values independently (direct SQL against the fixture DB, or plain Python arithmetic) rather than
  hard-coding a number you read off one test run. Several bugs in this project were only caught because a test's
  own expectation turned out to be wrong on closer inspection, not the code.
