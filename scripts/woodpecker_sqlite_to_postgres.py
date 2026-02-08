#!/usr/bin/env python3
"""
One-time Woodpecker DB migration helper: sqlite -> postgres for minimal continuity.

Why this exists:
- Woodpecker sqlite can lock under concurrency.
- We migrate to Postgres but keep existing repo + secrets so CI continues working.

This script copies a small set of tables:
  forges, orgs, users, repos, secrets

Assumptions:
- Postgres schema has already been initialized by starting woodpecker-server once.
- Target tables are empty (script skips tables that already contain rows).
"""

from __future__ import annotations

import os
import sqlite3
import sys
from typing import Any

import psycopg2

TABLES = ["forges", "orgs", "users", "repos", "secrets"]


def _env(name: str, *, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None or not str(v).strip():
        raise RuntimeError(f"Missing required env var: {name}")
    return str(v)


def _sqlite_connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _pg_connect() -> Any:
    return psycopg2.connect(
        host=_env("PGHOST"),
        port=int(_env("PGPORT", default="5432")),
        dbname=_env("PGDATABASE"),
        user=_env("PGUSER"),
        password=_env("PGPASSWORD"),
    )


def _pg_bool_cols(pg, table: str) -> set[str]:
    with pg.cursor() as c:
        c.execute(
            """
            select column_name
            from information_schema.columns
            where table_name=%s and data_type='boolean'
            """,
            (table,),
        )
        return {r[0] for r in c.fetchall()}


def _fetch_all(sq: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(sq.execute(f"SELECT * FROM {table}").fetchall())


def _normalize(table: str, col: str, v: Any, bool_cols: dict[str, set[str]]) -> Any:
    if col in bool_cols.get(table, set()):
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        # sqlite stores bools as ints
        return bool(int(v))
    return v


def _insert_rows(
    pg, table: str, rows: list[sqlite3.Row], bool_cols: dict[str, set[str]]
) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    sql = (
        f'INSERT INTO "{table}" ('
        + ", ".join([f'"{c}"' for c in cols])
        + ") VALUES ("
        + ", ".join(["%s"] * len(cols))
        + ")"
    )
    with pg.cursor() as c:
        for r in rows:
            vals = [_normalize(table, col, r[col], bool_cols) for col in cols]
            c.execute(sql, vals)


def main() -> int:
    sqlite_path = _env("SQLITE_PATH", default="/sqlite/woodpecker.sqlite")

    sq = _sqlite_connect(sqlite_path)
    pg = _pg_connect()
    pg.autocommit = False

    bool_cols: dict[str, set[str]] = {}
    for t in TABLES:
        bool_cols[t] = _pg_bool_cols(pg, t)

    try:
        for t in TABLES:
            with pg.cursor() as c:
                c.execute(f'SELECT count(*) FROM "{t}"')
                n = int(c.fetchone()[0])
            if n:
                print(f"{t}: postgres already has {n} rows; skipping")
                continue
            rs = _fetch_all(sq, t)
            print(f"{t}: copying {len(rs)} rows")
            _insert_rows(pg, t, rs, bool_cols)
        pg.commit()
    except Exception as e:  # noqa: BLE001
        pg.rollback()
        print(f"ERROR: migration failed: {e}", file=sys.stderr)
        raise
    finally:
        sq.close()
        pg.close()

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
