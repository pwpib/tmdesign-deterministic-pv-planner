import sqlite3
import json
from datetime import datetime
from pathlib import Path


DB_PATH = Path("/config/apps/pv_planner/data/plans.db")


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
