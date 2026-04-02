import sqlite3
import json
from datetime import datetime
from pathlib import Path


DB_PATH = Path("/config/apps/pv_planner/data/plans.db")


def _ensure_learning_tables(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS plan_validation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_date TEXT,
            created_at TEXT,
            data TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS learning_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)


def save_plan(plan_date: str, plan: dict, inputs: dict) -> None:
    """
    Zapisuje plan D+1 do plans.db.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_date TEXT UNIQUE,
                created_at TEXT,
                executed_at TEXT,
                data TEXT
            )
        """)

        # --- MIGRACJA: dodanie executed_at jeśli nie istnieje ---
        cur.execute("PRAGMA table_info(plans)")
        columns = [row[1] for row in cur.fetchall()]

        if "executed_at" not in columns:
            cur.execute("ALTER TABLE plans ADD COLUMN executed_at TEXT")
        _ensure_learning_tables(cur)

        payload = {
            "plan": plan,
            "inputs": inputs
        }

        cur.execute("""
            INSERT INTO plans (plan_date, created_at, data)
            VALUES (?, ?, ?)
            ON CONFLICT(plan_date) DO UPDATE SET
                created_at = excluded.created_at,
                data = excluded.data
        """, (
            plan_date,
            datetime.utcnow().isoformat(),
            json.dumps(payload, ensure_ascii=False)
        ))

        conn.commit()

    finally:
        conn.close()

def mark_plan_executed(plan_date: str) -> None:
    """
    Oznacza plan jako wykonany (ustawia executed_at).
    """
    if not DB_PATH.exists():
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE plans
            SET executed_at = ?
            WHERE plan_date = ? AND executed_at IS NULL
            """,
            (datetime.utcnow().isoformat(), plan_date)
        )
        conn.commit()
    finally:
        conn.close()


def save_plan_validation(plan_date: str, validation: dict) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        _ensure_learning_tables(cur)
        cur.execute(
            """
            INSERT INTO plan_validation (plan_date, created_at, data)
            VALUES (?, ?, ?)
            """,
            (plan_date, datetime.utcnow().isoformat(), json.dumps(validation, ensure_ascii=False))
        )
        conn.commit()
    finally:
        conn.close()


def get_learning_state(key: str, default_value: float = 0.0) -> float:
    if not DB_PATH.exists():
        return default_value

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        _ensure_learning_tables(cur)
        cur.execute("SELECT value FROM learning_state WHERE key = ?", (key,))
        row = cur.fetchone()
        if not row:
            return default_value
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return default_value
    finally:
        conn.close()


def set_learning_state(key: str, value: float) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        _ensure_learning_tables(cur)
        cur.execute(
            """
            INSERT INTO learning_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, str(value), datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        conn.close()
