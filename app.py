from flask import Flask, abort, render_template, request, redirect, jsonify, flash, url_for, send_file
from models import db, School, Student, Subject, Mark, User
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import timedelta
from functools import wraps
from flask_mail import Mail, Message
from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash as _generate_password_hash
from seed import seed_subjects
from flask_migrate import Migrate
from models import db
from sqlalchemy import func, case
import pandas as pd
import io
import os
import random
import string
import click
import functools
import csv

generate_password_hash = functools.partial(_generate_password_hash, method="pbkdf2:sha256")

def role_required(role):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()

            if current_user.role != role:
                abort(403)

            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

def cbc_grade(score):
    try:
        score = float(score)
    except:
        return None

    if score >= 75:
        return "EE"
    elif score >= 50:
        return "ME"
    elif score >= 30:
        return "AE"
    else:
        return "BE"

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

mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

db.init_app(app)

# Create DB

with app.app_context():
    db.create_all()
    seed_subjects()

migrate = Migrate(app, db)

@app.cli.command('seed-demo')
def seed_demo_command():
    """Populate database with demo data (20 schools, 50 students/grade)."""
    from seed_demo import seed_demo_data
    seed_demo_data()

def generate_password(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_users():

    schools = School.query.all()

    if request.method == 'POST':

        username = request.form['username']
        role = request.form['role']
        school_id = request.form.get('school_id')
        school_id = int(school_id) if school_id else None
        grade = request.form.get('grade')

        # -----------------------
        # VALIDATION
        # -----------------------
        if role != "admin" and not school_id:
            flash("Please select a school.", "danger")
            return redirect(url_for('manage_users'))

        if role == "teacher" and not grade:
            flash("Grade is required for teachers.", "danger")
            return redirect(url_for('manage_users'))

        # -----------------------
        # AUTO PASSWORD
        # -----------------------
        password_plain = generate_password()

        user = User(
            username=username,
            password=generate_password_hash(password_plain, method="pbkdf2:sha256"),
            role=role,
            school_id=school_id if role != "admin" else None,
            grade=grade if role == "teacher" else None
        )

        db.session.add(user)
        db.session.commit()

        return render_template(
            "user_created.html",
            username=username,
            password=password_plain
        )
    users = User.query.filter(User.role != None).options(joinedload(User.school)).all()

    return render_template(
        "admin_users.html",
        schools=schools,
        users=users
    )

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

# Home
@app.route('/')
@login_required
def index():
    schools_count = School.query.count()
    students_count = Student.query.count()
    subjects_count = Subject.query.count()

    return render_template(
        'index.html',
        schools_count=schools_count,
        students_count=students_count,
        subjects_count=subjects_count,
    )
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
# Schools

@app.route('/schools')
@login_required
def schools():
    schools = School.query.all()
    return render_template('schools.html', schools=schools)

# Add School
@app.route('/add_school', methods=['GET', 'POST'])
@login_required 
def add_school():
    if request.method == 'POST':
        name = request.form['name']
        type=request.form.get('type', 'Public')
        db.session.add(School(name=name))
        db.session.commit()
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

        if existing:
            existing.score = score
            existing.cbc_level = grade_level
        else:
            db.session.add(Mark(
                student_id=student.id,
                subject_id=int(subject_id),
                score=score,
                term=term,
                year=year,
                cbc_level=grade_level
            ))

    try:
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

@app.route('/edit_student/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_student(id):
    student = Student.query.get_or_404(id)
    schools = School.query.all()

    if request.method == 'POST':
        student.name = request.form['name']
        student.grade = request.form['grade']
        student.school_id = request.form['school_id']

        db.session.commit()
        return redirect('/')

    return render_template('edit_student.html', student=student, schools=schools)

@app.route('/delete_student/<int:id>')
@login_required
def delete_student(id):
    student = Student.query.get_or_404(id)

    # optional: delete marks too
    Mark.query.filter_by(student_id=student.id).delete()

    db.session.delete(student)
    db.session.commit()

    return redirect('/')

#Student Profile Route

@app.route('/student/<int:student_id>')
@login_required
def student_profile(student_id):
    student = Student.query.get_or_404(student_id)
    term = request.args.get('term')
    year = request.args.get('year')
    
    query = db.session.query(
        Subject.name.label("subject"),
        Mark.score.label("score"),
        Mark.term,
        Mark.year
    ).join(Mark, Mark.subject_id == Subject.id)\
     .filter(Mark.student_id == student_id)
    
    if term:
        query = query.filter(Mark.term == term)
    if year:
        try:
            query = query.filter(Mark.year == int(year))
        except ValueError:
            pass
    
    results = query.all()

    data = [
        {
            "subject": r.subject,
            "score": r.score,
            "term": r.term,
            "year": r.year
        }
        for r in results
    ]

    terms_years = db.session.query(Mark.term, Mark.year).filter(Mark.student_id == student_id).distinct().all()
    
    return render_template('student_profile.html', student=student, data=data, terms_years=terms_years, selected_term=term, selected_year=year)

# Quick Student List

@app.route('/students')
@login_required
def students():
    students = Student.query.all()
    return render_template('students.html', students=students)

#Subjects

@app.route('/subjects')
def subjects():
    grade = request.args.get('grade')

    if grade:
        subjects = Subject.query.filter_by(grade=grade).all()
    else:
        subjects = Subject.query.all()

    return render_template('subjects.html', subjects=subjects, grade=grade)

# Edit Subjects

@app.route('/edit_subject/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_subject(id):
    subject = Subject.query.get_or_404(id)

    if request.method == 'POST':
        subject.name = request.form['name']
        db.session.commit()
        return redirect('/subjects')

    return render_template('edit_subject.html', subject=subject)

# Delete Subjects

@app.route('/delete_subject/<int:id>')
@login_required
def delete_subject(id):
    subject = Subject.query.get_or_404(id)

    # ⚠️ IMPORTANT: delete related marks
    Mark.query.filter(Mark.subject_id == subject.id).delete()

    db.session.delete(subject)
    db.session.commit()

    return redirect('/subjects')

#Login

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':

        user = User.query.filter_by(
            username=request.form['username']
        ).first()

        if user and check_password_hash(user.password, request.form['password']):

            remember = True if request.form.get('remember') else False
            login_user(user, remember=remember)

            flash("Login successful", "success")

            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))

        flash("Invalid username or password", "danger")
        return redirect(url_for('login'))

    return render_template("login.html")

# Dashboard Analytics

@app.route('/analytics')
@login_required
def analytics():
    schools = School.query.all()

    return render_template(
        "analytics.html",
        schools=schools,
        grades=[
            "PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4","Grade 5",
            "Grade 6","Grade 7","Grade 8","Grade 9"
        ]
    )

# APIs

@app.route('/api/analytics')
@login_required
def api_analytics():
    grade = request.args.get('grade')
    school_id = request.args.get('school_id')
    student_id = request.args.get('student_id')
    year = request.args.get('year')
    term = request.args.get('term')
    
    if current_user.role != "admin":
        school_id = current_user.school_id
    else:
        school_id = request.args.get('school_id')

    query = db.session.query(
        Subject.name.label("subject"),
        Student.grade.label("grade"),
        School.name.label("school"),
        Student.id.label("student_id"),
        Student.name.label("student_name"),
        db.func.avg(Mark.score).label("avg_score")
    ).select_from(Mark)\
     .join(Subject, Mark.subject_id == Subject.id)\
     .join(Student, Mark.student_id == Student.id)\
     .join(School, Student.school_id == School.id)

    # Convert IDs to integers
    if school_id:
        query = query.filter(School.id == int(school_id))

    if grade:
        query = query.filter(Student.grade == grade)

    if student_id:
        query = query.filter(Student.id == int(student_id))

    # Convert Year to integer
    if year:
        try:
            query = query.filter(Mark.year == int(year))
        except ValueError:
            pass # Ignore if the user typed "Twenty Twenty Four" by accident

    if term:
        query = query.filter(Mark.term == term)

    results = query.group_by(
        Subject.name,
        Student.grade,
        School.name,
        Student.id,
        Student.name
    ).all()

    data = [
        {
            "subject": r.subject,
            "grade": r.grade,
            "school": r.school,
            "student_id": r.student_id,
            "student_name": r.student_name,
            "avg_score": float(r.avg_score)
        }
        for r in results
    ]

    # Return data with headers to prevent the browser from caching old data
    response = jsonify({"data": data})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

@app.route('/api/grades')
@login_required
def get_grades():
    if current_user.role != "admin":
        school_id = current_user.school_id
    else:
        school_id = request.args.get('school_id')

    query = db.session.query(Student.grade).distinct()

    if school_id:
        query = query.filter(Student.school_id == school_id)

    grades = [g[0] for g in query.all()]

    return {"grades": grades}

@app.route('/api/students')
@login_required
def get_students():
    if current_user.role != "admin":
        school_id = current_user.school_id
    else:
        school_id = request.args.get('school_id')

    grade = request.args.get('grade')

    query = Student.query

    if school_id:
        query = query.filter(Student.school_id == school_id)

    if grade:
        query = query.filter(Student.grade == grade)

    students = query.all()

    return {
        "students": [
            {"id": s.id, "name": s.name}
            for s in students
        ]
    }
@app.route('/api/school_overview')
@login_required
def api_school_overview():
    school_id = request.args.get('school_id')
    year = request.args.get('year')
    term = request.args.get('term')

    # Restrict non‑admin users to their own school
    if current_user.role != "admin":
        school_id = current_user.school_id

    if not school_id:
        return jsonify({"error": "school_id required"}), 400

    query = db.session.query(
        func.avg(Mark.score).label('avg_score'),
        func.count(func.distinct(Student.id)).label('student_count')
    ).select_from(Mark)\
     .join(Student, Mark.student_id == Student.id)\
     .filter(Student.school_id == int(school_id))

    if term:
        query = query.filter(Mark.term == term)
    if year:
        try:
            query = query.filter(Mark.year == int(year))
        except ValueError:
            pass

    result = query.first()
    avg = round(result.avg_score, 2) if result.avg_score else 0
    students = result.student_count if result.student_count else 0

    return jsonify({
        "avg_score": avg,
        "student_count": students
    })
# Reports

@app.route('/reports')
@login_required
def reports():
    # Access control
    if current_user.role not in ['admin', 'principal', 'teacher']:
        abort(403)

    selected_term = request.args.get('term', 'Term 1')
    selected_year = request.args.get('year', None)

    if current_user.role == 'admin':
        school_id = request.args.get('school_id')
        grade = request.args.get('grade')
    elif current_user.role == 'principal':
        school_id = current_user.school_id
        grade = request.args.get('grade')
    else:  # teacher
        school_id = current_user.school_id
        grade = current_user.grade

    # === 1. Schools per grade averages (unchanged) ===
    school_query = db.session.query(
        School.name.label('school_name'),
        School.type.label('school_type'),
        Student.grade.label('grade'),
        func.avg(Mark.score).label('avg_score'),
        func.count(func.distinct(Student.id)).label('student_count')
    ).select_from(Mark)\
     .join(Student, Mark.student_id == Student.id)\
     .join(School, Student.school_id == School.id)

    if selected_term:
        school_query = school_query.filter(Mark.term == selected_term)
    if selected_year:
        try:
            year_int = int(selected_year)
            school_query = school_query.filter(Mark.year == year_int)
        except ValueError:
            year_int = None
    if school_id:
        school_query = school_query.filter(School.id == int(school_id))
    if grade:
        school_query = school_query.filter(Student.grade == grade)

    school_results = school_query.group_by(
        School.name, School.type, Student.grade
    ).order_by(Student.grade, func.avg(Mark.score).desc()).all()

    # === 2. Top Male / Female per grade (by TOTAL marks, not average) ===
    top_n = 3
    top_male = []
    top_female = []

    # Build grades list
    if grade is None:
        grades = "Grade 9"
    else:
        grade_query = db.session.query(Student.grade).join(Mark)
        if school_id:
            grade_query = grade_query.filter(Student.school_id == int(school_id))
        if selected_term:
            grade_query = grade_query.filter(Mark.term == selected_term)
        if selected_year:
            grade_query = grade_query.filter(Mark.year == int(selected_year))
        grades = [g[0] for g in grade_query.distinct().all()]

    for g in grades:
        for gen, target_list in [('M', top_male), ('F', top_female)]:
            # Subquery to calculate total marks per student
            sub = db.session.query(
                Student.id,
                func.sum(Mark.score).label('total_score')
            ).join(Mark, Student.id == Mark.student_id)\
             .filter(Student.grade == g, Student.gender == gen)

            if school_id:
                sub = sub.filter(Student.school_id == int(school_id))
            if selected_term:
                sub = sub.filter(Mark.term == selected_term)
            if selected_year:
                sub = sub.filter(Mark.year == int(selected_year))

            sub = sub.group_by(Student.id).order_by(func.sum(Mark.score).desc()).limit(top_n).subquery()

            result = db.session.query(
                Student.id.label('student_id'),
                Student.name.label('student_name'),
                Student.grade.label('grade'),
                Student.gender.label('gender'),
                sub.c.total_score
            ).join(sub, Student.id == sub.c.id).all()

            for row in result:
                target_list.append({
                    'grade': row.grade,
                    'student_id': row.student_id,
                    'student_name': row.student_name,
                    'gender': row.gender,
                    'total_score': row.total_score
                })

    # === 3. Student Total Marks (sum across all subjects) for each student ===
    student_total_query = db.session.query(
        Student.id,
        Student.name,
        Student.grade,
        Student.gender,
        func.sum(Mark.score).label('total_score')
    ).join(Mark, Student.id == Mark.student_id)

    if selected_term:
        student_total_query = student_total_query.filter(Mark.term == selected_term)
    if selected_year:
        student_total_query = student_total_query.filter(Mark.year == int(selected_year))
    if school_id:
        student_total_query = student_total_query.filter(Student.school_id == int(school_id))
    if grade:
        student_total_query = student_total_query.filter(Student.grade == grade)

    student_totals = student_total_query.group_by(Student.id).order_by(Student.grade, func.sum(Mark.score).desc()).all()
    student_total_list = [
        {
            'student_id': r.id,
            'student_name': r.name,
            'grade': r.grade,
            'gender': r.gender,
            'total_score': r.total_score
        } for r in student_totals
    ]

    # === 4. Class Subject Averages (average score per subject across all filtered students) ===
    class_avg_query = db.session.query(
        Subject.name.label('subject_name'),
        func.avg(Mark.score).label('avg_score')
    ).select_from(Mark)\
     .join(Subject, Mark.subject_id == Subject.id)\
     .join(Student, Mark.student_id == Student.id)

    if selected_term:
        class_avg_query = class_avg_query.filter(Mark.term == selected_term)
    if selected_year:
        class_avg_query = class_avg_query.filter(Mark.year == int(selected_year))
    if school_id:
        class_avg_query = class_avg_query.filter(Student.school_id == int(school_id))
    if grade:
        class_avg_query = class_avg_query.filter(Student.grade == grade)

    class_avg_results = class_avg_query.group_by(Subject.name).order_by(func.avg(Mark.score).desc()).all()
    class_subject_averages = [
        {'subject_name': r.subject_name, 'avg_score': round(r.avg_score, 2)}
        for r in class_avg_results
    ]

    # Metadata for template
    schools = School.query.all() if current_user.role == 'admin' else []
    all_grades = ["PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4","Grade 5",
                  "Grade 6","Grade 7","Grade 8","Grade 9"]
    terms = ["Term 1","Term 2","Term 3"]

    return render_template(
        'reports.html',
        school_results=school_results,
        top_male=top_male,
        top_female=top_female,
        student_total_list=student_total_list,
        class_subject_averages=class_subject_averages,
        selected_term=selected_term,
        selected_year=selected_year,
        schools=schools,
        grades=all_grades,
        terms=terms
    )

# Logout

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')


if __name__ == '__main__':
    app.run(debug=True)
