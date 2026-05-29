"""
database.py — SQLite persistence for CodeArena.

Tables:
  users           — name, created_at
  submissions     — problem attempts with code, result, timestamp
  problem_stats   — aggregated per-problem stats (solve rate, avg time)

SQLite is used here for simplicity. For production swap with PostgreSQL
using the same interface — just change the connection string.
"""

import sqlite3
import json
import time
import os
from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass

DB_PATH = Path(__file__).parent / "codearena.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    """Context manager — auto-commits or rolls back."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                created_at  REAL    NOT NULL DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name       TEXT    NOT NULL,
                room_id         TEXT    NOT NULL,
                problem_id      TEXT    NOT NULL,
                problem_title   TEXT    NOT NULL DEFAULT '',
                language        TEXT    NOT NULL DEFAULT 'python',
                code            TEXT    NOT NULL DEFAULT '',
                passed          INTEGER NOT NULL DEFAULT 0,   -- 1 = all tests pass
                tests_total     INTEGER NOT NULL DEFAULT 0,
                tests_passed    INTEGER NOT NULL DEFAULT 0,
                time_taken_s    REAL    NOT NULL DEFAULT 0,   -- seconds since room created
                complexity_time TEXT    NOT NULL DEFAULT '',
                complexity_space TEXT   NOT NULL DEFAULT '',
                originality     INTEGER NOT NULL DEFAULT 0,  -- 0-100
                submitted_at    REAL    NOT NULL DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS problem_stats (
                problem_id      TEXT    PRIMARY KEY,
                problem_title   TEXT    NOT NULL DEFAULT '',
                total_attempts  INTEGER NOT NULL DEFAULT 0,
                total_solved    INTEGER NOT NULL DEFAULT 0,
                avg_time_s      REAL    NOT NULL DEFAULT 0,
                last_attempted  REAL    NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_submissions_user
                ON submissions(user_name);
            CREATE INDEX IF NOT EXISTS idx_submissions_problem
                ON submissions(problem_id);
            CREATE INDEX IF NOT EXISTS idx_submissions_room
                ON submissions(room_id);
        """)
    print(f"[db] Initialised at {DB_PATH}")


# ── Submissions ──────────────────────────────────────────────────────────────

def save_submission(
    user_name: str,
    room_id: str,
    problem_id: str,
    problem_title: str,
    language: str,
    code: str,
    test_results: list[dict],
    time_taken_s: float,
    complexity: dict | None = None,
    originality: dict | None = None,
) -> int:
    """
    Save a submission and update aggregated problem stats.
    Returns the new submission ID.
    """
    tests_total  = len(test_results)
    tests_passed = sum(1 for t in test_results if t.get("pass"))
    passed       = 1 if tests_total > 0 and tests_passed == tests_total else 0

    with db() as conn:
        cur = conn.execute("""
            INSERT INTO submissions
              (user_name, room_id, problem_id, problem_title, language, code,
               passed, tests_total, tests_passed, time_taken_s,
               complexity_time, complexity_space, originality)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user_name, room_id, problem_id, problem_title, language, code,
            passed, tests_total, tests_passed, time_taken_s,
            complexity.get("time", "") if complexity else "",
            complexity.get("space", "") if complexity else "",
            originality.get("score", 0) if originality else 0,
        ))
        sub_id = cur.lastrowid

        # Upsert problem_stats
        conn.execute("""
            INSERT INTO problem_stats (problem_id, problem_title, total_attempts, total_solved, avg_time_s, last_attempted)
            VALUES (?, ?, 1, ?, ?, unixepoch())
            ON CONFLICT(problem_id) DO UPDATE SET
                problem_title   = excluded.problem_title,
                total_attempts  = total_attempts + 1,
                total_solved    = total_solved + excluded.total_solved,
                avg_time_s      = (avg_time_s * total_attempts + excluded.avg_time_s) / (total_attempts + 1),
                last_attempted  = unixepoch()
        """, (problem_id, problem_title, passed, time_taken_s))

    return sub_id


# ── Progress queries ─────────────────────────────────────────────────────────

def get_user_progress(user_name: str) -> dict:
    """
    Return a full progress summary for a user:
    - problems solved / attempted
    - solve rate
    - list of solved problems with metadata
    - recent submissions
    - streak (consecutive days with a solve)
    """
    with db() as conn:
        # Aggregate stats
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT problem_id)                              AS attempted,
                COUNT(DISTINCT CASE WHEN passed=1 THEN problem_id END) AS solved,
                COUNT(*)                                                AS total_submissions,
                AVG(CASE WHEN passed=1 THEN time_taken_s END)          AS avg_solve_time,
                SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END)              AS total_passes
            FROM submissions
            WHERE user_name = ?
        """, (user_name,)).fetchone()

        # Problems solved (best submission per problem)
        solved_rows = conn.execute("""
            SELECT
                problem_id, problem_title, language,
                MIN(time_taken_s) AS best_time,
                MAX(submitted_at) AS last_solved,
                complexity_time, complexity_space, originality
            FROM submissions
            WHERE user_name = ? AND passed = 1
            GROUP BY problem_id
            ORDER BY last_solved DESC
        """, (user_name,)).fetchall()

        # Recent submissions (last 20)
        recent_rows = conn.execute("""
            SELECT problem_id, problem_title, language, passed,
                   tests_passed, tests_total, time_taken_s, submitted_at
            FROM submissions
            WHERE user_name = ?
            ORDER BY submitted_at DESC
            LIMIT 20
        """, (user_name,)).fetchall()

        # Difficulty breakdown (requires join with problem metadata we don't store,
        # so we track easy/medium/hard via problem_id prefixes — real impl would
        # store difficulty on submission)
        diff_row = conn.execute("""
            SELECT
                SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END) as solved_any
            FROM submissions WHERE user_name=?
        """, (user_name,)).fetchone()

    solved_list = [
        {
            "problem_id":     r["problem_id"],
            "problem_title":  r["problem_title"],
            "language":       r["language"],
            "best_time_s":    round(r["best_time"] or 0, 1),
            "last_solved":    r["last_solved"],
            "complexity_time": r["complexity_time"],
            "originality":    r["originality"],
        }
        for r in solved_rows
    ]

    recent_list = [
        {
            "problem_id":    r["problem_id"],
            "problem_title": r["problem_title"],
            "language":      r["language"],
            "passed":        bool(r["passed"]),
            "tests":         f"{r['tests_passed']}/{r['tests_total']}",
            "time_s":        round(r["time_taken_s"] or 0, 1),
            "submitted_at":  r["submitted_at"],
        }
        for r in recent_rows
    ]

    return {
        "user_name":          user_name,
        "problems_solved":    row["solved"] or 0,
        "problems_attempted": row["attempted"] or 0,
        "total_submissions":  row["total_submissions"] or 0,
        "solve_rate":         round((row["solved"] or 0) / max(row["attempted"] or 1, 1) * 100),
        "avg_solve_time_s":   round(row["avg_solve_time"] or 0, 1),
        "solved_problems":    solved_list,
        "recent_submissions": recent_list,
    }


def get_leaderboard(limit: int = 20) -> list[dict]:
    """Global leaderboard — ranked by problems solved."""
    with db() as conn:
        rows = conn.execute("""
            SELECT
                user_name,
                COUNT(DISTINCT CASE WHEN passed=1 THEN problem_id END) AS solved,
                COUNT(DISTINCT problem_id)                              AS attempted,
                COUNT(*)                                                AS submissions,
                MIN(submitted_at)                                       AS first_seen
            FROM submissions
            GROUP BY user_name
            ORDER BY solved DESC, submissions ASC
            LIMIT ?
        """, (limit,)).fetchall()

    return [
        {
            "rank":        i + 1,
            "user_name":   r["user_name"],
            "solved":      r["solved"],
            "attempted":   r["attempted"],
            "submissions": r["submissions"],
        }
        for i, r in enumerate(rows)
    ]


def get_problem_stats(problem_id: str) -> dict | None:
    """How many people have solved this problem and average time."""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM problem_stats WHERE problem_id = ?", (problem_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "problem_id":     row["problem_id"],
        "total_attempts": row["total_attempts"],
        "total_solved":   row["total_solved"],
        "solve_rate":     round(row["total_solved"] / max(row["total_attempts"], 1) * 100),
        "avg_time_s":     round(row["avg_time_s"], 1),
    }
