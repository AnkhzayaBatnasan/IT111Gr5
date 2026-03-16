# ============================================================
# TASK TRACKER WEB APP
# Documented for presentation / technical architecture review
# ============================================================

# -----------------------------
# Flask / standard library imports
# -----------------------------
from flask import Flask, render_template, request, redirect, url_for, abort, session, flash
import json                              # Used for lightweight file-based data storage
import re                                # Used for simple email validation
import datetime                          # Used for created timestamps and due date parsing
from pathlib import Path                 # Used for platform-safe file paths
from werkzeug.security import generate_password_hash, check_password_hash  # Password hashing helpers
from functools import wraps              # Used to build the login_required decorator

# -----------------------------
# Flask app setup
# -----------------------------
app = Flask(__name__)                    # Create the main Flask application object

# NOTE: In production, set this via an environment variable.
app.secret_key = "dev-secret-change-me"  # Enables secure sessions, flash messages, and login state

# -----------------------------
# File-based storage paths
# -----------------------------
DATA_DIR = Path("data")                  # Main folder that stores all persistent JSON data
DATA_PATH = DATA_DIR / "tasks.json"      # Legacy single-user task file kept for backward compatibility
USERS_PATH = DATA_DIR / "users.json"     # Stores registered user accounts
USER_TASKS_DIR = DATA_DIR / "user_tasks" # Stores one task file per user for task separation
COMMENTS_PATH = DATA_DIR / "comments.json"  # Stores landing-page feedback comments

# ------------------------------------------------------------
# About page content (Keep the text intact)
# These constants are rendered into the About template.
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

# ------------------------------------------------------------
# Data initialization / file management
# ------------------------------------------------------------

def ensure_data_files():
    """Create required folders and starter JSON files if they do not exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)            # Ensure /data exists
    USER_TASKS_DIR.mkdir(parents=True, exist_ok=True)      # Ensure /data/user_tasks exists

    if not USERS_PATH.exists():                            # Create users.json on first run
        with USERS_PATH.open("w", encoding="utf-8") as f:
            json.dump([], f, indent=2)                     # Start with an empty list of users


def load_users():
    """Load all registered users from users.json."""
    ensure_data_files()                                    # Make sure storage exists before reading

    try:
        with USERS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)                            # Return list of user dictionaries
    except json.JSONDecodeError:
        return []                                          # If JSON is corrupted/empty, fail safely


def save_users(users):
    """Save the full user list back to users.json."""
    ensure_data_files()                                    # Make sure storage exists before writing

    with USERS_PATH.open("w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)                      # Pretty-print JSON for readability


# ------------------------------------------------------------
# Comments (Feedback)
# Handles comment persistence for the landing page.
# ------------------------------------------------------------

def load_comments():
    """Load all user comments from comments.json."""
    ensure_data_files()

    if not COMMENTS_PATH.exists():                         # Create comments file if missing
        with COMMENTS_PATH.open("w", encoding="utf-8") as f:
            json.dump([], f)
        return []

    try:
        with COMMENTS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []                                          # Fail safely if JSON cannot be read


def save_comments(comments):
    """Save the current comments list to comments.json."""
    ensure_data_files()

    with COMMENTS_PATH.open("w", encoding="utf-8") as f:
        json.dump(comments, f, indent=2)


# ------------------------------------------------------------
# User helpers
# These are utility functions used during registration/login.
# ------------------------------------------------------------

def find_user(users, *, username=None, email=None, user_id=None):
    """Find a user by username, email, or ID."""
    for u in users:
        if user_id is not None and u.get("id") == user_id:
            return u                                       # Match by numeric ID
        if username and u.get("username", "").lower() == username.lower():
            return u                                       # Match username case-insensitively
        if email and u.get("email", "").lower() == email.lower():
            return u                                       # Match email case-insensitively
    return None                                            # No match found


def next_user_id(users):
    """Generate the next available user ID."""
    if not users:
        return 1                                           # First user starts at ID 1
    return max([u.get("id", 0) for u in users]) + 1        # Increment highest existing ID


# ------------------------------------------------------------
# Task storage helpers
# One JSON file per user keeps each user's task list separate.
# ------------------------------------------------------------

def task_file_for_user(user_id: int) -> Path:
    """Return the JSON file path for a specific user's tasks."""
    return USER_TASKS_DIR / f"user_{user_id}_tasks.json"


def load_tasks(user_id=None):
    """
    Load tasks for one user.
    If user_id is None, fall back to legacy tasks.json.
    """
    ensure_data_files()

    if user_id is None:
        path = DATA_PATH                                   # Legacy single-file mode
    else:
        path = task_file_for_user(int(user_id))            # Multi-user mode

    if not path.exists():
        return []                                          # Missing file means no tasks yet

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []                                          # Fail safely if file is unreadable


def save_tasks(tasks, user_id=None):
    """
    Save tasks for one user.
    If user_id is None, save to legacy tasks.json.
    """
    ensure_data_files()

    if user_id is None:
        path = DATA_PATH
    else:
        path = task_file_for_user(int(user_id))

    with path.open("w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)


# ------------------------------------------------------------
# Session / authentication helpers
# ------------------------------------------------------------

def current_user():
    """Return the currently logged-in user based on session data."""
    user_id = session.get("user_id")                       # Read user_id from signed session cookie
    if not user_id:
        return None                                        # Not logged in

    users = load_users()
    return find_user(users, user_id=user_id)               # Return full user record


def login_required(view_func):
    """
    Route decorator that blocks access unless a user is logged in.
    This is the app's main authorization mechanism.
    """
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):                     # If no authenticated session exists
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)                  # Otherwise allow access
    return wrapper


def is_valid_email(email: str) -> bool:
    """
    Simple email format validation.
    Good enough for a class project, but not full RFC validation.
    """
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


# ------------------------------------------------------------
# General task utilities
# ------------------------------------------------------------

def next_id(tasks):
    """Return the next task ID for a user's task list."""
    return max((t.get("id", 0) for t in tasks), default=0) + 1


def compute_stats(tasks):
    """Compute total, complete, and incomplete task counts."""
    total = len(tasks)
    complete = sum(1 for t in tasks if t.get("status") == "complete")
    incomplete = total - complete
    return total, complete, incomplete


def parse_date_yyyy_mm_dd(value: str):
    """Safely parse a date string in YYYY-MM-DD format."""
    if not value:
        return None

    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None                                        # Invalid dates return None safely


# ------------------------------------------------------------
# Task sorting logic
# This is one of the notable algorithms in the app.
# ------------------------------------------------------------

def sort_tasks(tasks, sort_key: str):
    """Return a new list sorted by the selected option."""
    sort_key = (sort_key or "").strip()

    if sort_key == "due_asc":
        # Sort by earliest due date first
        # Tasks with no due date are pushed to the bottom
        return sorted(
            tasks,
            key=lambda t: (
                parse_date_yyyy_mm_dd(t.get("due_date")) is None,
                parse_date_yyyy_mm_dd(t.get("due_date")) or datetime.date.max,
                (t.get("created_at") or ""),
            ),
        )

    if sort_key == "due_desc":
        # Sort by latest due date first
        # Tasks with no due date still go last
        return sorted(
            tasks,
            key=lambda t: (
                parse_date_yyyy_mm_dd(t.get("due_date")) is None,
                -(parse_date_yyyy_mm_dd(t.get("due_date")) or datetime.date.min).toordinal(),
                (t.get("created_at") or ""),
            ),
        )

    if sort_key == "status":
        # Incomplete tasks first, completed tasks second
        return sorted(
            tasks,
            key=lambda t: (t.get("status") == "complete", (t.get("created_at") or "")),
            reverse=False,
        )

    if sort_key == "newest":
        return sorted(tasks, key=lambda t: (t.get("created_at") or ""), reverse=True)

    if sort_key == "oldest":
        return sorted(tasks, key=lambda t: (t.get("created_at") or ""), reverse=False)

    # Default behavior: preserve original order
    return tasks


def find_task(tasks, task_id):
    """Find a single task in a list by ID."""
    return next((t for t in tasks if t.get("id") == task_id), None)


def current_home_query_defaults():
    """
    Build a querystring dictionary for /home.
    This allows POST routes to preserve the user's active filters/sort options.
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


# ============================================================
# ROUTES: Public pages
# ============================================================

@app.get("/")
def landing_page():
    """Render the public landing page and show newest comments first."""
    comments = load_comments()
    comments = sorted(
        comments,
        key=lambda c: c.get("created_at", ""),
        reverse=True                                      # Newest comments appear first
    )

    return render_template(
        "landing.html",
        comments=comments
    )


@app.get("/about")
def about_page():
    """Render the About page using constant content defined above."""
    return render_template(
        "about.html",
        about_title="About Us",
        about_paragraphs=ABOUT_PARAGRAPHS,
        team_members=ABOUT_TEAM_MEMBERS,
    )


@app.get("/privacy")
def privacy_page():
    """Render the privacy notice page."""
    return render_template("privacy.html")


# ============================================================
# ROUTES: Authentication (Register / Login / Logout)
# ============================================================

@app.get("/register")
def register():
    """Show the registration page unless the user is already logged in."""
    if session.get("user_id"):
        return redirect(url_for("home_page"))             # Logged-in users skip register page
    return render_template("register.html")


@app.post("/register")
def register_post():
    """Process registration form submission."""
    if session.get("user_id"):
        return redirect(url_for("home_page"))

    username = request.form.get("username", "").strip()   # Read submitted username
    email = request.form.get("email", "").strip()         # Read submitted email
    password = request.form.get("password", "")           # Read submitted password

    # Basic form validation
    if not username or not email or not password:
        flash("Please fill out username, email, and password.", "error")
        return redirect(url_for("register"))

    if not is_valid_email(email):
        flash("Please enter a valid email address (example: name@example.com).", "error")
        return redirect(url_for("register"))

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
        "id": next_user_id(users),                        # Assign unique user ID
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(          # Store hashed password, not plaintext
            password,
            method="pbkdf2:sha256",
            salt_length=16
        ),
    }

    users.append(user)
    save_users(users)

    flash("Account created! Please log in.", "success")
    return redirect(url_for("login"))


@app.get("/login")
def login():
    """Show the login page unless the user is already authenticated."""
    if session.get("user_id"):
        return redirect(url_for("home_page"))
    return render_template("login.html", next=request.args.get("next", ""))


@app.post("/login")
def login_post():
    """Process login form submission."""
    if session.get("user_id"):
        return redirect(url_for("home_page"))

    username_or_email = request.form.get("username_or_email", "").strip()
    password = request.form.get("password", "")

    users = load_users()

    # Allow login by either username or email
    user = find_user(users, username=username_or_email) or find_user(users, email=username_or_email)

    # Verify password against stored hash
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        flash("Invalid username/email or password.", "error")
        return redirect(url_for("login", next=request.form.get("next", "")))

    # Save authenticated user info in session
    session["user_id"] = user["id"]
    session["username"] = user["username"]

    flash(f"Welcome back, {user['username']}!", "success")

    next_url = request.form.get("next") or url_for("home_page")

    # Security check: only allow relative redirects
    if next_url.startswith("http://") or next_url.startswith("https://"):
        next_url = url_for("home_page")

    return redirect(next_url)


@app.get("/logout")
def logout():
    """Clear the session and log the user out."""
    session.clear()                                       # Remove all session data
    flash("You have been logged out.", "success")
    return redirect(url_for("landing_page"))


# ============================================================
# Home page + task filtering logic
# ============================================================

def apply_filters(tasks, *, status="all", q="", due="", due_from="", due_to=""):
    """
    Apply task filters and return:
      - filtered task list
      - active filter labels
      - validation errors
      - normalized filter values

    Filters supported:
      - status: all | complete | incomplete
      - q: text search in title + memo
      - due: exact date match
      - due_from / due_to: inclusive date range
    """
    active = []                                           # Tracks active filters for UI display
    errors = []                                           # Tracks validation errors for flashing

    status = (status or "all").strip().lower()
    q = (q or "").strip()
    due = (due or "").strip()
    due_from = (due_from or "").strip()
    due_to = (due_to or "").strip()

    filtered = list(tasks)                                # Start with all tasks

    # -----------------------------
    # Status filter
    # -----------------------------
    if status in ("complete", "incomplete"):
        filtered = [
            t for t in filtered
            if (t.get("status") == "complete") == (status == "complete")
        ]
        active.append(f"Status: {status.capitalize()}")
    else:
        status = "all"

    # -----------------------------
    # Keyword search filter
    # -----------------------------
    if q:
        needle = q.lower()

        def matches(t):
            title = (t.get("title") or "").lower()
            memo = (t.get("memo") or "").lower()
            return (needle in title) or (needle in memo)

        filtered = [t for t in filtered if matches(t)]
        active.append(f"Search: “{q}”")

    # -----------------------------
    # Date filters
    # -----------------------------
    due_dt = parse_date_yyyy_mm_dd(due) if due else None
    from_dt = parse_date_yyyy_mm_dd(due_from) if due_from else None
    to_dt = parse_date_yyyy_mm_dd(due_to) if due_to else None

    if due and not due_dt:
        errors.append("Due date filter must be a valid date.")
    if due_from and not from_dt:
        errors.append("From date must be a valid date.")
    if due_to and not to_dt:
        errors.append("To date must be a valid date.")

    # Exact due date takes priority over range filtering
    if due_dt:
        filtered = [t for t in filtered if parse_date_yyyy_mm_dd(t.get("due_date")) == due_dt]
        active.append(f"Due: {due_dt.isoformat()}")
        from_dt = None
        to_dt = None
    else:
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
    """
    Main authenticated task dashboard.
    Loads the current user's tasks, applies filters, sorts results,
    computes stats, and renders home.html.
    """
    # Read querystring parameters so filters stay active after refresh
    sort = (request.args.get("sort", "due_asc") or "due_asc").strip()
    status = request.args.get("status", "all")
    q = request.args.get("q", "")
    due = request.args.get("due", "")
    due_from = request.args.get("due_from", "")
    due_to = request.args.get("due_to", "")

    tasks = load_tasks(session.get("user_id"))            # Load only the current user's tasks

    # Backfill older tasks with default fields for compatibility
    for t in tasks:
        t.setdefault("memo", "")
        t.setdefault("due_date", "")
        t.setdefault("created_at", "")
        t.setdefault("status", "incomplete")

    # Compute stats for ALL user tasks, not just visible filtered tasks
    total_all, complete_all, incomplete_all = compute_stats(tasks)

    # Apply filters first
    filtered, active_filters, errors, status, q, due, due_from, due_to = apply_filters(
        tasks,
        status=status,
        q=q,
        due=due,
        due_from=due_from,
        due_to=due_to,
    )

    # Flash any filter validation errors
    for msg in errors:
        flash(msg, "error")

    # Sort the already-filtered results
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
        status_filter=status,
        q=q,
        due=due,
        due_from=due_from,
        due_to=due_to,
        active_filters=active_filters,
    )


# ============================================================
# Task actions
# These routes add, toggle, delete, and view tasks.
# ============================================================

@app.post("/tasks/add")
@login_required
def add_task():
    """Add a new task for the currently logged-in user."""
    title = request.form.get("title", "").strip()
    memo = request.form.get("memo", "").strip()
    due_date = request.form.get("due_date", "").strip()

    if not title:
        flash("Task title is required.", "error")
        return redirect(url_for("home_page"))

    if due_date and not parse_date_yyyy_mm_dd(due_date):
        flash("Please choose a valid due date.", "error")
        return redirect(url_for("home_page"))

    tasks = load_tasks(session.get("user_id"))

    tasks.append(
        {
            "id": next_id(tasks),                         # Unique task ID within this user's file
            "title": title,
            "memo": memo,
            "status": "incomplete",                      # New tasks start incomplete
            "due_date": due_date,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
    )

    save_tasks(tasks, session.get("user_id"))

    qs = current_home_query_defaults()                   # Preserve active sort/filter options
    return redirect(url_for("home_page", **qs))


@app.post("/tasks/<int:task_id>/toggle")
@login_required
def toggle_task(task_id):
    """Toggle one task between complete and incomplete."""
    tasks = load_tasks(session.get("user_id"))
    task = find_task(tasks, task_id)

    if not task:
        abort(404)                                       # Task not found for this user

    task["status"] = "complete" if task.get("status") != "complete" else "incomplete"
    save_tasks(tasks, session.get("user_id"))

    qs = current_home_query_defaults()
    return redirect(url_for("home_page", **qs))


@app.post("/tasks/<int:task_id>/delete")
@login_required
def delete_task(task_id):
    """Delete a task from the current user's task list."""
    tasks = load_tasks(session.get("user_id"))
    tasks = [t for t in tasks if t.get("id") != task_id] # Remove matching task by ID
    save_tasks(tasks, session.get("user_id"))

    qs = current_home_query_defaults()
    return redirect(url_for("home_page", **qs))


@app.get("/tasks/<int:task_id>")
@login_required
def view_task(task_id):
    """View a single task detail page."""
    tasks = load_tasks(session.get("user_id"))
    task = find_task(tasks, task_id)

    if not task:
        abort(404)

    return render_template("task.html", task=task)


# ============================================================
# Comment routes
# Handles user feedback on the landing page.
# ============================================================

@app.post("/comment")
def submit_comment():
    """Add a new feedback comment from the landing page."""
    name = request.form.get("name", "").strip()
    text = request.form.get("comment", "").strip()

    if not text:
        flash("Comment cannot be empty.", "error")
        return redirect(url_for("landing_page"))

    if len(text) > 500:
        flash("Comment too long (max 500).", "error")
        return redirect(url_for("landing_page"))

    comments = load_comments()

    comments.append({
        "id": len(comments) + 1,                         # Simple sequential comment ID
        "name": name or "Anonymous",                    # Default display name if blank
        "comment": text,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "user_id": session.get("user_id")               # Optional ownership tracking
    })

    save_comments(comments)

    flash("Thank you for feedback!", "success")
    return redirect(url_for("landing_page"))


@app.post("/comment/<int:comment_id>/delete")
def delete_comment(comment_id):
    """Delete a comment if the current user is the owner or an admin."""
    if not session.get("user_id"):
        abort(403)                                       # Must be logged in to delete

    comments = load_comments()
    comment = next((c for c in comments if c.get("id") == comment_id), None)

    if not comment:
        abort(404)

    current_id = session.get("user_id")
    current_name = session.get("username")

    # Authorization rule:
    # - comment owner may delete
    # - special username 'admin' may delete any comment
    if comment.get("user_id") != current_id and current_name != "admin":
        abort(403)

    comments = [c for c in comments if c.get("id") != comment_id]
    save_comments(comments)

    flash("Comment deleted.", "success")
    return redirect(url_for("landing_page"))


# ============================================================
# App entry point
# ============================================================

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)     # Local development server
