# CBC Online Grade Management System

CBC Online Grade Management System is a lightweight web application for managing student grades, courses, and academic records for CBC. It provides a simple interface for instructors and administrators to record, review, and export grades.

## Key features

- Manage students, courses, and assignments
- Record and update grades
- Generate simple grade reports and exports (CSV)
- Web-based interface (HTML + Python backend)

## Tech stack

- Backend: Python
- Frontend: HTML/CSS
- Data storage: SQLite by default

## Requirements

- Python 3.8+
- A virtual environment tool (venv or virtualenv)
- A database supported by the project (SQLite works by default)

## Quick start

1. Clone the repository

   git clone https://github.com/D-Githaka/cbc-management-system.git
   cd cbc-management-system

2. Create and activate a virtual environment

   python -m venv .venv
   source .venv/bin/activate   # macOS / Linux
   .\.venv\Scripts\activate  # Windows (PowerShell)

3. Install dependencies

   pip install -r requirements.txt

4. Run the application

   export FLASK_APP=app:create_app
   flask run

   Or, if you prefer:

   python app.py

## Usage

- Open the application in your browser at http://127.0.0.1:5000
- Log in with the appropriate admin or teacher account to manage students, schools, and marks
- Use the app to record student marks, review scores, and generate reports

## Database setup

The project is configured to use SQLite by default in `config.py`:

- Database file: `database.db`
- You may update the config for a production database if needed

## Admin and seed commands

The app includes Flask CLI commands for setup and testing:

- `flask seed-demo` — populate the database with demo data
- `flask create-admin <username> <password>` — create an admin user
- `flask create-super-admin <username> <password>` — create a super admin

## Testing

If test files are added later, run them with:

   pytest

or:

   python -m unittest discover

## Deployment

For production deployment, configure a secure environment, set proper secrets, and run the app behind a WSGI server such as Gunicorn with HTTPS enabled.

## Contributing

Contributions are welcome. Please open an issue to discuss major changes before submitting a pull request. When submitting PRs, include a clear description of the change and any migration or configuration steps required.

## License

Specify the project license here (for example: MIT, Apache-2.0). Add a `LICENSE` file to the repository.

## Contact

Maintainer: D-Githaka
