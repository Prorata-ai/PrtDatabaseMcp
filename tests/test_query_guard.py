import pytest

from prt_database_mcp.query_guard import QueryRejectedError, apply_row_limit, validate_query


def test_select_allowed():
    result = validate_query("SELECT id, name FROM publishers WHERE enabled = true")
    assert result.is_read_only


def test_select_with_cte():
    sql = "WITH active AS (SELECT id FROM publishers) SELECT * FROM active"
    result = validate_query(sql)
    assert "active" in result.sql


def test_delete_rejected():
    with pytest.raises(QueryRejectedError, match="Forbidden"):
        validate_query("DELETE FROM publishers")


def test_insert_rejected():
    with pytest.raises(QueryRejectedError):
        validate_query("INSERT INTO publishers (name) VALUES ('x')")


def test_multi_statement_rejected():
    with pytest.raises(QueryRejectedError, match="Multiple"):
        validate_query("SELECT 1; SELECT 2")


def test_apply_limit_when_missing():
    out = apply_row_limit("SELECT * FROM sites", 100, 500)
    assert "LIMIT 100" in out


def test_apply_limit_preserves_existing():
    out = apply_row_limit("SELECT * FROM sites LIMIT 5", 100, 500)
    assert out.endswith("LIMIT 5")
