# CBC Online Grade Management System

CBC Online Grade Management System is a lightweight web application for managing student grades, courses, and academic records for CBC. It provides a simple interface for instructors and administrators to record, review, and export grades.

Key features

- Manage students, courses, and assignments
- Record and update grades
- Generate simple grade reports and exports (CSV)
- Web-based interface (HTML + Python backend)

Tech stack

- Backend: Python (framework used in the repo)
- Frontend: HTML/CSS
- Data storage: (replace with actual DB used in the project, e.g., SQLite, PostgreSQL)

Requirements

- Python 3.8+
- A virtual environment tool (venv or virtualenv)
- A database supported by the project (SQLite included by default in many small projects)

Quick start

1. Clone the repository

   git clone https://github.com/D-Githaka/cbc-management-system.git
   cd cbc-management-system

2. Create and activate a virtual environment

   python -m venv .venv
   source .venv/bin/activate   # macOS / Linux
   .\.venv\Scripts\activate  # Windows (PowerShell)

3. Install dependencies

   pip install -r requirements.txt

4. Run database migrations (if the project uses a framework with migrations)

   # Django (if applicable)
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver

   # Flask (if applicable)
   # export FLASK_APP=app.py
   # flask run

   If the repository uses a different framework or custom setup, refer to the project files for exact commands and additional configuration steps (for example DATABASE_URL, environment variables, or secrets).

Usage

- Open the application in your browser at http://127.0.0.1:8000 (Django default) or http://127.0.0.1:5000 (Flask default), depending on the project.
- Log in with an admin account to create courses, students, and assignments, then begin recording grades.

Testing

- If tests are included in the repository, run them with:

  pytest
  # or
  python -m unittest discover

Deployment

- For production deployment, configure a production-ready database (PostgreSQL recommended), set proper environment variables, and use a WSGI server such as Gunicorn behind a reverse proxy (NGINX).

Contributing

Contributions are welcome. Please open an issue to discuss major changes before submitting a pull request. When submitting PRs, include a clear description of the change, motivation, and any migration or configuration steps required.

License

Specify the project license here (e.g., MIT, Apache-2.0). Add a LICENSE file to the repository.

Contact

Maintainer: D-Githaka

Notes

This README is intentionally framework-agnostic because the repository may use Django, Flask, or another Python web framework. If you want, I can update this README with exact setup and run instructions after inspecting the repository files (for example, identifying whether the project uses Django or Flask, where the entry point is, and what database is configured).