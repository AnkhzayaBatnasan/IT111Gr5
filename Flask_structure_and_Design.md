**Flask structure**
This app uses a single Flask application file with route handlers for public pages, authentication, the task dashboard, task actions, and comments. It follows the usual Flask pattern of **routes + templates + static assets**, even though blueprints are not implemented yet. Templates like `landing.html`, `home.html`, `about.html`, `login.html`, and `register.html` are rendered from the route functions, while static styling and images would live in the static folder. 

**Database design**
This project does not use a relational database yet. Instead, it uses **JSON files as lightweight persistence**: `users.json` stores account records, `comments.json` stores feedback, and each user gets a separate task file in `data/user_tasks/`, which acts like per-user storage. That means there is no ORM such as SQLAlchemy here; the “data model” is represented by Python dictionaries written to JSON files. 

**Relationships / data model**
A user has an `id`, `username`, `email`, and hashed password. Tasks are separated by user through file organization rather than a SQL foreign key, and comments optionally store a `user_id` so the app can tell who created them. In a future database version, this would naturally become a **one-to-many relationship** from `User -> Tasks` and `User -> Comments`. 

**External libraries used**
The main external framework is **Flask** for routing, request handling, sessions, redirects, and template rendering. The app also uses **Werkzeug security helpers** to hash passwords with `generate_password_hash()` and verify them with `check_password_hash()`, which is an important security improvement over storing plain text passwords. 

**Authentication and authorization**
Authentication is implemented with registration, login, logout, password hashing, and Flask sessions. Authorization is handled mainly through the `login_required` decorator, which redirects unauthenticated users away from protected routes such as `/home` and task actions. There is also an ownership check in comment deletion so only the comment owner, or a special `admin` user, can delete a comment. 

**Notable algorithms and logic**
The most notable logic is the **filtering and sorting system**. `apply_filters()` supports filtering by completion status, keyword search, exact due date, and due-date range, while `sort_tasks()` handles ordering by due date, status, newest, and oldest. Another useful design detail is `current_home_query_defaults()`, which preserves the user’s active filters and sort settings across POST actions like add, toggle, and delete, so the dashboard stays consistent after an action. 

**One honest technical note**
This code is well organized for a class project, but it would be stronger in production if it were split into **blueprints**, used a real database such as SQLite/PostgreSQL with SQLAlchemy, moved the secret key to environment variables, and added stronger authorization checks around all task ownership operations. 


