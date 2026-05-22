"""Validate SQL before execution (read-only by default)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import DML

_FORBIDDEN_KEYWORDS = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "truncate",
        "alter",
        "create",
        "grant",
        "revoke",
        "copy",
        "call",
        "execute",
        "merge",
        "replace",
    }
)

_LIMIT_RE = re.compile(r"\blimit\s+\d+", re.IGNORECASE)


@dataclass(frozen=True)
class GuardResult:
    sql: str
    is_read_only: bool


class QueryRejectedError(ValueError):
    pass


def _strip_comments(sql: str) -> str:
    return sqlparse.format(sql, strip_comments=True).strip()


def _first_token_is_select(statement: Statement) -> bool:
    for token in statement.tokens:
        if token.ttype is DML:
            return token.value.lower() == "select"
        if not token.is_whitespace and token.ttype is not None:
            break
    return False


def _statement_is_read_only_select(statement: Statement) -> bool:
    if _first_token_is_select(statement):
        return True
    tokens = [
        t.value.lower()
        for t in statement.flatten()
        if getattr(t, "value", None) and str(t.value).strip()
    ]
    if tokens and tokens[0] == "with":
        return "select" in tokens
    return False


def _statement_has_forbidden_keyword(statement: Statement) -> Optional[str]:
    for token in statement.flatten():
        if token.ttype is DML and token.value.lower() in _FORBIDDEN_KEYWORDS:
            return token.value.lower()
        if token.ttype is None and isinstance(token.value, str):
            word = token.value.lower()
            if word in _FORBIDDEN_KEYWORDS:
                return word
    return None


def validate_query(sql: str, *, allow_write: bool = False) -> GuardResult:
    cleaned = _strip_comments(sql)
    if not cleaned:
        raise QueryRejectedError("Empty SQL")

    if ";" in cleaned.rstrip().rstrip(";"):
        parts = [p.strip() for p in cleaned.split(";") if p.strip()]
        if len(parts) > 1:
            raise QueryRejectedError("Multiple statements are not allowed")

    parsed = sqlparse.parse(cleaned)
    if not parsed:
        raise QueryRejectedError("Could not parse SQL")

    for statement in parsed:
        forbidden = _statement_has_forbidden_keyword(statement)
        if forbidden:
            raise QueryRejectedError(f"Forbidden keyword: {forbidden.upper()}")

        if not _statement_is_read_only_select(statement):
            if allow_write:
                raise QueryRejectedError(
                    "Only SELECT queries are allowed (write mode is not implemented in v1)"
                )
            raise QueryRejectedError("Only SELECT statements are allowed")

    return GuardResult(sql=cleaned, is_read_only=True)


def apply_row_limit(sql: str, max_rows: int, hard_max: int) -> str:
    limit = min(max_rows, hard_max)
    if _LIMIT_RE.search(sql):
        return sql
    return f"{sql.rstrip().rstrip(';')} LIMIT {limit}"
