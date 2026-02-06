from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, render_template

app = Flask(__name__)

# -----------------------------------------------------------------------------
# Data file (adjust path if your structure is different)
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TASKS_FILE = DATA_DIR / "tasks.json"


def load_tasks() -> list[dict[str, Any]]:
    """
    US1: Load tasks from data/tasks.json.

    Each record example:
      {
        "id": 1,
        "title": "IT 111 Reading",
        "status": "incomplete",
        "memo": "Read chapters on Lambda Functions"
      }
    """
    if not TASKS_FILE.exists():
        return []

    try:
        with TASKS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return []

        tasks: list[dict[str, Any]] = []
        for t in data:
            if not isinstance(t, dict):
                continue

            title = str(t.get("title", "")).strip()
            status = str(t.get("status", "incomplete")).strip().lower()
            memo = str(t.get("memo", "")).strip()

            if status not in ("complete", "incomplete"):
                status = "incomplete"

            tasks.append(
                {
                    "id": t.get("id"),
                    "title": title,
                    "status": status,
                    "memo": memo,
                }
            )

        return tasks

    except (OSError, json.JSONDecodeError):
        return []


@app.get("/")
def home_page():
    """
    US1 Home Page:
    - Shows list of tasks
    - Each task shows at least: title + status
    - If none exist, show a message
    """
    tasks = load_tasks()
    return render_template("home.html", tasks=tasks)


# -----------------------------------------------------------------------------
# TODO (TEAM) — placeholders only (not executed)
# - Add Task (US2)
# - Toggle Complete/Incomplete (US3)
# - Delete Task (US4)
# - Persistence improvements (Sprint 3+)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
