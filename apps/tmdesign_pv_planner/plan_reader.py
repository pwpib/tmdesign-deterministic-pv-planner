import sqlite3
import json
from datetime import date
from pathlib import Path

DB_PATH = Path("/config/apps/pv_planner/data/plans.db")


def load_plan_for_today():
    """
    Odczytuje plan na DZISIAJ (D) z plans.db.
    Zwraca dict albo None.
    """
    if not DB_PATH.exists():
        return None

    today = date.today().isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT data FROM plans WHERE plan_date = ?",
            (today,)
        )
        row = cur.fetchone()
        if not row:
            return None

        return json.loads(row[0])

    finally:
        conn.close()


def load_plan_for_tomorrow():
    """
    Odczytuje plan na JUTRO (D+1) z plans.db.
    Zwraca dict albo None.
    """
    if not DB_PATH.exists():
        return None

    tomorrow = (date.today().toordinal() + 1)
    tomorrow = date.fromordinal(tomorrow).isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT data FROM plans WHERE plan_date = ?",
            (tomorrow,)
        )
        row = cur.fetchone()
        if not row:
            return None

        return json.loads(row[0])

    finally:
        conn.close()

def is_plan_executed(plan_date: str) -> bool:
    """
    Zwraca True, jeśli plan na daną datę był już wykonany.
    """
    if not DB_PATH.exists():
        return False

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT executed_at FROM plans WHERE plan_date = ?",
            (plan_date,)
        )
        row = cur.fetchone()
        if not row:
            return False

        return row[0] is not None

    finally:
        conn.close()
