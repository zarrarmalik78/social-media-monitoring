"""Unit tests for QueryBuilder and SearchQueryFilter."""

import pytest
from app.utils.query_builder import QueryBuilder, SearchQueryFilter


def test_build_simple_keywords():
    f = SearchQueryFilter(all_words="IIUI admissions")
    q = QueryBuilder.build(f)
    assert q == "IIUI admissions"


def test_build_exact_phrase():
    f = SearchQueryFilter(exact_phrase="International Islamic University")
    q = QueryBuilder.build(f)
    assert q == '"International Islamic University"'


def test_build_or_grouping():
    f = SearchQueryFilter(any_words="IIUI COMSATS NUST")
    q = QueryBuilder.build(f)
    assert q == "(IIUI OR COMSATS OR NUST)"


def test_build_exclusions():
    f = SearchQueryFilter(all_words="IIUI", none_words="jobs vacancy")
    q = QueryBuilder.build(f)
    assert q == "IIUI -jobs -vacancy"


def test_build_accounts_and_language():
    f = SearchQueryFilter(
        from_accounts="IIUI_OFFICIAL, COMSATS_en",
        language="en"
    )
    q = QueryBuilder.build(f)
    assert q == "(from:IIUI_OFFICIAL OR from:COMSATS_en) lang:en"


def test_build_full_composite_query():
    f = SearchQueryFilter(
        all_words="scholarship",
        exact_phrase="Faculty of Computing",
        any_words="IIUI NUST",
        none_words="expired",
        from_accounts="IIUI_OFFICIAL",
        language="en",
        since_date="2026-01-01",
        until_date="2026-08-30",
        min_likes=5,
        min_reposts=2,
        has_media=True,
        exclude_replies=True,
    )
    q = QueryBuilder.build(f)
    assert 'scholarship "Faculty of Computing" (IIUI OR NUST) -expired from:IIUI_OFFICIAL lang:en since:2026-01-01 until:2026-08-30 min_faves:5 min_retweets:2 filter:media -filter:replies' in q


def test_validate_valid_query():
    res = QueryBuilder.validate('IIUI lang:en min_faves:10 since:2026-01-01 "Computer Science"')
    assert res["valid"] is True
    assert len(res["errors"]) == 0
    assert res["operators"]["lang"] == "en"
    assert res["operators"]["min_faves"] == "10"
    assert res["operators"]["since"] == "2026-01-01"


def test_validate_unbalanced_quotes():
    res = QueryBuilder.validate('IIUI "Computer Science')
    assert res["valid"] is False
    assert any("Unbalanced quotation marks" in err for err in res["errors"])


def test_validate_unbalanced_parentheses():
    res = QueryBuilder.validate('(IIUI OR COMSATS')
    assert res["valid"] is False
    assert any("Unbalanced parentheses" in err for err in res["errors"])


def test_validate_invalid_date():
    res = QueryBuilder.validate('IIUI since:2026-13-45')
    assert res["valid"] is False
    assert any("Invalid date format" in err for err in res["errors"])


def test_validate_invalid_metric():
    res = QueryBuilder.validate('IIUI min_faves:invalid')
    assert res["valid"] is False
    assert any("Invalid metric value" in err for err in res["errors"])
