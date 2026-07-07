import list_packages as lp
import pytest


def test_default_query():
    q, params = lp.build_query()
    assert q == 'SELECT "Name" FROM packages ORDER BY "Name" ASC'
    assert params == []


def test_foreign_clause():
    q, params = lp.build_query(where_clauses=['foreign'])
    assert 'WHERE is_foreign = 1' in q
    assert params == []


def test_orphan_uses_equals_not_is():
    # H2: the canned clauses must compare against the literal string 'None'
    # with '=', never the NULL-flavored 'IS'.
    q, _ = lp.build_query(where_clauses=['orphan'])
    assert "= 'None'" in q
    assert ' IS ' not in q.upper().replace('THIS', '')  # no stray IS operator


def test_notadep_clause():
    q, _ = lp.build_query(where_clauses=['notadep'])
    assert "Required_By = 'None'" in q


def test_field_like():
    q, params = lp.build_query(field_searches=[('Name', 'vim')])
    assert '"Name" LIKE ?' in q
    assert params == ['%vim%']


def test_field_exact():
    q, params = lp.build_query(field_searches=[('Name', 'vim')], exact_match=True)
    assert '"Name" = ?' in q
    assert params == ['vim']


def test_any_field_ors_across_columns():
    q, params = lp.build_query(any_field_searches=['foo'])
    # one OR group, one param per real column
    cols = lp.get_table_columns()
    assert q.count('LIKE ?') == len(cols)
    assert params == ['%foo%'] * len(cols)


def test_invert_all_requires_something():
    with pytest.raises(ValueError):
        lp.build_query(invert_all=True)


def test_invert_all_negates_group():
    q, _ = lp.build_query(where_clauses=['foreign'], invert_all=True)
    assert 'NOT (is_foreign = 1)' in q


def test_scoped_invert_keeps_precondition():
    q, _ = lp.build_query(where_clauses=['explicit'], invert_clauses=['notadep'])
    assert "Install_Reason = 'Explicitly installed'" in q  # precondition kept
    assert 'NOT (' in q  # scoped negation
    assert 'Required_By' in q


def test_sort_size_defaults_desc():
    q, _ = lp.build_query(sort_field='Installed_Size')
    assert q.endswith('ORDER BY "Installed_Size" DESC')


def test_sort_name_defaults_asc():
    q, _ = lp.build_query(sort_field='Name')
    assert q.endswith('ORDER BY "Name" ASC')


def test_explicit_direction_overrides_default():
    q, _ = lp.build_query(sort_field='Installed_Size', sort_direction='ASC')
    assert q.endswith('ORDER BY "Installed_Size" ASC')


def test_field_name_resolution_is_forgiving():
    # spaces + lowercase resolve to the real column; Installed_Size keeps its
    # DESC default direction.
    q, _ = lp.build_query(sort_field='installed size')
    assert q.endswith('ORDER BY "Installed_Size" DESC')
    # a non-size field resolves case-insensitively and defaults ASC
    q2, _ = lp.build_query(sort_field='vErSiOn')
    assert q2.endswith('ORDER BY "Version" ASC')


def test_unknown_field_raises():
    with pytest.raises(ValueError):
        lp.build_query(field_searches=[('NoSuchColumn', 'x')])


def test_total_select_and_no_order():
    q, _ = lp.build_query(
        where_clauses=['foreign'],
        select_cols='SUM("Installed_Size")',
        include_order=False,
    )
    assert q.startswith('SELECT SUM("Installed_Size")')
    assert 'ORDER BY' not in q
    assert 'WHERE is_foreign = 1' in q
