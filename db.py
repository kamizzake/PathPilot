import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "pathpilot.db")


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS milestone_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT NOT NULL,
            milestone_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'not_started',
            percent INTEGER NOT NULL DEFAULT 0,
            checklist TEXT NOT NULL DEFAULT '{}',
            topics_done TEXT NOT NULL DEFAULT '{}',
            notes TEXT DEFAULT '',
            github_link TEXT DEFAULT '',
            reflection TEXT DEFAULT '',
            outcome TEXT DEFAULT '',
            updated_at TEXT,
            UNIQUE(profile, milestone_id)
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'backlog',
            percent INTEGER NOT NULL DEFAULT 0,
            repository TEXT DEFAULT '',
            reflection TEXT DEFAULT '',
            improvements TEXT DEFAULT '',
            milestone_id TEXT DEFAULT '',
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT 'Untitled',
            body TEXT DEFAULT '',
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            created_at TEXT
        );
        """)
    cols = [
        r["name"] for r in c.execute("PRAGMA table_info(milestone_progress)").fetchall()
    ]
    if "topics_done" not in cols:
        c.execute(
            "ALTER TABLE milestone_progress ADD COLUMN topics_done TEXT NOT NULL DEFAULT '{}'"
        )
    conn.commit()
    conn.close()


def log_activity(profile, kind, label):
    conn = get_db()
    conn.execute(
        "INSERT INTO activity (profile, kind, label, created_at) VALUES (?,?,?,?)",
        (profile, kind, label, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_milestone_progress(profile, milestone_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM milestone_progress WHERE profile=? AND milestone_id=?",
        (profile, milestone_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_milestone_progress(profile, milestone_id, **fields):
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM milestone_progress WHERE profile=? AND milestone_id=?",
        (profile, milestone_id),
    ).fetchone()
    fields["updated_at"] = datetime.utcnow().isoformat()
    if existing:
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [profile, milestone_id]
        conn.execute(
            f"UPDATE milestone_progress SET {cols} WHERE profile=? AND milestone_id=?",
            vals,
        )
    else:
        fields.update({"profile": profile, "milestone_id": milestone_id})
        cols = ", ".join(fields.keys())
        ph = ", ".join("?" for _ in fields)
        conn.execute(
            f"INSERT INTO milestone_progress ({cols}) VALUES ({ph})",
            list(fields.values()),
        )
    conn.commit()
    conn.close()


def all_progress(profile):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM milestone_progress WHERE profile=?", (profile,)
    ).fetchall()
    conn.close()
    return {r["milestone_id"]: dict(r) for r in rows}


# --------------------------------------------------------------------- streaks
from datetime import date, timedelta


def study_dates(profile):
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT substr(created_at,1,10) AS d FROM activity "
        "WHERE profile=? AND created_at IS NOT NULL ORDER BY d",
        (profile,),
    ).fetchall()
    conn.close()
    return {r["d"] for r in rows if r["d"]}


def _longest_streak(dates):
    if not dates:
        return 0
    ordered = sorted(date.fromisoformat(d) for d in dates)
    best = run = 1
    for prev, cur in zip(ordered, ordered[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)
    return best


def streak_info(profile):
    dates = study_dates(profile)
    today = date.today()
    checked_in = today.isoformat() in dates

    anchor = today if checked_in else today - timedelta(days=1)
    current = 0
    if anchor.isoformat() in dates:
        d = anchor
        while d.isoformat() in dates:
            current += 1
            d -= timedelta(days=1)

    week = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        week.append(
            {
                "label": d.strftime("%a")[0],
                "active": d.isoformat() in dates,
                "today": d == today,
            }
        )

    return {
        "streak": current,
        "checked_in": checked_in,
        "week": week,
        "longest": _longest_streak(dates),
    }


def check_in(profile):
    today = date.today().isoformat()
    if today not in study_dates(profile):
        log_activity(profile, "study", "Studied today")
    return streak_info(profile)
