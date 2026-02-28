from flask import Flask, render_template, request, redirect, url_for, abort, session, flash
import json
import re
import datetime
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)

# NOTE: In production, set this via an environment variable.
app.secret_key = "dev-secret-change-me"

DATA_DIR = Path("data")
DATA_PATH = DATA_DIR / "tasks.json"  # legacy (kept for backward compatibility)
USERS_PATH = DATA_DIR / "users.json"
USER_TASKS_DIR = DATA_DIR / "user_tasks"

# ------------------------------------------------------------
# About page content (Keep the text intact)
# ------------------------------------------------------------

ABOUT_PARAGRAPHS = [
    "We are Team 5, a group of students from diverse technical and academic backgrounds collaborating on the Task Tracker productivity web app. Our goal is to design a simple, lightweight tool that helps students and everyday users organize tasks in one place without unnecessary complexity.",
    "Our team brings together perspectives from psychology, computer science, app development, networking, and electronics. This mix of disciplines helps us think about both the human side of productivity and the technical side of building reliable software. By combining our skills, we aim to create an app that is intuitive, efficient, and focused on real user needs.",
    "Task Tracker reflects our shared interest in practical problem-solving: helping people stay organized, reduce stress, and manage their work more effectively through a clean, minimal interface.",
    "Here is a little bit about what our team members are studying for their majors!",
]
ABOUT_TEAM_MEMBERS = [
    {"name": "Ankhzaya", "role": "AAS App Development", "bio": ""},
    {"name": "Ali", "role": "AAS Network & Server Administration Specialist", "bio": ""},
    {"name": "John", "role": "AAS Electronics", "bio": ""},
    {"name": "Drake", "role": "Computer Science", "bio": ""},
    {"name": "Nil", "role": "Psychology", "bio": ""},
]


def ensure_data_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_PATH.exists():
        with USERS_PATH.open("w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def load_users():
    ensure_data_files()
    try:
        with USERS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_users(users):
    ensure_data_files()
    with USERS_PATH.open("w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def find_user(users, *, username=None, email=None, user_id=None):
    for u in users:
        if user_id is not None and u.get("id") == user_id:
            return u
        if username and u.get("username", "").lower() == username.lower():
            return u
        if email and u.get("email", "").lower() == email.lower():
            return u
    return None


def next_user_id(users):
    if not users:
        return 1
    return max([u.get("id", 0) for u in users]) + 1


def task_file_for_user(user_id: int) -> Path:
    return USER_TASKS_DIR / f"user_{user_id}_tasks.json"


def load_tasks(user_id=None):
    """Load tasks for a user. If user_id is None, falls back to legacy tasks.json."""
    ensure_data_files()
    if user_id is None:
        path = DATA_PATH
    else:
        path = task_file_for_user(int(user_id))
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_tasks(tasks, user_id=None):
    """Save tasks for a user. If user_id is None, saves to legacy tasks.json."""
    ensure_data_files()
    if user_id is None:
        path = DATA_PATH
    else:
        path = task_file_for_user(int(user_id))
    with path.open("w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    users = load_users()
    return find_user(users, user_id=user_id)


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)

    return wrapper


def is_valid_email(email: str) -> bool:
    # Simple, practical email format check for a class project (not fully RFC compliant)
    # Requires: local@domain.tld (at least one dot in the domain part)
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def next_id(tasks):
    return max((t.get("id", 0) for t in tasks), default=0) + 1


def compute_stats(tasks):
    total = len(tasks)
    complete = sum(1 for t in tasks if t.get("status") == "complete")
    incomplete = total - complete
    return total, complete, incomplete


def parse_date_yyyy_mm_dd(value: str):
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def sort_tasks(tasks, sort_key: str):
    """Return a new list sorted by the selected option."""
    sort_key = (sort_key or "").strip()

    if sort_key == "due_asc":
        # Tasks without due date go last
        return sorted(
            tasks,
            key=lambda t: (
                parse_date_yyyy_mm_dd(t.get("due_date")) is None,
                parse_date_yyyy_mm_dd(t.get("due_date")) or datetime.date.max,
                (t.get("created_at") or ""),
            ),
        )

    if sort_key == "due_desc":
        return sorted(
            tasks,
            key=lambda t: (
                parse_date_yyyy_mm_dd(t.get("due_date")) is None,
                -(parse_date_yyyy_mm_dd(t.get("due_date")) or datetime.date.min).toordinal(),
                (t.get("created_at") or ""),
            ),
        )

    if sort_key == "status":
        # Incomplete first, then complete
        return sorted(
            tasks,
            key=lambda t: (t.get("status") == "complete", (t.get("created_at") or "")),
            reverse=False,
        )

    if sort_key == "newest":
        return sorted(tasks, key=lambda t: (t.get("created_at") or ""), reverse=True)

    if sort_key == "oldest":
        return sorted(tasks, key=lambda t: (t.get("created_at") or ""), reverse=False)

    # default: keep existing order
    return tasks


def find_task(tasks, task_id):
    return next((t for t in tasks if t.get("id") == task_id), None)


def current_home_query_defaults():
    """
    Build a querystring dict for /home so POST routes can preserve the user's filters.
    We prefer form fields (hidden inputs) first, then fallback to request.args.
    """
    def pick(name, default=""):
        return (request.form.get(name) or request.args.get(name) or default).strip()

    return {
        "sort": pick("sort", "due_asc"),
        "status": pick("status", "all"),
        "q": pick("q", ""),
        "due": pick("due", ""),
        "due_from": pick("due_from", ""),
        "due_to": pick("due_to", ""),
    }


@app.get("/")
def landing_page():
    return render_template("landing.html")


@app.get("/about")
def about_page():
    return render_template(
        "about.html",
        about_title="About Us",
        about_paragraphs=ABOUT_PARAGRAPHS,
        team_members=ABOUT_TEAM_MEMBERS,
    )


@app.get("/privacy")
def privacy_page():
    return render_template("privacy.html")


# ------------------------------------------------------------
# Auth (Register / Login / Logout)
# ------------------------------------------------------------

@app.get("/register")
def register():
    if session.get("user_id"):
        return redirect(url_for("home_page"))
    return render_template("register.html")


@app.post("/register")
def register_post():
    if session.get("user_id"):
        return redirect(url_for("home_page"))

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    # Basic validation (keep it simple for the class project)
    if not username or not email or not password:
        flash("Please fill out username, email, and password.", "error")
        return redirect(url_for("register"))

    if not is_valid_email(email):
        flash("Please enter a valid email address (example: name@example.com).", "error")
        return redirect(url_for("register"))

    # Optional: simple password minimum length (helps UX without being too strict)
    if len(password) < 6:
        flash("Password must be at least 6 characters long.", "error")
        return redirect(url_for("register"))

    users = load_users()

    if find_user(users, username=username):
        flash("That username is already taken.", "error")
        return redirect(url_for("register"))

    if find_user(users, email=email):
        flash("That email is already registered.", "error")
        return redirect(url_for("register"))

    user = {
        "id": next_user_id(users),
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256", salt_length=16),
    }
    users.append(user)
    save_users(users)

    flash("Account created! Please log in.", "success")
    return redirect(url_for("login"))


@app.get("/login")
def login():
    if session.get("user_id"):
        return redirect(url_for("home_page"))
    return render_template("login.html", next=request.args.get("next", ""))


@app.post("/login")
def login_post():
    if session.get("user_id"):
        return redirect(url_for("home_page"))

    username_or_email = request.form.get("username_or_email", "").strip()
    password = request.form.get("password", "")

    users = load_users()
    user = find_user(users, username=username_or_email) or find_user(users, email=username_or_email)

    if not user or not check_password_hash(user.get("password_hash", ""), password):
        flash("Invalid username/email or password.", "error")
        return redirect(url_for("login", next=request.form.get("next", "")))

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    flash(f"Welcome back, {user['username']}!", "success")
    next_url = request.form.get("next") or url_for("home_page")
    # Simple safety: only allow relative redirects
    if next_url.startswith("http://") or next_url.startswith("https://"):
        next_url = url_for("home_page")
    return redirect(next_url)


@app.get("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("landing_page"))


# ------------------------------------------------------------
# Home + Filters
# ------------------------------------------------------------

def apply_filters(tasks, *, status="all", q="", due="", due_from="", due_to=""):
    """
    Filters:
      - status: all | complete | incomplete
      - q: case-insensitive contains search in title + memo
      - due: exact due date
      - due_from / due_to: inclusive range
    Returns: (filtered_tasks, active_filters_list, error_messages_list)
    """
    active = []
    errors = []

    status = (status or "all").strip().lower()
    q = (q or "").strip()
    due = (due or "").strip()
    due_from = (due_from or "").strip()
    due_to = (due_to or "").strip()

    filtered = list(tasks)

    # Status
    if status in ("complete", "incomplete"):
        filtered = [t for t in filtered if (t.get("status") == "complete") == (status == "complete")]
        active.append(f"Status: {status.capitalize()}")
    else:
        status = "all"

    # Search
    if q:
        needle = q.lower()
        def matches(t):
            title = (t.get("title") or "").lower()
            memo = (t.get("memo") or "").lower()
            return (needle in title) or (needle in memo)

        filtered = [t for t in filtered if matches(t)]
        active.append(f"Search: “{q}”")

    # Dates
    due_dt = parse_date_yyyy_mm_dd(due) if due else None
    from_dt = parse_date_yyyy_mm_dd(due_from) if due_from else None
    to_dt = parse_date_yyyy_mm_dd(due_to) if due_to else None

    if due and not due_dt:
        errors.append("Due date filter must be a valid date.")
    if due_from and not from_dt:
        errors.append("From date must be a valid date.")
    if due_to and not to_dt:
        errors.append("To date must be a valid date.")

    # If exact due is set (and valid), it wins over range (simple, predictable UX)
    if due_dt:
        filtered = [t for t in filtered if parse_date_yyyy_mm_dd(t.get("due_date")) == due_dt]
        active.append(f"Due: {due_dt.isoformat()}")
        # ignore range if exact is used
        from_dt = None
        to_dt = None
    else:
        # Range (only apply if at least one bound is valid/present)
        if from_dt or to_dt:
            if from_dt and to_dt and from_dt > to_dt:
                errors.append("Due date range is invalid: From is after To.")
            else:
                def in_range(t):
                    d = parse_date_yyyy_mm_dd(t.get("due_date"))
                    if d is None:
                        return False
                    if from_dt and d < from_dt:
                        return False
                    if to_dt and d > to_dt:
                        return False
                    return True

                filtered = [t for t in filtered if in_range(t)]
                if from_dt and to_dt:
                    active.append(f"Due: {from_dt.isoformat()} → {to_dt.isoformat()}")
                elif from_dt:
                    active.append(f"Due: from {from_dt.isoformat()}")
                else:
                    active.append(f"Due: up to {to_dt.isoformat()}")

    return filtered, active, errors, status, q, due, due_from, due_to


@app.get("/home")
@login_required
def home_page():
    # Querystring params (persist after refresh)
    sort = (request.args.get("sort", "due_asc") or "due_asc").strip()
    status = request.args.get("status", "all")
    q = request.args.get("q", "")
    due = request.args.get("due", "")
    due_from = request.args.get("due_from", "")
    due_to = request.args.get("due_to", "")

    tasks = load_tasks(session.get("user_id"))

    # Ensure older tasks have expected fields
    for t in tasks:
        t.setdefault("memo", "")
        t.setdefault("due_date", "")
        t.setdefault("created_at", "")
        t.setdefault("status", "incomplete")

    # Stats should reflect ALL tasks (not filtered)
    total_all, complete_all, incomplete_all = compute_stats(tasks)

    # Apply filters, then sort the filtered set
    filtered, active_filters, errors, status, q, due, due_from, due_to = apply_filters(
        tasks,
        status=status,
        q=q,
        due=due,
        due_from=due_from,
        due_to=due_to,
    )

    for msg in errors:
        flash(msg, "error")

    tasks_sorted = sort_tasks(list(filtered), sort)

    return render_template(
        "home.html",
        tasks=tasks_sorted,
        total=total_all,
        complete=complete_all,
        incomplete=incomplete_all,
        shown_count=len(tasks_sorted),
        username=session.get("username"),
        sort=sort,
        # filters (to keep UI sticky)
        status_filter=status,
        q=q,
        due=due,
        due_from=due_from,
        due_to=due_to,
        active_filters=active_filters,
    )


# ------------------------------------------------------------
# Task actions (preserve current filters via hidden inputs)
# ------------------------------------------------------------

@app.post("/tasks/add")
@login_required
def add_task():
    title = request.form.get("title", "").strip()
    memo = request.form.get("memo", "").strip()
    due_date = request.form.get("due_date", "").strip()

    if not title:
        flash("Task title is required.", "error")
        return redirect(url_for("home_page"))

    # Validate due date (optional)
    if due_date and not parse_date_yyyy_mm_dd(due_date):
        flash("Please choose a valid due date.", "error")
        return redirect(url_for("home_page"))

    tasks = load_tasks(session.get("user_id"))

    tasks.append(
        {
            "id": next_id(tasks),
            "title": title,
            "memo": memo,
            "status": "incomplete",
            "due_date": due_date,  # YYYY-MM-DD (optional)
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_tasks(tasks, session.get("user_id"))

    qs = current_home_query_defaults()
    return redirect(url_for("home_page", **qs))


@app.post("/tasks/<int:task_id>/toggle")
@login_required
def toggle_task(task_id):
    tasks = load_tasks(session.get("user_id"))
    task = find_task(tasks, task_id)
    if not task:
        abort(404)

    task["status"] = "complete" if task.get("status") != "complete" else "incomplete"
    save_tasks(tasks, session.get("user_id"))

    qs = current_home_query_defaults()
    return redirect(url_for("home_page", **qs))


@app.post("/tasks/<int:task_id>/delete")
@login_required
def delete_task(task_id):
    tasks = load_tasks(session.get("user_id"))
    tasks = [t for t in tasks if t.get("id") != task_id]
    save_tasks(tasks, session.get("user_id"))

    qs = current_home_query_defaults()
    return redirect(url_for("home_page", **qs))


@app.get("/tasks/<int:task_id>")
@login_required
def view_task(task_id):
    tasks = load_tasks(session.get("user_id"))
    task = find_task(tasks, task_id)
    if not task:
        abort(404)
    return render_template("task.html", task=task)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)