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
    mail.init_app(app)          # add this
    login_manager.init_app(app)
    login_manager.login_view = "login"

<<<<<<< HEAD
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)
app.config['SESSION_PERMANENT'] = False
app.config['REMEMBER_COOKIE_SECURE'] = True   # only over HTTPS
app.config['SESSION_COOKIE_SECURE'] = True
app.config['ADMIN_SECRET'] = os.environ.get('ADMIN_SECRET_KEY')
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_app_password'
app.config['MAIL_DEFAULT_SENDER'] = 'your_email@gmail.com'
=======
    with app.app_context():
        db.create_all()
        seed_subjects()
>>>>>>> 1856202 (Multi-exam support, reports overhaul, and blueprint refactor)

    from blueprints.reports import reports_bp
    from blueprints.api import api_bp
    from blueprints.marks import marks_bp
    from blueprints.main import main_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(marks_bp)


    @app.cli.command('seed-demo')
    def seed_demo_command():
        """Populate database with demo data (20 schools, 50 students/grade)."""
        from seed_demo import seed_demo_data 
        seed_demo_data()

    def generate_password(length=8):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

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

        safe_filename = os.path.basename(filename)   # security against directory traversal
        filepath = os.path.join(logs_dir, safe_filename)
        if not os.path.isfile(filepath):
            abort(404)
        return send_file(filepath, as_attachment=True, download_name=safe_filename, mimetype='text/plain')

    @app.route('/admin/users', methods=['GET', 'POST'])
    @login_required
    def manage_users():
        if current_user.role not in ['admin', 'principal']:
            abort(403)

        # ----- Build schools list (used by both GET and POST rendering) -----
        if current_user.role == 'admin':
            schools = School.query.all()
        else:
            schools = [School.query.get(current_user.school_id)]

        # ----- GET: fetch the users that will be shown in the table -----
        if request.method == 'GET':
            if current_user.role == 'admin':
                # Regular admin cannot see super admin accounts
                if current_user.is_superadmin:
                    users = User.query.filter(User.role != None).options(joinedload(User.school)).all()
                else:
                    users = User.query.filter(User.role != None, User.is_superadmin == False).options(joinedload(User.school)).all()
            else:  # principal
                users = User.query.filter_by(school_id=current_user.school_id, role='teacher').options(joinedload(User.school)).all()

            return render_template("admin_users.html", schools=schools, users=users)

        # ----- POST: create a new user -----
        username = request.form['username']
        role = request.form['role']
        school_id = request.form.get('school_id')
        school_id = int(school_id) if school_id else None
        grade = request.form.get('grade')

        # Validation
        # Principal can only create teacher accounts for their own school
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

        # Auto‑generate password
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

        # ---------- Super admin cannot be deleted ----------
        if target.is_superadmin:
            flash('The super admin account cannot be deleted.', 'danger')
            return redirect(url_for('manage_users'))

        # ---------- Self‑deletion prevention ----------
        if target.id == current_user.id:
            flash('You cannot delete your own account.', 'danger')
            return redirect(url_for('manage_users'))

        # ---------- Principal scope: only teachers in own school ----------
        if current_user.role == 'principal':
            if target.role != 'teacher' or target.school_id != current_user.school_id:
                flash('You can only delete teachers from your own school.', 'danger')
                return redirect(url_for('manage_users'))

        # Admin can delete any other admin, principal, teacher (except super admin, already caught)
        db.session.delete(target)
        db.session.commit()
<<<<<<< HEAD
        return redirect('/')
    return render_template('add_school.html')
#Edit and delete School

# Edit School
@app.route('/edit_school/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_school(id):
    school = School.query.get_or_404(id)
    if request.method == 'POST':
        school.name = request.form['name']
        school.type = request.form.get('type', school.type)
        db.session.commit()
        flash('School updated.', 'success')
        return redirect(url_for('schools'))
    return render_template('edit_school.html', school=school)

# Delete School
@app.route('/delete_school/<int:id>')
@login_required
@role_required('admin')
def delete_school(id):
    school = School.query.get_or_404(id)
    # also delete all related students, marks, users?
    # for safety, only allow if no students?
    if school.students:
        flash('Cannot delete school with students. Remove students first.', 'danger')
        return redirect(url_for('schools'))
    db.session.delete(school)
    db.session.commit()
    flash('School deleted.', 'success')
    return redirect(url_for('schools'))

# Add Student
@app.route('/add_student', methods=['GET', 'POST'])
@login_required
def add_student():
    schools = School.query.all()
    if request.method == 'POST':
        student = Student(
            name=request.form['name'],
            grade=request.form['grade'],
            gender=request.form.get('gender', 'M'),
            school_id=request.form['school_id']
        )
        db.session.add(student)
        db.session.commit()
        flash('Student added successfully.', 'success')
        return redirect(url_for('students'))
    return render_template('add_student.html', schools=schools)
    
@app.route('/school_dashboard')
@login_required
def school_dashboard():
    if current_user.role not in ['principal', 'admin']:
        abort(403)
    if current_user.role == 'admin':
        # admin must select a school? We'll redirect to a selector or use query param.
        school_id = request.args.get('school_id')
        if not school_id:
            schools = School.query.all()
            return render_template('school_selector.html', schools=schools)
        school = School.query.get_or_404(int(school_id))
    else:
        school_id = current_user.school_id
        school = School.query.get(school_id)
    
    # gather per-grade data for latest term/year? We'll just show links.
    grades = ["PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4","Grade 5","Grade 6","Grade 7","Grade 8","Grade 9"]
    
    # Example: show number of students per grade
    grade_counts = {}
    for g in grades:
        count = Student.query.filter_by(school_id=school.id, grade=g).count()
        grade_counts[g] = count
    
    # Quick links: for each grade, link to enter_marks with current year and Term 1 as default? We can set year=2026.
    return render_template('principal_dashboard.html', school=school, grades=grades, grade_counts=grade_counts)

@app.route('/api/add_student_with_marks', methods=['POST'])
@login_required
def add_student_with_marks():

    data = request.get_json()

    # -----------------------------
    # Validate required fields
    # -----------------------------
    name = data.get("name")
    grade = data.get("grade")
    term = data.get("term")
    year = data.get("year")
    marks = data.get("marks", {})

    if not name or not grade or not term or not year:
        return jsonify({"error": "Missing required fields"}), 400

    # -----------------------------
    # Check duplicates (optional but recommended)
    # -----------------------------
    existing = Student.query.filter_by(
    name=name,
    grade=grade
    ).first()
    if existing:
        return jsonify({"error": "Student already exists in this grade"}), 400

    # -----------------------------
    # Create student
    # -----------------------------
    # Determine the school_id
    if current_user.role == "admin":
        school_id = data.get("school_id")
    else:
        school_id = current_user.school_id

    # Check duplicates
    existing = Student.query.filter_by(
        name=name,
        grade=grade,
        school_id=school_id
    ).first()
    if existing:
        return jsonify({"error": "Student already exists in this grade"}), 400

    # Create student
    student = Student(
        name=name,
        grade=grade,
        school_id=school_id
    )

    db.session.add(student)
    db.session.flush()  # get student.id before commit

    # -----------------------------
    # Save marks
    # -----------------------------
    for subject_id, score in marks.items():

        try:
            score = float(score)
        except:
            return jsonify({"error": f"Invalid score for subject {subject_id}"}), 400

        if score < 0 or score > 100:
            return jsonify({"error": "Score must be between 0 and 100"}), 400

        db.session.add(Mark(
            student_id=student.id,
            subject_id=int(subject_id),
            score=score,
            term=term,
            year=year,
            cbc_level=cbc_grade(score)
        ))

    # -----------------------------
    # Commit all changes
    # -----------------------------
    db.session.commit()

    return jsonify({
        "status": "success",
        "student_id": student.id,
        "message": "Student and marks saved successfully"
    })

#Upload CSV

@app.route('/upload_csv', methods=['GET', 'POST'])
@login_required
def upload_csv():
    # Only admin, principal, teacher can upload
    if current_user.role not in ['admin', 'principal', 'teacher']:
        abort(403)

    if request.method == 'POST':
        # Check if file part exists
        if 'csv_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(request.url)

        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)

        # Validate file extension (optional)
        if not file.filename.lower().endswith('.csv'):
            flash('Only CSV files are allowed.', 'danger')
            return redirect(request.url)

        # Read and parse CSV
        try:
            stream = io.StringIO(file.stream.read().decode('utf-8'))
            csv_reader = csv.DictReader(stream)
        except Exception as e:
            flash(f'Error reading CSV: {str(e)}', 'danger')
            return redirect(request.url)

        # Collect rows and validate headers
        required_headers = {'name', 'grade'}
        # Optionally allow 'marks' columns (subject names) – we'll handle later
        if not required_headers.issubset(csv_reader.fieldnames):
            flash('CSV must contain at least "name" and "grade" columns.', 'danger')
            return redirect(request.url)

        # Determine school_id based on role
        if current_user.role == 'admin':
            school_id = request.form.get('school_id')
            if not school_id:
                flash('Please select a school for the upload.', 'danger')
                return redirect(request.url)
        else:
            school_id = current_user.school_id

        # Process rows
        success_count = 0
        error_rows = []
        for idx, row in enumerate(csv_reader, start=2):  # 2 because header=1
            name = row.get('name', '').strip()
            grade = row.get('grade', '').strip()

            # Skip empty rows
            if not name or not grade:
                continue

            # Teacher can only add to their own grade
            if current_user.role == 'teacher' and grade != current_user.grade:
                error_rows.append(f'Row {idx}: grade mismatch (you can only add to {current_user.grade})')
                continue

            # Check if student already exists in this school+grade
            existing = Student.query.filter_by(
                name=name,
                grade=grade,
                school_id=school_id
            ).first()
            if existing:
                error_rows.append(f'Row {idx}: student "{name}" already exists in {grade}.')
                continue

            gender = row.get('gender', 'M').strip().upper()
            if gender not in ('M', 'F'):
                gender = 'M'  # default fallback


            # Create student
            student = Student(
                name=name,
                grade=grade,
                gender =gender,
                school_id=school_id
            )
            db.session.add(student)
            db.session.flush()  # get student.id

            # Optional: check for marks columns (any column not name/grade)
            marks = {}
            for col in row.keys():
                if col not in ['name', 'grade'] and row[col].strip():
                    # Find subject by name and grade
                    subject = Subject.query.filter_by(name=col, grade=grade).first()
                    if subject:
                        try:
                            score = float(row[col])
                            if 0 <= score <= 100:
                                marks[subject.id] = score
                            else:
                                error_rows.append(f'Row {idx}: score for {col} out of range (0-100), skipping mark.')
                        except ValueError:
                            error_rows.append(f'Row {idx}: score for {col} is not a number, skipping mark.')
                    else:
                        error_rows.append(f'Row {idx}: subject "{col}" not found for {grade}, skipping mark.')

            # Save marks if term and year provided
            term = request.form.get('term')
            year = request.form.get('year')
            if marks and term and year:
                try:
                    year = int(year)
                except:
                    error_rows.append('Invalid year, marks not saved.')
                else:
                    for sub_id, score in marks.items():
                        db.session.add(Mark(
                            student_id=student.id,
                            subject_id=sub_id,
                            score=score,
                            term=term,
                            year=year,
                            cbc_level=cbc_grade(score)
                        ))

            success_count += 1

        try:
            db.session.commit()
            flash(f'{success_count} student(s) imported successfully.', 'success')
            if error_rows:
                flash('Some errors occurred: ' + '; '.join(error_rows), 'warning')
        except Exception as e:
            db.session.rollback()
            flash(f'Database error: {str(e)}', 'danger')
            return redirect(request.url)

        return redirect(url_for('upload_csv'))

    # GET request – show form
    schools = School.query.all() if current_user.role == 'admin' else []
    return render_template('upload_csv.html', schools=schools)

#Add Subject
@app.route('/add_subject', methods=['GET', 'POST'])
def add_subject():
    if request.method == 'POST':
        name = request.form['name']
        grade = request.form['grade']

        db.session.add(Subject(name=name, grade=grade))
        db.session.commit()

        return redirect('/subjects')

    return render_template('add_subject.html')

# Timetable

import io
import pandas as pd
from flask import send_file
from timetable_generator import generate_timetable, generate_subjects_template, generate_allocation_template

@app.route('/timetable', methods=['GET', 'POST'])
@login_required
def timetable_page():
    if current_user.role not in ['admin', 'principal']:
        abort(403)

    if request.method == 'POST':
        # ---- (A) Upload CSV files and generate ----
        if 'subjects_file' in request.files and 'alloc_file' in request.files:
            subj_file = request.files['subjects_file']
            alloc_file = request.files['alloc_file']
            if subj_file.filename == '' or alloc_file.filename == '':
                flash('Both files are required.', 'danger')
                return redirect(url_for('timetable_page'))
            if not subj_file.filename.endswith('.csv') or not alloc_file.filename.endswith('.csv'):
                flash('Only CSV files are allowed.', 'danger')
                return redirect(url_for('timetable_page'))
            try:
                subs_df = pd.read_csv(subj_file)
                alloc_df = pd.read_csv(alloc_file)
            except Exception as e:
                flash(f'Error reading CSV: {str(e)}', 'danger')
                return redirect(url_for('timetable_page'))

            selected_grades = request.form.getlist('grades')
            if not selected_grades:
                flash('Please select at least one grade.', 'danger')
                return redirect(url_for('timetable_page'))

            try:
                timetable_df = generate_timetable(subs_df, alloc_df, grades=selected_grades)
            except Exception as e:
                flash(f'Error: {str(e)}', 'danger')
                return redirect(url_for('timetable_page'))

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                timetable_df.to_excel(writer, sheet_name='Timetable', index=False)
            output.seek(0)
            return send_file(
                output,
                download_name='timetable.xlsx',
                as_attachment=True,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

        # ---- (B) Download template CSVs ----
        if 'download_subjects_template' in request.form or 'download_alloc_template' in request.form:
            selected_grades = request.form.getlist('grades')
            if not selected_grades:
                flash('Please select at least one grade.', 'warning')
                return redirect(url_for('timetable_page'))

            if 'download_subjects_template' in request.form:
                df = generate_subjects_template(selected_grades)
                filename = 'subjects_template.csv'
            else:
                df = generate_allocation_template(selected_grades)
                filename = 'allocation_template.csv'

            output = io.BytesIO()
            df.to_csv(output, index=False)
            output.seek(0)
            return send_file(
                output,
                download_name=filename,
                as_attachment=True,
                mimetype='text/csv'
            )

        flash('Invalid action.', 'danger')
        return redirect(url_for('timetable_page'))

    # GET
    all_grades = [
        "PP1", "PP2",
        "Grade 1", "Grade 2", "Grade 3",
        "Grade 4", "Grade 5", "Grade 6",
        "Grade 7", "Grade 8", "Grade 9"
    ]
    return render_template('timetable.html', all_grades=all_grades)

# Marks

@app.route('/marks')
@login_required
def marks():
    schools = School.query.all()
    return render_template('marks.html', schools=schools)

# Enter Marks
@app.route('/enter_marks', methods=['GET'])
@login_required
def enter_marks():

    grade = request.args.get('grade')
    term = request.args.get('term')
    year = request.args.get('year')

    # -------------------------
    # ROLE-BASED SCHOOL LOGIC
    # -------------------------
    if current_user.role == "admin":
        school_id = request.args.get('school_id')
        if not school_id:
            flash("Please select a school first.", "warning")
            return redirect(url_for('marks'))
    else:
        school_id = current_user.school_id

    # -------------------------
    # TEACHER GRADE LOCK
    # -------------------------
    if current_user.role == "teacher":
        grade = current_user.grade

    school = School.query.get(school_id)
    if not school:
        return "Invalid school", 404
    
    students = []
    subjects = []
    marks_dict = {}

    # -------------------------
    # LOAD DATA
    # -------------------------
    if grade and school_id:

        students = [
            {"id": s.id, "name": s.name}
            for s in Student.query.filter_by(
                grade=grade,
                school_id=school_id
            ).all()
        ]

        subjects = [
            {"id": s.id, "name": s.name}
            for s in Subject.query.filter_by(grade=grade).all()
        ]

    # -------------------------
    # LOAD MARKS (SAFE + FILTERED)
    # -------------------------
    if grade and term and year:

        marks = db.session.query(Mark)\
            .join(Student, Mark.student_id == Student.id)\
            .filter(
                Student.grade == grade,
                Student.school_id == school_id,  # ✅ CRITICAL FIX
                Mark.term == term,
                Mark.year == year
            ).all()

        print(f"Found {len(marks)} marks")

        for m in marks:
            marks_dict[f"{m.student_id}_{m.subject_id}"] = m.score

    # -------------------------
    # RENDER
    # -------------------------
    return render_template(
        "enter_marks.html",
        school=school,
        school_id=school_id,
        grade=grade,
        term=term,
        year=year,
        students=students,
        subjects=subjects,
        marks_dict=marks_dict
    )

#Save Marks

@app.route('/save_marks', methods=['POST'])
@login_required
def save_marks():
    data = request.json
    student_id = data['student_id']
    term = data['term']
    year = data['year']
    marks = data['marks']

    # Fetch student and validate access
    student = Student.query.get(student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    if current_user.role != "admin":
        if current_user.school_id != student.school_id:
            return jsonify({"error": "Access denied: wrong school"}), 403
        if current_user.role == "teacher":
            if current_user.grade != student.grade:
                return jsonify({"error": "You can only enter marks for your assigned grade"}), 403
            # Optional: ensure the teacher’s grade matches, but front‑end already enforces

    for subject_id, score in marks.items():
        # Validate score
        try:
            score = float(score)
        except ValueError:
            return jsonify({"error": "Invalid score"}), 400
        if score < 0 or score > 100:
            return jsonify({"error": "Score out of range"}), 400

        # Optional: check subject exists and grade matches student
        subject = Subject.query.get(int(subject_id))
        if not subject or subject.grade != student.grade:
            return jsonify({"error": f"Subject #{subject_id} not valid for this student"}), 400

        grade_level = cbc_grade(score)

        existing = Mark.query.filter_by(
            student_id=student.id,
            subject_id=int(subject_id),
            term=term,
            year=year
        ).first()

=======
        flash(f"User '{target.username}' deleted.", 'success')
        return redirect(url_for('manage_users'))

    @login_manager.unauthorized_handler
    def unauthorized():
        return redirect('/login')

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html',
                               error_title="Access Denied",
                               error_message="You don't have permission to access this page."), 403

    @app.cli.command('create-super-admin')
    @click.argument('username')
    @click.argument('password')
    def create_super_admin(username, password):
        """Create a super admin user that cannot be deleted."""
        existing = User.query.filter_by(username=username).first()
>>>>>>> 1856202 (Multi-exam support, reports overhaul, and blueprint refactor)
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

    @app.cli.command('create-admin')
    @click.argument('username')
    @click.argument('password')
    def create_admin_cli(username, password):
        """Create an admin user."""
        admin = User(
            username=username,
            password=generate_password_hash(password, method="pbkdf2:sha256"),
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()
        print(f"Admin '{username}' created.")

    #Login

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
                return redirect(next_page or url_for('main.index'))
            else:
                login_logger.warning(f"Login FAILURE: username '{username}' from IP {request.remote_addr}")
                flash("Invalid username or password", "danger")
                return redirect(url_for('login'))

        return render_template("login.html")

    # Logout

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect('/login')

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
