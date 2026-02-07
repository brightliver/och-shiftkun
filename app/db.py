from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "och_shiftkun.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            doctor TEXT NOT NULL,
            request_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            table_text TEXT NOT NULL,
            counts_text TEXT NOT NULL,
            change_log TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS travel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            doctor TEXT NOT NULL,
            days INTEGER,
            dates_text TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(month, doctor)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS config_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            editor TEXT NOT NULL,
            staff_list TEXT NOT NULL,
            base_rules TEXT NOT NULL,
            individual_rules TEXT NOT NULL,
            additional_rules TEXT NOT NULL
        )
        """
    )
    try:
        cur.execute("ALTER TABLE config_history ADD COLUMN editor TEXT NOT NULL DEFAULT 'unknown'")
    except sqlite3.OperationalError:
        pass
    # Lightweight migration for existing DBs
    try:
        cur.execute("ALTER TABLE schedules ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def add_request(month: str, doctor: str, request_text: str, created_at: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO requests (month, doctor, request_text, created_at) VALUES (?, ?, ?, ?)",
        (month, doctor, request_text, created_at),
    )
    conn.commit()
    conn.close()


def list_requests(month: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, doctor, request_text, created_at FROM requests WHERE month=? ORDER BY created_at ASC",
        (month,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_requests_by_doctor(month: str, doctor: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, doctor, request_text, created_at FROM requests WHERE month=? AND doctor=? ORDER BY created_at ASC",
        (month, doctor),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_request(request_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM requests WHERE id=?", (request_id,))
    conn.commit()
    conn.close()


def upsert_travel(month: str, doctor: str, days: int | None, dates_text: str | None, created_at: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id FROM travel WHERE month=? AND doctor=?",
        (month, doctor),
    ).fetchone()
    if existing:
        cur.execute(
            "UPDATE travel SET days=?, dates_text=?, created_at=? WHERE month=? AND doctor=?",
            (days, dates_text, created_at, month, doctor),
        )
    else:
        cur.execute(
            "INSERT INTO travel (month, doctor, days, dates_text, created_at) VALUES (?, ?, ?, ?, ?)",
            (month, doctor, days, dates_text, created_at),
        )
    conn.commit()
    conn.close()


def list_travel(month: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT doctor, days, dates_text, created_at FROM travel WHERE month=? ORDER BY doctor ASC",
        (month,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_travel(month: str, doctor: str) -> Dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT doctor, days, dates_text, created_at FROM travel WHERE month=? AND doctor=?",
        (month, doctor),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_config_map() -> Dict[str, str]:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_config_map(data: Dict[str, str]) -> None:
    conn = get_conn()
    cur = conn.cursor()
    for key, value in data.items():
        cur.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
    conn.commit()
    conn.close()


def add_config_history(
    staff_list: str,
    base_rules: str,
    individual_rules: str,
    additional_rules: str,
    created_at: str,
    editor: str,
) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO config_history (created_at, editor, staff_list, base_rules, individual_rules, additional_rules) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (created_at, editor, staff_list, base_rules, individual_rules, additional_rules),
    )
    conn.commit()
    conn.close()


def list_config_history(limit: int | None = 10) -> List[Dict[str, Any]]:
    conn = get_conn()
    if limit is None:
        rows = conn.execute(
            "SELECT created_at, editor, staff_list, base_rules, individual_rules, additional_rules "
            "FROM config_history ORDER BY id DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT created_at, editor, staff_list, base_rules, individual_rules, additional_rules "
            "FROM config_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_schedule(
    month: str,
    status: str,
    table_text: str,
    counts_text: str,
    change_log: str,
    created_at: str,
) -> None:
    conn = get_conn()
    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id FROM schedules WHERE month=? AND status=?",
        (month, status),
    ).fetchone()
    if existing:
        cur.execute(
            "UPDATE schedules SET table_text=?, counts_text=?, change_log=?, created_at=? WHERE month=? AND status=?",
            (table_text, counts_text, change_log, created_at, month, status),
        )
    else:
        cur.execute(
            "INSERT INTO schedules (month, status, table_text, counts_text, change_log, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (month, status, table_text, counts_text, change_log, created_at),
        )
    conn.commit()
    conn.close()


def get_schedule(month: str, status: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute(
        "SELECT month, status, table_text, counts_text, change_log, created_at FROM schedules WHERE month=? AND status=?",
        (month, status),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_latest_schedule(month: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute(
        "SELECT month, status, table_text, counts_text, change_log, created_at "
        "FROM schedules WHERE month=? ORDER BY created_at DESC LIMIT 1",
        (month,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def export_all() -> Dict[str, Any]:
    conn = get_conn()
    data = {
        "requests": [
            dict(r)
            for r in conn.execute(
                "SELECT id, month, doctor, request_text, created_at FROM requests ORDER BY id ASC"
            ).fetchall()
        ],
        "schedules": [
            dict(r)
            for r in conn.execute(
                "SELECT id, month, status, table_text, counts_text, change_log, created_at FROM schedules ORDER BY id ASC"
            ).fetchall()
        ],
        "travel": [
            dict(r)
            for r in conn.execute(
                "SELECT id, month, doctor, days, dates_text, created_at FROM travel ORDER BY id ASC"
            ).fetchall()
        ],
        "config": [
            dict(r)
            for r in conn.execute(
                "SELECT key, value FROM config ORDER BY key ASC"
            ).fetchall()
        ],
        "config_history": [
            dict(r)
            for r in conn.execute(
                "SELECT id, created_at, editor, staff_list, base_rules, individual_rules, additional_rules "
                "FROM config_history ORDER BY id ASC"
            ).fetchall()
        ],
    }
    conn.close()
    return data


def restore_all(data: Dict[str, Any]) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM requests")
    cur.execute("DELETE FROM schedules")
    cur.execute("DELETE FROM travel")
    cur.execute("DELETE FROM config")
    cur.execute("DELETE FROM config_history")

    for r in data.get("requests", []):
        cur.execute(
            "INSERT INTO requests (month, doctor, request_text, created_at) VALUES (?, ?, ?, ?)",
            (r.get("month", ""), r.get("doctor", ""), r.get("request_text", ""), r.get("created_at", "")),
        )
    for s in data.get("schedules", []):
        cur.execute(
            "INSERT INTO schedules (month, status, table_text, counts_text, change_log, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                s.get("month", ""),
                s.get("status", "draft"),
                s.get("table_text", ""),
                s.get("counts_text", ""),
                s.get("change_log", ""),
                s.get("created_at", ""),
            ),
        )
    for t in data.get("travel", []):
        cur.execute(
            "INSERT INTO travel (month, doctor, days, dates_text, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                t.get("month", ""),
                t.get("doctor", ""),
                t.get("days"),
                t.get("dates_text"),
                t.get("created_at", ""),
            ),
        )
    for c in data.get("config", []):
        cur.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)",
            (c.get("key", ""), c.get("value", "")),
        )
    for h in data.get("config_history", []):
        cur.execute(
            "INSERT INTO config_history (created_at, editor, staff_list, base_rules, individual_rules, additional_rules) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                h.get("created_at", ""),
                h.get("editor", ""),
                h.get("staff_list", ""),
                h.get("base_rules", ""),
                h.get("individual_rules", ""),
                h.get("additional_rules", ""),
            ),
        )
    conn.commit()
    conn.close()
