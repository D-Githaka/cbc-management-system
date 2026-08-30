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
                   flash, url_for, send_file, g, has_request_context, send_from_directory)
from werkzeug.security import check_password_hash, generate_password_hash as _generate_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import event

from models import School, Student, Subject, Mark, User
from utils.preferences import get_preference
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

    # with app.app_context():
        # db.create_all()
        # seed_subjects()

    # ---------- Blueprints ----------
    from blueprints.reports import reports_bp
    from blueprints.api import api_bp
    from blueprints.marks import marks_bp
    from blueprints.main import main_bp
    from blueprints.approvals import approvals_bp
    app.register_blueprint(approvals_bp)
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
            try:
                hist = attr.get_history(target, attr.key)
            except AttributeError:
                # Some column types (e.g. Boolean) may not support get_history
                continue
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

    @app.route('/admin/logs/view/<filename>')
    @login_required
    def view_log(filename):
        if current_user.role != 'admin':
            abort(403)
        safe_filename = os.path.basename(filename)
        filepath = os.path.join(logs_dir, safe_filename)
        if not os.path.isfile(filepath):
            abort(404)
        # Return the file content as plain text (rendered in browser)
        return send_file(filepath, mimetype='text/plain', as_attachment=False)
        
    @app.route('/admin/users', methods=['GET', 'POST'])
    @login_required
    def manage_users():
        if current_user.role not in ['admin', 'principal']:
            abort(403)

        # Determine schools list
        if current_user.role == 'admin':
            schools = School.query.all()
        else:
            schools = [School.query.get(current_user.school_id)] if current_user.school_id else []

        # ---------- GET: show form with filters ----------
        if request.method == 'GET':
            # 1. Read filter parameters
            filter_school_id = request.args.get('filter_school_id')
            filter_role = request.args.get('filter_role')
            filter_grade = request.args.get('filter_grade')
            filter_username = request.args.get('filter_username', '').strip()

            # 2. Build the base query
            if current_user.role == 'admin':
                query = User.query.filter(User.role != None, User.is_superadmin == False)
            else:  # principal
                query = User.query.filter_by(school_id=current_user.school_id, role='teacher')

            # 3. Apply filters (if provided)
            if filter_school_id:
                query = query.filter(User.school_id == int(filter_school_id))
            if filter_role:
                query = query.filter(User.role == filter_role)
            if filter_grade:
                query = query.filter(User.grade == filter_grade)
            if filter_username:
                query = query.filter(User.username.ilike(f'%{filter_username}%'))

            users = query.options(joinedload(User.school)).all()

            # 4. Load global filters for the creation form (default school)
            saved = get_preference('global_filters', {})
            saved_school_id = saved.get('school_id')
            if current_user.role == 'admin':
                if saved_school_id and any(s.id == int(saved_school_id) for s in schools):
                    selected_school_id = int(saved_school_id)
                else:
                    selected_school_id = schools[0].id if schools else None
            else:
                selected_school_id = current_user.school_id

            selected_role = request.args.get('filter_role', 'teacher')
            selected_grade = request.args.get('filter_grade', '')

            # 5. Pass filters back to template
            return render_template("admin_users.html",
                                   schools=schools,
                                   users=users,
                                   selected_role=selected_role,
                                   selected_school_id=selected_school_id,
                                   selected_grade=selected_grade,
                                   filter_school_id=filter_school_id,
                                   filter_role=filter_role,
                                   filter_grade=filter_grade,
                                   filter_username=filter_username)

        # ---------- POST: create user ----------
        # Read form data
        username = request.form.get('username', '').strip()
        role = request.form.get('role')
        school_id = request.form.get('school_id')
        school_id = int(school_id) if school_id else None
        grade = request.form.get('grade')

        # ---- Validation ----
        if not username:
            flash("Username is required.", "danger")
            return render_template("admin_users.html",
                                   schools=schools,
                                   users=User.query.filter_by(school_id=current_user.school_id, role='teacher').options(joinedload(User.school)).all() if current_user.role == 'principal' else User.query.filter(User.role != None, User.is_superadmin == False).options(joinedload(User.school)).all(),
                                   selected_role=role,
                                   selected_school_id=school_id,
                                   selected_grade=grade)

        if current_user.role == 'principal' and role != 'teacher':
            flash("Principal can only create teacher accounts.", "danger")
            return render_template("admin_users.html",
                                   schools=schools,
                                   users=User.query.filter_by(school_id=current_user.school_id, role='teacher').options(joinedload(User.school)).all(),
                                   selected_role=role,
                                   selected_school_id=school_id,
                                   selected_grade=grade)

        if role != "admin" and not school_id:
            flash("Please select a school.", "danger")
            return render_template("admin_users.html",
                                   schools=schools,
                                   users=User.query.filter_by(school_id=current_user.school_id, role='teacher').options(joinedload(User.school)).all() if current_user.role == 'principal' else User.query.filter(User.role != None, User.is_superadmin == False).options(joinedload(User.school)).all(),
                                   selected_role=role,
                                   selected_school_id=school_id,
                                   selected_grade=grade)

        if role == "teacher" and not grade:
            flash("Grade is required for teachers.", "danger")
            return render_template("admin_users.html",
                                   schools=schools,
                                   users=User.query.filter_by(school_id=current_user.school_id, role='teacher').options(joinedload(User.school)).all() if current_user.role == 'principal' else User.query.filter(User.role != None, User.is_superadmin == False).options(joinedload(User.school)).all(),
                                   selected_role=role,
                                   selected_school_id=school_id,
                                   selected_grade=grade)

        # ---- Generate password and create user ----
        password_plain = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        user = User(
            username=username,
            password=generate_password_hash(password_plain),
            role=role,
            school_id=school_id if role != "admin" else None,
            grade=grade if role == "teacher" else None
        )
        db.session.add(user)
        db.session.commit()

        # ---- Success: show password once ----
        return render_template("user_created.html", username=username, password=password_plain)

    @app.route('/admin/users/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def edit_user(id):
        if current_user.role not in ['admin', 'principal']:
            abort(403)

        target = db.session.get(User, id)
        if not target:
            flash('User not found.', 'danger')
            return redirect(url_for('manage_users'))

        # Principal can only edit teachers in their own school
        if current_user.role == 'principal':
            if target.role != 'teacher' or target.school_id != current_user.school_id:
                flash('You can only edit teachers from your own school.', 'danger')
                return redirect(url_for('manage_users'))

        # Prevent editing superadmin by anyone
        if getattr(target, 'is_superadmin', False) and not getattr(current_user, 'is_superadmin', False):
            flash('You cannot edit the super admin account.', 'danger')
            return redirect(url_for('manage_users'))

        # Build schools list for the dropdown
        if current_user.role == 'admin':
            schools = School.query.all()
        else:
            schools = [School.query.get(current_user.school_id)]

        if request.method == 'POST':
            new_username = request.form.get('username', '').strip()
            new_role = request.form.get('role', target.role)
            new_school_id = request.form.get('school_id')
            new_grade = request.form.get('grade')
            new_password = request.form.get('password', '').strip()

            if new_username and new_username != target.username:
                existing = User.query.filter_by(username=new_username).first()
                if existing:
                    flash('Username already taken.', 'danger')
                    return redirect(url_for('edit_user', id=id))
                target.username = new_username

            # Only admin can change roles
            if current_user.role == 'admin':
                target.role = new_role

            if new_school_id and current_user.role == 'admin':
                target.school_id = int(new_school_id)

            if new_role == 'teacher' and new_grade:
                target.grade = new_grade
            else:
                target.grade = None

            if new_password:
                target.password = generate_password_hash(new_password)

            try:
                db.session.commit()
                flash('User updated.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('manage_users'))

        return render_template('edit_user.html', user=target, schools=schools)

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
        
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(app.static_folder, 'favicon.ico')

    @app.route('/.well-known/appspecific/com.chrome.devtools.json')
    def chrome_devtools_json():
        return '', 204

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
        username = getattr(g, 'username', 'Unknown')   # <-- safe access
        error_logger.error(
            f"Unhandled exception: {e}\n"
            f"Request: {request.method} {request.path}\n"
            f"User: {username}\n"
            f"{traceback.format_exc()}"
        )
        return render_template('error.html',
                               error_title="Internal Server Error",
                               error_message="An unexpected error occurred. The error has been logged."), 500
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)