import json
import os
import glob
from datetime import datetime, timedelta

from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    redirect,
    url_for,
    session,
    abort,
)

import db

BASE = os.path.dirname(__file__)
ROADMAP_DIR = os.path.join(BASE, "roadmaps")
PROFILE_DIR = os.path.join(BASE, "profiles")

app = Flask(__name__)
app.secret_key = "pathpilot-local-first-secret"


# ---------------------------------------------------------------- data loaders
def load_roadmaps():
    roadmaps = {}
    for path in glob.glob(os.path.join(ROADMAP_DIR, "*.json")):
        with open(path) as f:
            rm = json.load(f)
            roadmaps[rm["id"]] = rm
    return roadmaps


def load_roadmap(rid):
    path = os.path.join(ROADMAP_DIR, f"{rid}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def load_profile(name):
    path = os.path.join(PROFILE_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def save_profile(name, data):
    os.makedirs(PROFILE_DIR, exist_ok=True)
    with open(os.path.join(PROFILE_DIR, f"{name}.json"), "w") as f:
        json.dump(data, f, indent=2)


def list_profiles():
    out = []
    for path in glob.glob(os.path.join(PROFILE_DIR, "*.json")):
        slug = os.path.splitext(os.path.basename(path))[0]
        with open(path) as f:
            data = json.load(f)
        data["slug"] = slug  # filename the key routes use
        data.setdefault("name", slug)  # display name
        out.append(data)
    return out


def current_profile_name():
    return session.get("profile", "mueed")


def current_profile():
    p = load_profile(current_profile_name())
    if not p:  # fall back to guest
        session["profile"] = "guest"
        p = load_profile("guest")
    return p


# ---------------------------------------------------------- progress computation
def milestone_view(milestone, progress_row):
    pr = progress_row or {}
    checklist = {}
    if pr.get("checklist"):
        try:
            checklist = json.loads(pr["checklist"])
        except (ValueError, TypeError):
            checklist = {}
    topics_done = {}
    if pr.get("topics_done"):
        try:
            topics_done = json.loads(pr["topics_done"])
        except (ValueError, TypeError):
            topics_done = {}
    delivs = milestone.get("deliverables", [])
    if delivs:
        done = sum(1 for d in delivs if checklist.get(d))
        derived = round(done / len(delivs) * 100)
    else:
        derived = pr.get("percent", 0)
    percent = pr.get("percent", derived) if pr.get("status") else derived
    status = pr.get("status", "not_started")
    if percent >= 100:
        status = "completed"
    elif percent > 0:
        status = "in_progress"
    return {
        **milestone,
        "percent": percent,
        "status": status,
        "checklist": checklist,
        "topics_done": topics_done,
        "notes": pr.get("notes", ""),
        "github_link": pr.get("github_link", ""),
        "reflection": pr.get("reflection", ""),
        "outcome": pr.get("outcome", ""),
    }


def roadmap_with_progress(rid, profile_name):
    rm = load_roadmap(rid)
    if not rm:
        return None
    prog = db.all_progress(profile_name)
    rm = dict(rm)
    rm["milestones"] = [milestone_view(m, prog.get(m["id"])) for m in rm["milestones"]]
    total = len(rm["milestones"]) or 1
    rm["percent"] = round(sum(m["percent"] for m in rm["milestones"]) / total)
    rm["completed_count"] = sum(
        1 for m in rm["milestones"] if m["status"] == "completed"
    )
    return rm


def pillar_progress(roadmap):
    pillars = {p: [] for p in roadmap.get("pillars", [])}
    for m in roadmap["milestones"]:
        p = m.get("pillar")
        if p in pillars:
            pillars[p].append(m["percent"])
    out = []
    for name, vals in pillars.items():
        pct = round(sum(vals) / len(vals)) if vals else 0
        out.append({"name": name, "percent": pct})
    return out


# ------------------------------------------------------------------ context/base
@app.context_processor
def inject_globals():
    prof = current_profile()
    rm = load_roadmap(prof.get("active_roadmap", "ai_data_engineer"))
    return {
        "profile": prof,
        "profile_name": current_profile_name(),
        "active_roadmap_meta": rm,
        "app_name": "PathPilot",
        "now": datetime.utcnow(),
    }


# ----------------------------------------------------------------------- routes
@app.route("/")
def dashboard():
    prof = current_profile()
    rid = prof.get("active_roadmap", "ai_data_engineer")
    rm = roadmap_with_progress(rid, current_profile_name())
    milestones = rm["milestones"]

    current = next((m for m in milestones if m["status"] == "in_progress"), None)
    if not current:
        current = next((m for m in milestones if m["status"] == "not_started"), None)
    if not current and milestones:
        current = milestones[-1]

    weekend = current.get("weekend_project") if current else None
    upcoming = [m for m in milestones if m["status"] != "completed"][:4]

    conn = db.get_db()
    activity = conn.execute(
        "SELECT * FROM activity WHERE profile=? ORDER BY id DESC LIMIT 6",
        (current_profile_name(),),
    ).fetchall()
    projects = conn.execute(
        "SELECT * FROM projects WHERE profile=? ORDER BY updated_at DESC LIMIT 1",
        (current_profile_name(),),
    ).fetchall()
    conn.close()

    streak = db.streak_info(current_profile_name())
    return render_template(
        "dashboard.html",
        page="dashboard",
        roadmap=rm,
        current=current,
        weekend=weekend,
        upcoming=upcoming,
        pillars=pillar_progress(rm),
        activity=[dict(a) for a in activity],
        current_project=dict(projects[0]) if projects else None,
        streak=streak,
    )


@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    info = db.check_in(current_profile_name())
    prof = current_profile()
    prof["study_streak"] = info["streak"]
    save_profile(current_profile_name(), prof)
    return jsonify({"ok": True, **info})


@app.route("/roadmaps")
def roadmaps():
    prof_name = current_profile_name()
    active = current_profile().get("active_roadmap")
    rms = load_roadmaps()

    pos_to_slot = {
        "top": "top",
        "upper_left": "upper_left",
        "upper_right": "upper_right",
        "center": "lower_left",
        "bottom": "lower_right",
    }
    slots = {}
    leftover = []
    for rid, rm in rms.items():
        withp = roadmap_with_progress(rid, prof_name)
        slot = pos_to_slot.get(rm.get("position"))
        if slot and slot not in slots:
            slots[slot] = withp
        else:
            leftover.append(withp)
    for slot in ["top", "upper_left", "upper_right", "lower_left", "lower_right"]:
        if slot not in slots and leftover:
            slots[slot] = leftover.pop(0)

    def split_label(name):
        words = name.split()
        if len(words) <= 1:
            return [name]
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            diff = abs(len(a) - len(b))
            if best is None or diff < best[0]:
                best = (diff, a, b)
        return [best[1], best[2]]

    for rm in slots.values():
        rm["lines"] = split_label(rm["name"])

    active_rm = roadmap_with_progress(active, prof_name) if active else None
    if not active_rm and slots:
        active_rm = next(iter(slots.values()))

    pcts = [rm["percent"] for rm in slots.values()]
    overall = round(sum(pcts) / len(pcts)) if pcts else 0
    streak = db.streak_info(prof_name)
    return render_template(
        "roadmaps.html",
        page="roadmaps",
        slots=slots,
        active=active,
        active_rm=active_rm,
        overall=overall,
        streak=streak,
    )


@app.route("/roadmap/<rid>")
def roadmap_detail(rid):
    rm = roadmap_with_progress(rid, current_profile_name())
    if not rm:
        abort(404)
    return render_template(
        "roadmap_detail.html", page="roadmaps", roadmap=rm, pillars=pillar_progress(rm)
    )


@app.route("/roadmap/<rid>/activate", methods=["POST"])
def activate_roadmap(rid):
    prof = current_profile()
    prof["active_roadmap"] = rid
    save_profile(current_profile_name(), prof)
    db.log_activity(
        current_profile_name(), "roadmap", f"Switched to {rid.replace('_',' ').title()}"
    )
    return jsonify({"ok": True})


@app.route("/milestones")
def milestones():
    prof = current_profile()
    rid = prof.get("active_roadmap", "ai_data_engineer")
    rm = roadmap_with_progress(rid, current_profile_name())
    return render_template("milestones.html", page="milestones", roadmap=rm)


@app.route("/milestone/<mid>")
def milestone_detail(mid):
    prof = current_profile()
    rid = prof.get("active_roadmap", "ai_data_engineer")
    rm = roadmap_with_progress(rid, current_profile_name())
    m = next((x for x in rm["milestones"] if x["id"] == mid), None)
    if not m:
        for other in load_roadmaps():
            orm = roadmap_with_progress(other, current_profile_name())
            m = next((x for x in orm["milestones"] if x["id"] == mid), None)
            if m:
                rm = orm
                break
    if not m:
        abort(404)
    return render_template("milestone_detail.html", page="milestones", roadmap=rm, m=m)


@app.route("/api/milestone/<mid>", methods=["POST"])
def api_milestone_update(mid):
    data = request.get_json(force=True)
    fields = {}
    for key in ("notes", "github_link", "reflection", "outcome", "status", "percent"):
        if key in data:
            fields[key] = data[key]
    if "checklist" in data:
        fields["checklist"] = json.dumps(data["checklist"])
        cl = data["checklist"]
        if cl:
            done = sum(1 for v in cl.values() if v)
            fields["percent"] = round(done / len(cl) * 100)
    if "topics_done" in data:
        fields["topics_done"] = json.dumps(data["topics_done"])
    prof_name = current_profile_name()
    db.upsert_milestone_progress(prof_name, mid, **fields)
    if fields.get("percent") == 100:
        db.log_activity(prof_name, "complete", f"Completed milestone {mid}")
    elif "checklist" in data:
        db.log_activity(prof_name, "progress", f"Progressed on {mid}")
    row = db.get_milestone_progress(prof_name, mid)
    return jsonify({"ok": True, "progress": row})


# ------------------------------------------------------------------- projects
@app.route("/projects")
def projects():
    conn = db.get_db()
    rows = conn.execute(
        "SELECT * FROM projects WHERE profile=? ORDER BY id DESC",
        (current_profile_name(),),
    ).fetchall()
    conn.close()
    cols = {"backlog": [], "in_progress": [], "review": [], "done": []}
    for r in rows:
        cols.setdefault(r["status"], []).append(dict(r))
    return render_template("projects.html", page="projects", columns=cols)


@app.route("/api/projects", methods=["POST"])
def api_project_create():
    data = request.get_json(force=True)
    conn = db.get_db()
    conn.execute(
        """INSERT INTO projects (profile, title, description, status, percent,
           repository, reflection, improvements, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            current_profile_name(),
            data.get("title", "Untitled"),
            data.get("description", ""),
            data.get("status", "backlog"),
            data.get("percent", 0),
            data.get("repository", ""),
            data.get("reflection", ""),
            data.get("improvements", ""),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    db.log_activity(
        current_profile_name(), "project", f"Created project {data.get('title')}"
    )
    return jsonify({"ok": True})


@app.route("/api/projects/<int:pid>", methods=["PATCH", "DELETE"])
def api_project_update(pid):
    conn = db.get_db()
    if request.method == "DELETE":
        conn.execute(
            "DELETE FROM projects WHERE id=? AND profile=?",
            (pid, current_profile_name()),
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    data = request.get_json(force=True)
    allowed = (
        "title",
        "description",
        "status",
        "percent",
        "repository",
        "reflection",
        "improvements",
    )
    fields = {k: v for k, v in data.items() if k in allowed}
    fields["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE projects SET {cols} WHERE id=? AND profile=?",
        list(fields.values()) + [pid, current_profile_name()],
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------- notes
@app.route("/notes")
def notes():
    conn = db.get_db()
    rows = conn.execute(
        "SELECT * FROM notes WHERE profile=? ORDER BY updated_at DESC",
        (current_profile_name(),),
    ).fetchall()
    conn.close()
    return render_template("notes.html", page="notes", notes=[dict(r) for r in rows])


@app.route("/api/notes", methods=["POST"])
def api_note_create():
    conn = db.get_db()
    cur = conn.execute(
        "INSERT INTO notes (profile, title, body, updated_at) VALUES (?,?,?,?)",
        (current_profile_name(), "Untitled note", "", datetime.utcnow().isoformat()),
    )
    conn.commit()
    nid = cur.lastrowid
    conn.close()
    return jsonify({"ok": True, "id": nid})


@app.route("/api/notes/<int:nid>", methods=["PATCH", "DELETE"])
def api_note_update(nid):
    conn = db.get_db()
    if request.method == "DELETE":
        conn.execute(
            "DELETE FROM notes WHERE id=? AND profile=?", (nid, current_profile_name())
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    data = request.get_json(force=True)
    conn.execute(
        "UPDATE notes SET title=?, body=?, updated_at=? WHERE id=? AND profile=?",
        (
            data.get("title", "Untitled"),
            data.get("body", ""),
            datetime.utcnow().isoformat(),
            nid,
            current_profile_name(),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ----------------------------------------------------------------- statistics
@app.route("/statistics")
def statistics():
    prof = current_profile()
    rid = prof.get("active_roadmap", "ai_data_engineer")
    rm = roadmap_with_progress(rid, current_profile_name())
    conn = db.get_db()
    projects = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM projects WHERE profile=?", (current_profile_name(),)
        ).fetchall()
    ]
    activity = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM activity WHERE profile=? ORDER BY id DESC LIMIT 40",
            (current_profile_name(),),
        ).fetchall()
    ]
    conn.close()

    total_hours = sum(m["hours"] for m in rm["milestones"])
    done_hours = sum(m["hours"] for m in rm["milestones"] if m["status"] == "completed")
    done_hours += sum(
        m["hours"] * m["percent"] // 100
        for m in rm["milestones"]
        if m["status"] == "in_progress"
    )

    stats = {
        "total_hours": total_hours,
        "done_hours": done_hours,
        "milestones_total": len(rm["milestones"]),
        "milestones_done": rm["completed_count"],
        "projects_total": len(projects),
        "projects_done": sum(1 for p in projects if p["status"] == "done"),
        "streak": db.streak_info(current_profile_name())["streak"],
        "roadmap_percent": rm["percent"],
    }
    return render_template(
        "statistics.html",
        page="statistics",
        roadmap=rm,
        pillars=pillar_progress(rm),
        stats=stats,
        projects=projects,
        activity=activity,
        all_roadmaps=[
            roadmap_with_progress(r, current_profile_name()) for r in load_roadmaps()
        ],
    )


# ------------------------------------------------------------------- profiles
@app.route("/profiles")
def profiles():
    return render_template(
        "profiles.html",
        page="profiles",
        profiles=list_profiles(),
        active=current_profile_name(),
    )


@app.route("/profiles/switch/<name>", methods=["POST"])
def switch_profile(name):
    if load_profile(name):
        session["profile"] = name
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 404


@app.route("/profiles/delete/<name>", methods=["POST"])
def delete_profile(name):
    slugs = [p["slug"] for p in list_profiles()]
    if name not in slugs:
        return jsonify({"ok": False, "error": "No such profile"}), 404
    if len(slugs) <= 1:
        return jsonify({"ok": False, "error": "Can't delete your only profile"}), 400

    path = os.path.join(PROFILE_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)
    conn = db.get_db()
    for table in ("milestone_progress", "projects", "notes", "activity"):
        conn.execute(f"DELETE FROM {table} WHERE profile=?", (name,))
    conn.commit()
    conn.close()

    new_active = current_profile_name()
    if name == current_profile_name():
        new_active = next(s for s in slugs if s != name)
        session["profile"] = new_active
    return jsonify({"ok": True, "switched_to": new_active})


@app.route("/profiles/create", methods=["POST"])
def create_profile():
    data = request.get_json(force=True)
    name = data.get("name", "").strip().lower().replace(" ", "_")
    if not name or load_profile(name):
        return jsonify({"ok": False, "error": "Name taken or invalid"}), 400
    save_profile(
        name,
        {
            "name": data.get("name", name).strip(),
            "avatar": data.get("name", "P")[0].upper(),
            "active_roadmap": data.get("active_roadmap", "ai_data_engineer"),
            "study_streak": 0,
            "created": datetime.utcnow().strftime("%Y-%m-%d"),
            "completed_milestones": [],
            "in_progress_milestone": "",
            "settings": {"theme": "light"},
        },
    )
    return jsonify({"ok": True, "name": name})


@app.route("/profiles/export/<name>")
def export_profile(name):
    prof = load_profile(name)
    if not prof:
        abort(404)
    conn = db.get_db()
    prog = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM milestone_progress WHERE profile=?", (name,)
        ).fetchall()
    ]
    projects = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM projects WHERE profile=?", (name,)
        ).fetchall()
    ]
    notes = [
        dict(r)
        for r in conn.execute("SELECT * FROM notes WHERE profile=?", (name,)).fetchall()
    ]
    conn.close()
    bundle = {
        "profile": prof,
        "milestone_progress": prog,
        "projects": projects,
        "notes": notes,
        "exported_at": datetime.utcnow().isoformat(),
    }
    return app.response_class(
        json.dumps(bundle, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={name}_pathpilot.json"},
    )


@app.route("/profiles/import", methods=["POST"])
def import_profile():
    try:
        bundle = request.get_json(force=True)
        prof = bundle["profile"]
        name = prof["name"].strip().lower().replace(" ", "_")
        save_profile(name, prof)
        conn = db.get_db()
        for row in bundle.get("milestone_progress", []):
            row = {k: v for k, v in row.items() if k != "id"}
            row["profile"] = name
            cols = ", ".join(row.keys())
            ph = ", ".join("?" for _ in row)
            conn.execute(
                f"INSERT OR REPLACE INTO milestone_progress ({cols}) VALUES ({ph})",
                list(row.values()),
            )
        for row in bundle.get("projects", []):
            row = {k: v for k, v in row.items() if k != "id"}
            row["profile"] = name
            cols = ", ".join(row.keys())
            ph = ", ".join("?" for _ in row)
            conn.execute(
                f"INSERT INTO projects ({cols}) VALUES ({ph})", list(row.values())
            )
        for row in bundle.get("notes", []):
            row = {k: v for k, v in row.items() if k != "id"}
            row["profile"] = name
            cols = ", ".join(row.keys())
            ph = ", ".join("?" for _ in row)
            conn.execute(
                f"INSERT INTO notes ({cols}) VALUES ({ph})", list(row.values())
            )
        conn.commit()
        conn.close()
        session["profile"] = name
        return jsonify({"ok": True, "name": name})
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/theme", methods=["POST"])
def api_theme():
    data = request.get_json(force=True)
    prof = current_profile()
    prof.setdefault("settings", {})["theme"] = data.get("theme", "light")
    save_profile(current_profile_name(), prof)
    return jsonify({"ok": True})


@app.template_filter("titlecase")
def titlecase(s):
    return str(s).replace("_", " ").title()


_TOPIC_ACRONYMS = {
    "oop": "OOP",
    "vs": "VS",
    "bi": "BI",
    "api": "API",
    "apis": "APIs",
    "sql": "SQL",
    "eda": "EDA",
    "etl": "ETL",
    "kpi": "KPI",
    "kpis": "KPIs",
    "ui": "UI",
    "ux": "UX",
    "rag": "RAG",
    "llm": "LLM",
    "llms": "LLMs",
    "ai": "AI",
    "ml": "ML",
    "crud": "CRUD",
    "json": "JSON",
    "rest": "REST",
    "pc": "PC",
    "css": "CSS",
    "html": "HTML",
    "orm": "ORM",
}
_TOPIC_BRANDS = {
    "github": "GitHub",
    "numpy": "NumPy",
    "postgresql": "PostgreSQL",
    "sqlite": "SQLite",
    "javascript": "JavaScript",
    "fastapi": "FastAPI",
    "readme": "README",
    "powerbi": "PowerBI",
    "pandas": "pandas",
}
_TOPIC_SMALL = {"to", "of", "and", "the", "for", "in", "on", "with", "vs."}


@app.template_filter("topiccase")
def topiccase(s):
    words = str(s).replace("_", " ").split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in _TOPIC_ACRONYMS:
            out.append(_TOPIC_ACRONYMS[lw])
        elif lw in _TOPIC_BRANDS:
            out.append(_TOPIC_BRANDS[lw])
        elif lw in _TOPIC_SMALL and i != 0:
            out.append(lw)
        elif w[:1].isalpha():
            out.append(w[:1].upper() + w[1:])
        else:
            out.append(w)
    return " ".join(out)


if __name__ == "__main__":
    db.init_db()
    conn = db.get_db()
    has = conn.execute(
        "SELECT COUNT(*) c FROM projects WHERE profile='mueed'"
    ).fetchone()["c"]
    if not has:
        seed = [
            (
                "Expense Analytics",
                "Pandas EDA over my own expense data with charts.",
                "in_progress",
                60,
                "github.com/mueed/expense-analytics",
                "Cleaning the categories took longer than the analysis.",
                "Add month-over-month trends.",
                "aide-m3",
            ),
            (
                "Expense Tracker Database",
                "SQLite schema for expenses and categories, driven from Python.",
                "done",
                100,
                "github.com/mueed/expense-db",
                "Designing the schema first made the code simpler.",
                "Add a migrations step.",
                "aide-m2",
            ),
            (
                "AI Financial Assistant",
                "LLM feature that answers questions about spending.",
                "backlog",
                0,
                "",
                "",
                "",
                "aide-m6",
            ),
        ]
        for s in seed:
            conn.execute(
                """INSERT INTO projects (profile,title,description,status,percent,
                   repository,reflection,improvements,milestone_id,updated_at)
                   VALUES ('mueed',?,?,?,?,?,?,?,?,?)""",
                (*s, datetime.utcnow().isoformat()),
            )
        from datetime import date, timedelta

        for i in range(11, 0, -1):
            d = (date.today() - timedelta(days=i)).isoformat()
            conn.execute(
                "INSERT INTO activity (profile,kind,label,created_at) VALUES ('mueed','study',?,?)",
                ("Studied", d + "T09:00:00"),
            )
        for lbl in [
            "Completed milestone SQL & Databases",
            "Created project Expense Analytics",
            "Progressed on Data & Analytics",
            "Wrote a reflection note",
        ]:
            conn.execute(
                "INSERT INTO activity (profile,kind,label,created_at) VALUES ('mueed','seed',?,?)",
                (lbl, datetime.utcnow().isoformat()),
            )
        conn.execute(
            "INSERT INTO notes (profile,title,body,updated_at) VALUES ('mueed','SQL learnings','Design the schema before writing code. Keep categories in their own table so reporting stays clean.',?)",
            (datetime.utcnow().isoformat(),),
        )
    conn.commit()
    conn.close()
    app.run(debug=True, port=5000)
