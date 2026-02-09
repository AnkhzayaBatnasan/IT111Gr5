from flask import Flask, render_template, request, redirect, url_for, abort
import json
from pathlib import Path

app = Flask(__name__)

DATA_PATH = Path("data/tasks.json")


def load_tasks():
    if not DATA_PATH.exists():
        return []
    try:
        with DATA_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_tasks(tasks):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DATA_PATH.open("w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)


def next_id(tasks):
    return max((t.get("id", 0) for t in tasks), default=0) + 1


def compute_stats(tasks):
    total = len(tasks)
    complete = sum(1 for t in tasks if t.get("status") == "complete")
    incomplete = total - complete
    return total, complete, incomplete


def find_task(tasks, task_id):
    return next((t for t in tasks if t.get("id") == task_id), None)


@app.get("/")
def home_page():
    tasks = load_tasks()
    total, complete, incomplete = compute_stats(tasks)
    return render_template(
        "home.html",
        tasks=tasks,
        total=total,
        complete=complete,
        incomplete=incomplete,
    )


@app.post("/tasks/add")
def add_task():
    title = request.form.get("title", "").strip()
    memo = request.form.get("memo", "").strip()

    if not title:
        return redirect(url_for("home_page"))

    tasks = load_tasks()
    tasks.append({
        "id": next_id(tasks),
        "title": title,
        "memo": memo,
        "status": "incomplete"
    })
    save_tasks(tasks)
    return redirect(url_for("home_page"))


@app.post("/tasks/<int:task_id>/toggle")
def toggle_task(task_id):
    tasks = load_tasks()
    task = find_task(tasks, task_id)
    if not task:
        abort(404)

    task["status"] = "complete" if task["status"] != "complete" else "incomplete"
    save_tasks(tasks)
    return redirect(url_for("home_page"))


@app.post("/tasks/<int:task_id>/delete")
def delete_task(task_id):
    tasks = load_tasks()
    tasks = [t for t in tasks if t.get("id") != task_id]
    save_tasks(tasks)
    return redirect(url_for("home_page"))


@app.get("/tasks/<int:task_id>")
def view_task(task_id):
    tasks = load_tasks()
    task = find_task(tasks, task_id)
    if not task:
        abort(404)
    return render_template("task.html", task=task)


if __name__ == "__main__":
    app.run(debug=True)
