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
        return sorted(tasks, key=lambda t: (t.get("status") == "complete", (t.get("created_at") or "")), reverse=False)

    if sort_key == "newest":
        return sorted(tasks, key=lambda t: (t.get("created_at") or ""), reverse=True)

    if sort_key == "oldest":
        return sorted(tasks, key=lambda t: (t.get("created_at") or ""), reverse=False)

    # default: keep existing order
    return tasks


def find_task(tasks, task_id):
    return next((t for t in tasks if t.get("id") == task_id), None)


# ------------------------------------------------------------
# NEW: Querystring persistence helper for dashboard actions
# ------------------------------------------------------------

def dashboard_params_from_request(req):
    """
    Pull dashboard query values from either:
      - request.args (GET /home)
      - request.form (POST actions that include hidden inputs)
    """
    sort = (req.get("sort") or "due_asc").strip()
    status = (req.get("status") or "all").strip().lower()
    q = (req.get("q") or "").strip()
    due = (req.get("due") or "").strip()           # exact due date
    due_from = (req.get("due_from") or "").strip()
    due_to = (req.get("due_to") or "").strip()
    return {
        "sort": sort or "due_asc",
        "status": status or "all",
        "q": q,
        "due": due,
        "due_from": due_from,
        "due_to": due_to,
    }


def apply_filters(tasks, status="all", q="", due="", due_from="", due_to=""):
    """
    User Story 3.1: Filter by status (all/complete/incomplete)
    User Story 3.2: Search (case-insensitive contains) in title + memo
    User Story 3.3: Due date exact OR range (inclusive). Invalid dates are handled safely.
    """
    filtered = list(tasks)

    # --- 3.1 Completion status filter ---
    status = (status or "all").lower()
    if status in ("complete", "incomplete"):
        filtered = [t for t in filtered if (t.get("status") or "incomplete") == status]

    # --- 3.2 Search filter (title + memo, case-insensitive) ---
    q = (q or "").strip()
    if q:
        q_lower = q.lower()
        def matches(task):
            title = (task.get("title") or "").lower()
            memo = (task.get("memo") or "").lower()
            return (q_lower in title) or (q_lower in memo)
        filtered = [t for t in filtered if matches(t)]

    # --- 3.3 Due date filter (exact OR range) ---
    # Exact date takes precedence if provided
    exact = parse_date_yyyy_mm_dd(due)
    frm = parse_date_yyyy_mm_dd(due_from)
    to = parse_date_yyyy_mm_dd(due_to)

    if due and not exact:
        # invalid exact date: ignore it, but don't crash
        flash("Invalid exact due date filter. Please choose a valid date.", "error")

    if due_from and not frm:
        flash("Invalid 'From' due date. Please choose a valid date.", "error")

    if due_to and not to:
        flash("Invalid 'To' due date. Please choose a valid date.", "error")

    # Normalize range if both valid but reversed
    if frm and to and frm > to:
        flash("Due date range was reversed. Swapping From/To.", "error")
        frm, to = to, frm

    if exact:
        filtered = [
            t for t in filtered
            if parse_date_yyyy_mm_dd(t.get("due_date") or "") == exact
        ]
    elif frm or to:
        def in_range(task):
            d = parse_date_yyyy_mm_dd(task.get("due_date") or "")
            if not d:
                return False
            if frm and d < frm:
                return False
            if to and d > to:
                return False
            return True

        filtered = [t for t in filtered if in_range(t)]

    return filtered


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


@app.get("/home")
@login_required
def home_page():
    # Dashboard query controls
    params = dashboard_params_from_request(request.args)
    sort = params["sort"]
    status = params["status"]
    q = params["q"]
    due = params["due"]
    due_from = params["due_from"]
    due_to = params["due_to"]

    tasks = load_tasks(session.get("user_id"))

    # Ensure older tasks have expected fields
    for t in tasks:
        t.setdefault("due_date", "")
        t.setdefault("created_at", "")
        t.setdefault("memo", "")
        t.setdefault("status", "incomplete")

    has_any_tasks = len(tasks) > 0

    # Apply filters/search/due date
    filtered = apply_filters(tasks, status=status, q=q, due=due, due_from=due_from, due_to=due_to)

    # Sort after filtering
    tasks_sorted = sort_tasks(list(filtered), sort)

    # Stats should reflect what is currently shown (filtered set)
    total, complete, incomplete = compute_stats(tasks_sorted)

    # Used for displaying correct empty-state message
    filters_active = (status in ("complete", "incomplete")) or bool(q) or bool(due) or bool(due_from) or bool(due_to)

    return render_template(
        "home.html",
        tasks=tasks_sorted,
        total=total,
        complete=complete,
        incomplete=incomplete,
        username=session.get("username"),
        sort=sort,
        status_filter=status,
        q=q,
        due=due,
        due_from=due_from,
        due_to=due_to,
        has_any_tasks=has_any_tasks,
        filters_active=filters_active,
    )


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

    # Preserve dashboard filters/search/sort after Add
    params = dashboard_params_from_request(request.form)
    return redirect(url_for("home_page", **params))


@app.post("/tasks/<int:task_id>/toggle")
@login_required
def toggle_task(task_id):
    tasks = load_tasks(session.get("user_id"))
    task = find_task(tasks, task_id)
    if not task:
        abort(404)

    task["status"] = "complete" if task.get("status") != "complete" else "incomplete"
    save_tasks(tasks, session.get("user_id"))

    params = dashboard_params_from_request(request.form)
    return redirect(url_for("home_page", **params))


@app.post("/tasks/<int:task_id>/delete")
@login_required
def delete_task(task_id):
    tasks = load_tasks(session.get("user_id"))
    tasks = [t for t in tasks if t.get("id") != task_id]
    save_tasks(tasks, session.get("user_id"))

    params = dashboard_params_from_request(request.form)
    return redirect(url_for("home_page", **params))


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