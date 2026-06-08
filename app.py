import os
import click
import random
import string
import logging
import traceback
import functools
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from flask_login import login_required, current_user, login_user, logout_user
from flask import (Flask, abort, render_template, request, redirect,
                   flash, url_for, send_file, g, has_request_context)
from werkzeug.security import check_password_hash, generate_password_hash as _generate_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import event

from models import School, Student, Subject, Mark, User
from seed import seed_subjects
from extensions import db, migrate, cache, login_manager, mail
from config import Config 

generate_password_hash = functools.partial(_generate_password_hash, method="pbkdf2:sha256")

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Create logs directory
    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # ---- Audit Logger (database changes) ----
    audit_logger = logging.getLogger('audit')
    audit_logger.setLevel(logging.INFO)
    audit_handler = RotatingFileHandler(
        os.path.join(logs_dir, 'audit.log'),
        maxBytes=1024 * 1024, backupCount=10
    )
    audit_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    audit_logger.addHandler(audit_handler)

    # ---- Login Logger ----
    login_logger = logging.getLogger('login')
    login_logger.setLevel(logging.INFO)
    login_handler = RotatingFileHandler(
        os.path.join(logs_dir, 'login.log'),
        maxBytes=1024 * 1024, backupCount=5
    )
    login_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    login_logger.addHandler(login_handler)

    # ---- Error Logger ----
    error_logger = logging.getLogger('error')
    error_logger.setLevel(logging.ERROR)
    error_handler = RotatingFileHandler(
        os.path.join(logs_dir, 'error.log'),
        maxBytes=1024 * 1024, backupCount=5
    )
    error_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    error_logger.addHandler(error_handler)

    cache_dir = os.path.join(os.path.dirname(__file__), 'cache')
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    db.init_app(app)
    migrate.init_app(app, db)
    cache.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"

    with app.app_context():
        db.create_all()
        seed_subjects()

    # ---------- Blueprints ----------
    from blueprints.reports import reports_bp
    from blueprints.api import api_bp
    from blueprints.marks import marks_bp
    from blueprints.main import main_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(marks_bp)

    # ---------- CLI Commands ----------
    @app.cli.command('seed-demo')
    def seed_demo_command():
        """Populate database with demo data (20 schools, 50 students/grade)."""
        from seed_demo import seed_demo_data 
        seed_demo_data()

    @app.cli.command('create-admin')
    @click.argument('username')
    @click.argument('password')
    def create_admin_cli(username, password):
        """Create an admin user."""
        admin = User(
            username=username,
            password=generate_password_hash(password),
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()
        print(f"Admin '{username}' created.")

    @app.cli.command('create-super-admin')
    @click.argument('username')
    @click.argument('password')
    def create_super_admin(username, password):
        """Create a super admin user that cannot be deleted."""
        existing = User.query.filter_by(username=username).first()
        if existing:
            existing.is_superadmin = True
            db.session.commit()
            print(f"User '{username}' is now super admin.")
        else:
            admin = User(
                username=username,
                password=generate_password_hash(password),
                role="admin",
                is_superadmin=True
            )
            db.session.add(admin)
            db.session.commit()
            print(f"Super admin '{username}' created.")

    # ---------- Request hooks & audit logging ----------
    @app.before_request
    def set_logged_user():
        if current_user.is_authenticated:
            g.user_id = current_user.id
            g.username = current_user.username
            g.user_role = current_user.role
        else:
            g.user_id = None
            g.username = 'anonymous'
            g.user_role = 'anonymous'

    def log_insert(mapper, connection, target):
        if has_request_context():
            user_info = f"user:{g.username} ({g.user_role})"
        else:
            user_info = "user:system (seed)"
        cols = [c.key for c in mapper.column_attrs]
        values = {c: getattr(target, c) for c in cols}
        audit_logger.info(f"{user_info} - INSERT {target.__class__.__name__} {values}")

    def log_update(mapper, connection, target):
        if has_request_context():
            user_info = f"user:{g.username} ({g.user_role})"
        else:
            user_info = "user:system (seed)"
        changes = []
        for attr in mapper.column_attrs:
            hist = attr.get_history(target, attr.key)
            if hist.has_changes():
                old = hist.deleted[0] if hist.deleted else None
                new = hist.added[0] if hist.added else None
                changes.append(f"{attr.key}: {old} -> {new}")
        if changes:
            audit_logger.info(f"{user_info} - UPDATE {target.__class__.__name__} id={target.id} changes: {', '.join(changes)}")

    def log_delete(mapper, connection, target):
        if has_request_context():
            user_info = f"user:{g.username} ({g.user_role})"
        else:
            user_info = "user:system (seed)"
        cols = [c.key for c in mapper.column_attrs]
        values = {c: getattr(target, c) for c in cols}
        audit_logger.info(f"{user_info} - DELETE {target.__class__.__name__} {values}")

    with app.app_context():
        for cls in [User, School, Student, Subject, Mark]:
            event.listen(cls, 'after_insert', log_insert)
            event.listen(cls, 'after_update', log_update)
            event.listen(cls, 'after_delete', log_delete)

    # ---------- Admin routes (remain in app.py) ----------
    @app.route('/admin/logs')
    @login_required
    def admin_logs():
        if current_user.role != 'admin':
            abort(403)
        logs = []
        for filename in os.listdir(logs_dir):
            if filename.endswith('.log'):
                filepath = os.path.join(logs_dir, filename)
                size = os.path.getsize(filepath)
                logs.append({'name': filename, 'size': size})
        return render_template('admin_logs.html', logs=logs)

    @app.route('/admin/logs/download/<filename>')
    @login_required
    def download_log(filename):
        if current_user.role != 'admin':
            abort(403)
        safe_filename = os.path.basename(filename)
        filepath = os.path.join(logs_dir, safe_filename)
        if not os.path.isfile(filepath):
            abort(404)
        return send_file(filepath, as_attachment=True, download_name=safe_filename, mimetype='text/plain')

    @app.route('/admin/users', methods=['GET', 'POST'])
    @login_required
    def manage_users():
        if current_user.role not in ['admin', 'principal']:
            abort(403)

        if current_user.role == 'admin':
            schools = School.query.all()
        else:
            schools = [School.query.get(current_user.school_id)]

        if request.method == 'GET':
            if current_user.role == 'admin':
                if getattr(current_user, 'is_superadmin', False):
                    users = User.query.filter(User.role != None).options(joinedload(User.school)).all()
                else:
                    users = User.query.filter(User.role != None, User.is_superadmin == False).options(joinedload(User.school)).all()
            else:
                users = User.query.filter_by(school_id=current_user.school_id, role='teacher').options(joinedload(User.school)).all()
            return render_template("admin_users.html", schools=schools, users=users)

        # POST – create user
        username = request.form['username']
        role = request.form['role']
        school_id = request.form.get('school_id')
        school_id = int(school_id) if school_id else None
        grade = request.form.get('grade')
        employee_id = request.form.get('employee_id', '').strip()
        if not employee_id:
            # Auto‑generate based on role
            if role == 'admin':
                # Find the highest existing admin ID
                last_admin = User.query.filter(User.role == 'admin', User.employee_id.like('ADM-%')).order_by(User.id.desc()).first()
                next_num = 1
                if last_admin:
                    try:
                        next_num = int(last_admin.employee_id.split('-')[1]) + 1
                    except:
                        next_num = 1
                employee_id = f"ADM-{next_num:03d}"
            else:
                school = School.query.get(school_id)
                if school:
                    # Find highest existing staff ID for this school
                    last_emp = User.query.filter(User.school_id == school_id, User.employee_id.like(f'{school.entry}-%')).order_by(User.id.desc()).first()
                    next_num = 1
                    if last_emp:
                        try:
                            next_num = int(last_emp.employee_id.split('-')[-1]) + 1
                        except:
                            next_num = 1
                    employee_id = f"{school.entry}-EMP-{next_num:03d}"
                else:
                    flash("School is required for non‑admin users.", "danger")
                    return redirect(url_for('manage_users'))
        else:
            # Check global uniqueness
            existing = User.query.filter_by(employee_id=employee_id).first()
            if existing:
                flash('A user with that Staff ID already exists.', 'danger')
                return redirect(url_for('manage_users'))
        if not employee_id and role in ['teacher', 'principal']:
            # Generate based on school
            school = School.query.get(school_id)
            if school:
                # find max existing employee_id for that school
                existing = User.query.filter(
                    User.school_id == school_id,
                    User.employee_id.isnot(None)
                ).order_by(User.id.desc()).first()
                last_num = 1
                if existing and existing.employee_id:
                    # e.g. SCH-001-EMP-003 → extract 3
                    try:
                        last_num = int(existing.employee_id.split('-')[-1]) + 1
                    except:
                        last_num = 1
                employee_id = f"{school.entry}-EMP-{last_num:03d}"
        elif employee_id and role in ['teacher', 'principal']:
            # check uniqueness per school
            existing = User.query.filter_by(school_id=school_id, employee_id=employee_id).first()
            if existing:
                flash('An employee with that ID already exists in this school.', 'danger')
                return redirect(url_for('manage_users'))
        # … then create the user with employee_id
        if current_user.role == 'principal':
            if role != 'teacher':
                flash("Principal can only create teacher accounts.", "danger")
                return redirect(url_for('manage_users'))
            if school_id != current_user.school_id:
                flash("You can only create teachers for your own school.", "danger")
                return redirect(url_for('manage_users'))

        if role != "admin" and not school_id:
            flash("Please select a school.", "danger")
            return redirect(url_for('manage_users'))
        if role == "teacher" and not grade:
            flash("Grade is required for teachers.", "danger")
            return redirect(url_for('manage_users'))

        def generate_password(length=8):
            return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

        password_plain = generate_password()
        user = User(
            username=username,
            password=generate_password_hash(password_plain),
            role=role,
            school_id=school_id if role != "admin" else None,
            grade=grade if role == "teacher" else None
        )
        db.session.add(user)
        db.session.commit()

        return render_template("user_created.html", username=username, password=password_plain)

    @app.route('/admin/users/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_user(id):
        if current_user.role not in ['admin', 'principal']:
            abort(403)

        target = db.session.get(User, id)
        if not target:
            flash('User not found.', 'danger')
            return redirect(url_for('manage_users'))

        if getattr(target, 'is_superadmin', False):
            flash('The super admin account cannot be deleted.', 'danger')
            return redirect(url_for('manage_users'))

        if target.id == current_user.id:
            flash('You cannot delete your own account.', 'danger')
            return redirect(url_for('manage_users'))

        if current_user.role == 'principal':
            if target.role != 'teacher' or target.school_id != current_user.school_id:
                flash('You can only delete teachers from your own school.', 'danger')
                return redirect(url_for('manage_users'))

        db.session.delete(target)
        db.session.commit()
        flash(f"User '{target.username}' deleted.", 'success')
        return redirect(url_for('manage_users'))

    # ---------- Auth routes ----------
    @login_manager.unauthorized_handler
    def unauthorized():
        return redirect('/login')

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form['username']
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, request.form['password']):
                remember = True if request.form.get('remember') else False
                login_user(user, remember=remember)
                login_logger.info(f"Login SUCCESS: user {user.username} (role {user.role}) from IP {request.remote_addr}")
                flash("Login successful", "success")
                next_page = request.args.get('next')
                return redirect(next_page or url_for('main.splash'))
            else:
                login_logger.warning(f"Login FAILURE: username '{username}' from IP {request.remote_addr}")
                flash("Invalid username or password", "danger")
                return redirect(url_for('login'))

        return render_template("login.html")

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect('/')

    # ---------- Error handlers ----------
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html',
                               error_title="Access Denied",
                               error_message="You don't have permission to access this page."), 403

    @app.errorhandler(Exception)
    def log_exception(e):
        error_logger.error(
            f"Unhandled exception: {e}\n"
            f"Request: {request.method} {request.path}\n"
            f"User: {g.username}\n"
            f"{traceback.format_exc()}"
        )
        return render_template('error.html',
                               error_title="Internal Server Error",
                               error_message="An unexpected error occurred. The error has been logged."), 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)