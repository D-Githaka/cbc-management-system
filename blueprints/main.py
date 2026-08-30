import io
import csv
import pandas as pd
import uuid
from flask import (Blueprint, render_template, request, redirect,
                   flash, url_for, send_file,abort)
from flask_login import login_required, current_user
from datetime import datetime
from extensions import db
from models import School, Student, Subject, Mark, User
from utils.decorators import role_required
from utils.helpers import cbc_grade
from utils.preferences import get_preference, merge_preferences
from timetable_generator import (generate_timetable,
                                 generate_subjects_template,
                                 generate_allocation_template)
from werkzeug.security import generate_password_hash
ALL_GRADES = ["PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4","Grade 5",
              "Grade 6","Grade 7","Grade 8","Grade 9"]
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def splash():
    if current_user.is_authenticated:
        # Gather dashboard stats
        schools_count = School.query.count()
        students_count = Student.query.count()
        subjects_count = Subject.query.count()
        return render_template('splash.html',
                               schools_count=schools_count,
                               students_count=students_count,
                               subjects_count=subjects_count)
    # Not logged in – no stats needed
    return render_template('splash.html')

# ---------- Schools ----------
@main_bp.route('/schools')
@login_required
def schools():
    schools = School.query.all()
    return render_template('schools.html', schools=schools)


@main_bp.route('/add_school', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def add_school():
    if request.method == 'POST':
        name = request.form['name']
        school_type = request.form.get('type', 'Public')
        entry = request.form.get('entry', '').strip()
        if not entry:
            # Auto‑generate: find the highest existing number and increment
            last = School.query.order_by(School.id.desc()).first()
            next_num = (last.id + 1) if last else 1
            entry = f"SCH-{next_num:03d}"
        # Check uniqueness
        existing = School.query.filter_by(entry=entry).first()
        if existing:
            flash('A school with that Entry number already exists.', 'danger')
            return redirect(url_for('main.add_school'))
        db.session.add(School(name=name, type=school_type, entry=entry))
        db.session.commit()
        flash('School added.', 'success')
        return redirect(url_for('main.schools'))
    return render_template('add_school.html')


@main_bp.route('/edit_school/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_school(id):
    school = School.query.get_or_404(id)
    if request.method == 'POST':
        school.name = request.form['name']
        school.type = request.form.get('type', school.type)
        new_entry = request.form.get('entry', '').strip()
        if new_entry and new_entry != school.entry:
            existing = School.query.filter_by(entry=new_entry).first()
            if existing:
                flash('That Entry number is already in use.', 'danger')
                return render_template('edit_school.html', school=school)
            school.entry = new_entry
        db.session.commit()
        flash('School updated.', 'success')
        return redirect(url_for('main.schools'))
    return render_template('edit_school.html', school=school)


@main_bp.route('/delete_school/<int:id>')
@login_required
@role_required('admin')
def delete_school(id):
    school = School.query.get_or_404(id)
    if school.students.count() > 0:
        flash('Cannot delete school with students. Remove students first.', 'danger')
        return redirect(url_for('main.schools'))
    db.session.delete(school)
    db.session.commit()
    flash('School deleted.', 'success')
    return redirect(url_for('main.schools'))


@main_bp.route('/students')
@login_required
def students():
    # Read params
    school_id = request.args.get('school_id', type=int)
    grade = request.args.get('grade')
    term = request.args.get('term')
    year = request.args.get('year', type=int)

    # Save any filter that is present (even empty)
    updates = {}
    if 'school_id' in request.args:
        updates['school_id'] = school_id or ''
    if 'grade' in request.args:
        updates['grade'] = grade or ''
    if 'term' in request.args:
        updates['term'] = term or ''
    if 'year' in request.args:
        updates['year'] = year or ''

    if updates:
        merge_preferences(updates)

    # Load saved preferences (after saving, they are updated)
    saved = get_preference('global_filters', {})

    # Role overrides
    if current_user.role == 'teacher':
        schools_list = [School.query.get(current_user.school_id)] if current_user.school_id else []
        selected_school_id = current_user.school_id
        selected_grade = current_user.grade
    elif current_user.role == 'principal':
        schools_list = [School.query.get(current_user.school_id)] if current_user.school_id else []
        selected_school_id = current_user.school_id
        selected_grade = saved.get('grade', 'Grade 1') if saved.get('grade') else 'Grade 1'
    else:  # admin
        schools_list = School.query.all()
        saved_school_id = saved.get('school_id')
        if saved_school_id and any(s.id == int(saved_school_id) for s in schools_list):
            selected_school_id = int(saved_school_id)
        else:
            selected_school_id = schools_list[0].id if schools_list else None
        selected_grade = saved.get('grade', 'Grade 1')

    selected_term = saved.get('term', 'Term 1')
    selected_year = saved.get('year', str(datetime.now().year))

    # Query students
    query = Student.query
    if selected_school_id:
        query = query.filter_by(school_id=selected_school_id)
    if selected_grade:
        query = query.filter_by(grade=selected_grade)
    students_list = query.order_by(Student.name).all()

    return render_template('students.html',
                           students=students_list,
                           schools=schools_list,
                           selected_school_id=selected_school_id,
                           selected_grade=selected_grade,
                           selected_term=selected_term,
                           selected_year=selected_year,
                           all_grades=ALL_GRADES,
                           all_terms=["Term 1", "Term 2", "Term 3"])
                          

@main_bp.route('/add_student', methods=['GET', 'POST'])
@login_required
def add_student():
    schools = School.query.all() if current_user.role == 'admin' else [School.query.get(current_user.school_id)]
    if request.method == 'POST':
        name = request.form['name']
        grade = request.form['grade']
        gender = request.form.get('gender', 'M')
        school_id = request.form.get('school_id')

        # Validate school_id
        if not school_id:
            flash('Please select a school.', 'danger')
            return redirect(url_for('main.add_student'))
        school = School.query.get(school_id)
        if not school:
            flash('Invalid school selected.', 'danger')
            return redirect(url_for('main.add_student'))

        adm = request.form.get('admission_number', '').strip()

        if not adm:
            # Auto‑generate admission number
            # Use school.entry if available, otherwise fall back to school.id
            entry_prefix = school.entry if school.entry else f"SCH-{school.id:03d}"
            # Find the highest existing number for this school
            last = Student.query.filter(
                Student.admission_number.like(f'{entry_prefix}-ADM-%')
            ).order_by(Student.admission_number.desc()).first()

            if last and last.admission_number:
                try:
                    # Extract the numeric part after the last dash
                    parts = last.admission_number.split('-')
                    last_num = int(parts[-1])
                except (ValueError, IndexError):
                    last_num = 0
            else:
                last_num = 0

            # Loop to ensure uniqueness (in case of duplicate)
            next_num = last_num + 1
            while True:
                new_adm = f"{entry_prefix}-ADM-{next_num:04d}"
                existing = Student.query.filter_by(admission_number=new_adm).first()
                if not existing:
                    adm = new_adm
                    break
                next_num += 1
        else:
            # Manual entry – check uniqueness within the school
            existing = Student.query.filter_by(school_id=school_id, admission_number=adm).first()
            if existing:
                flash('A student with that admission number already exists in this school.', 'danger')
                return redirect(url_for('main.add_student'))

        # Create and save student
        student = Student(name=name, grade=grade, gender=gender, admission_number=adm, school_id=school_id)
        db.session.add(student)
        try:
            db.session.commit()
            flash('Student added.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding student: {str(e)}', 'danger')
            return redirect(url_for('main.add_student'))

        redirect_params = {
            k: v for k, v in request.args.items()
            if k in ('grade', 'school_id', 'term', 'year')
        }
        return redirect(url_for('main.students', **redirect_params))

    return render_template('add_student.html', schools=schools)

@main_bp.route('/edit_student/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_student(id):
    student = Student.query.get_or_404(id)
    if current_user.role != 'admin':
        if current_user.school_id != student.school_id:
            abort(403)
        if current_user.role == 'teacher' and current_user.grade != student.grade:
            abort(403)

    schools = School.query.all() if current_user.role == 'admin' else [School.query.get(current_user.school_id)]

    if request.method == 'POST':
        student.name = request.form['name']
        student.grade = request.form['grade']
        student.gender = request.form.get('gender', student.gender)
        student.school_id = request.form['school_id']

        # --- Admission number logic ---
        new_adm = request.form.get('admission_number', '').strip()
        if new_adm:
            # Manual entry – check uniqueness (excluding this student)
            existing = Student.query.filter(
                Student.admission_number == new_adm,
                Student.id != student.id
            ).first()
            if existing:
                flash('A student with that admission number already exists.', 'danger')
                return render_template('edit_student.html', student=student, schools=schools)
            student.admission_number = new_adm
        # if blank, keep the existing one (or auto-generate if it was empty before)
        elif not student.admission_number:
            # Auto‑generate
            school = School.query.get(student.school_id)
            if school:
                last = Student.query.filter(
                    Student.admission_number.like(f'{school.entry}-%')
                ).order_by(Student.id.desc()).first()
                next_num = 1
                if last:
                    try:
                        next_num = int(last.admission_number.split('-')[-1]) + 1
                    except:
                        next_num = 1
                student.admission_number = f"{school.entry}-ADM-{next_num:04d}"

        db.session.commit()
        flash('Student updated.', 'success')
        redirect_params = {
            k: v for k, v in request.args.items()
            if k in ('grade', 'school_id', 'term', 'year')
        }
        return redirect(url_for('main.students', **redirect_params))


    return render_template('edit_student.html', student=student, schools=schools)


@main_bp.route('/delete_student/<int:id>')
@login_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    if current_user.role != 'admin':
        if current_user.school_id != student.school_id:
            abort(403)
        if current_user.role == 'teacher' and current_user.grade != student.grade:
            abort(403)

    Mark.query.filter_by(student_id=student.id).delete()
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted.', 'success')
    redirect_params = {
            k: v for k, v in request.args.items()
            if k in ('grade', 'school_id', 'term', 'year')
        }
    return redirect(url_for('main.students', **redirect_params))

@main_bp.route('/delete_students', methods=['POST'])
@login_required
def delete_students():
    # Get list of student ids from the form
    student_ids = request.form.getlist('student_ids')
    if not student_ids:
        flash('No students selected.', 'warning')
        # Preserve filters and redirect back
        redirect_params = {k: v for k, v in request.args.items() if k in ('grade', 'school_id', 'term', 'year')}
        return redirect(url_for('main.students', **redirect_params))

    # Convert to integers
    try:
        student_ids = [int(id) for id in student_ids]
    except ValueError:
        flash('Invalid student selection.', 'danger')
        return redirect(url_for('main.students'))

    # Fetch all selected students
    students = Student.query.filter(Student.id.in_(student_ids)).all()
    if not students:
        flash('No valid students found.', 'warning')
        return redirect(url_for('main.students'))

    # --- Permission checks ---
    user = current_user
    if user.role == 'admin':
        # Admin can delete any students
        pass
    elif user.role == 'principal':
        # Principal can only delete students in their school
        students = [s for s in students if s.school_id == user.school_id]
        if not students:
            flash('You can only delete students from your own school.', 'danger')
            return redirect(url_for('main.students'))
    elif user.role == 'teacher':
        # Teacher can only delete students in their grade and school
        students = [s for s in students if s.school_id == user.school_id and s.grade == user.grade]
        if not students:
            flash('You can only delete students from your assigned grade.', 'danger')
            return redirect(url_for('main.students'))
    else:
        abort(403)

    # --- Perform deletion ---
    deleted_count = 0
    for student in students:
        # Delete marks first
        Mark.query.filter_by(student_id=student.id).delete()
        db.session.delete(student)
        deleted_count += 1

    db.session.commit()
    flash(f'{deleted_count} student(s) deleted successfully.', 'success')

    # Preserve filters and redirect back
    redirect_params = {k: v for k, v in request.args.items() if k in ('grade', 'school_id', 'term', 'year')}
    return redirect(url_for('main.students', **redirect_params))

@main_bp.route('/student/<int:student_id>')
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
    data = [{"subject": r.subject, "score": r.score, "term": r.term, "year": r.year} for r in results]
    terms_years = db.session.query(Mark.term, Mark.year).filter(Mark.student_id == student_id).distinct().all()
    return render_template('student_profile.html', student=student, data=data,
                           terms_years=terms_years, selected_term=term, selected_year=year)


# ---------- Subjects ----------
@main_bp.route('/subjects')
@login_required
def subjects():
    # Read grade from request
    grade = request.args.get('grade')
    updates = {}
    if 'grade' in request.args:
        updates['grade'] = grade or ''
    if updates:
        merge_preferences(updates)

    # Load saved or fallback
    saved = get_preference('global_filters', {})
    selected_grade = grade or saved.get('grade', 'Grade 1')

    subjects_list = Subject.query.filter_by(grade=selected_grade).all() if selected_grade else Subject.query.all()

    return render_template('subjects.html',
                           subjects=subjects_list,
                           grade=selected_grade,   # used in template
                           all_grades=ALL_GRADES)
    
@main_bp.route('/add_subject', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def add_subject():
    if request.method == 'POST':
        name = request.form['name']
        grade = request.form['grade']
        db.session.add(Subject(name=name, grade=grade))
        db.session.commit()
        flash('Subject added.', 'success')

        return redirect(url_for('main.subjects', grade=grade))
    return render_template('add_subject.html')


@main_bp.route('/edit_subject/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_subject(id):
    subject = Subject.query.get_or_404(id)
    if request.method == 'POST':
        subject.name = request.form['name']
        db.session.commit()
        flash('Subject updated.', 'success')
        # Preserve grade filter
        redirect_params = {k: v for k, v in request.args.items() if k == 'grade'}
        return redirect(url_for('main.subjects', **redirect_params))
    return render_template('edit_subject.html', subject=subject)

@main_bp.route('/delete_subject/<int:id>')
@login_required
@role_required('admin')
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    Mark.query.filter(Mark.subject_id == subject.id).delete()
    db.session.delete(subject)
    db.session.commit()
    flash('Subject deleted.', 'success')
    # Preserve grade filter
    redirect_params = {k: v for k, v in request.args.items() if k == 'grade'}
    return redirect(url_for('main.subjects', **redirect_params))


# ---------- School Dashboard ----------
@main_bp.route('/school_dashboard')
@login_required
def school_dashboard():
    if current_user.role not in ['principal', 'admin', 'teacher']:
        abort(403)
    if current_user.role == 'admin':
        school_id = request.args.get('school_id')
        if not school_id:
            flash('Please select a school from the list below.', 'info')
            return redirect(url_for('main.schools'))
        school = School.query.get_or_404(int(school_id))
    else:
        school_id = current_user.school_id
        school = School.query.get(school_id)

    grades = ["PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4","Grade 5",
              "Grade 6","Grade 7","Grade 8","Grade 9"]
    grade_counts = {g: Student.query.filter_by(school_id=school.id, grade=g).count() for g in grades}
    return render_template('principal_dashboard.html', school=school,
                           grades=grades, grade_counts=grade_counts)


# ---------- CSV Upload ----------
@main_bp.route('/upload_csv', methods=['GET', 'POST'])
@login_required
def upload_csv():
    if current_user.role not in ['admin', 'principal', 'teacher']:
        abort(403)

    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(request.url)

        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)

        if not file.filename.lower().endswith('.csv'):
            flash('Only CSV files are allowed.', 'danger')
            return redirect(request.url)

        try:
            stream = io.StringIO(file.stream.read().decode('utf-8'))
            csv_reader = csv.DictReader(stream)
        except Exception as e:
            flash(f'Error reading CSV: {str(e)}', 'danger')
            return redirect(request.url)

        required_headers = {'name', 'grade'}
        if not required_headers.issubset(csv_reader.fieldnames):
            flash('CSV must contain at least "name" and "grade" columns.', 'danger')
            return redirect(request.url)

        if current_user.role == 'admin':
            school_id = request.form.get('school_id')
            if not school_id:
                flash('Please select a school for the upload.', 'danger')
                return redirect(request.url)
        else:
            school_id = current_user.school_id

        # ---- PRE-LOAD all subjects once ----
        all_subjects = Subject.query.all()
        subjects_by_grade = {}
        for sub in all_subjects:
            subjects_by_grade.setdefault(sub.grade, []).append((sub.name, sub.id))
        # Convert to dict for O(1) lookup: grade -> {subject_name: subject_id}
        subjects_dict_by_grade = {
            g: {name: id for name, id in lst}
            for g, lst in subjects_by_grade.items()
        }

        # ---- PRE-LOAD existing admission numbers for this school ----
        existing_adms = set()
        if school_id:
            existing = Student.query.with_entities(Student.admission_number)\
                                    .filter_by(school_id=school_id).all()
            existing_adms = {adm[0] for adm in existing}

        school = School.query.get(int(school_id)) if school_id else None

        success_count = 0
        error_rows = []
        marks_to_add = []  # collect marks for bulk insert later

        for idx, row in enumerate(csv_reader, start=2):
            name = row.get('name', '').strip()
            grade = row.get('grade', '').strip()
            if not name or not grade:
                continue

            gender = row.get('gender', 'M').strip().upper()
            if gender not in ('M', 'F'):
                gender = 'M'

            adm = row.get('admission_number', '').strip()

            # ---- Admission number generation / validation ----
            if not adm:
                if school:
                    # Auto‑generate: find highest existing number for this school
                    last = Student.query.filter(
                        Student.admission_number.like(f'{school.entry}-%')
                    ).order_by(Student.id.desc()).first()
                    next_num = 1
                    if last:
                        try:
                            next_num = int(last.admission_number.split('-')[-1]) + 1
                        except:
                            next_num = 1
                    adm = f"{school.entry}-ADM-{next_num:04d}"
                else:
                    adm = f"ADM-{uuid.uuid4().hex[:6].upper()}"
            else:
                # Check uniqueness (global or per-school – we use global set)
                if adm in existing_adms:
                    error_rows.append(f'Row {idx}: admission number "{adm}" already exists.')
                    continue
                existing_adms.add(adm)   # mark as used for subsequent rows

            # ---- Create student ----
            student = Student(
                name=name,
                grade=grade,
                gender=gender,
                admission_number=adm,
                school_id=school_id
            )
            db.session.add(student)
            db.session.flush()   # get student.id for marks

            # ---- Process marks (using pre‑loaded subject dict) ----
            term = request.form.get('term')
            year = request.form.get('year')
            try:
                year = int(year) if year else None
            except ValueError:
                error_rows.append('Invalid year, marks not saved.')
                year = None

            subject_dict = subjects_dict_by_grade.get(grade, {})
            for col, value in row.items():
                if col in ['name', 'grade', 'gender', 'admission_number'] or not value.strip():
                    continue
                subj_id = subject_dict.get(col)
                if not subj_id:
                    error_rows.append(f'Row {idx}: subject "{col}" not found for {grade}.')
                    continue
                try:
                    score = float(value)
                    if not (0 <= score <= 100):
                        error_rows.append(f'Row {idx}: score for {col} out of range (0-100).')
                        continue
                except ValueError:
                    error_rows.append(f'Row {idx}: score for {col} not a number.')
                    continue

                if term and year is not None:
                    marks_to_add.append(Mark(
                        student_id=student.id,
                        subject_id=subj_id,
                        score=score,
                        term=term,
                        year=year,
                        cbc_level=cbc_grade(score)
                    ))

            success_count += 1

        # ---- Bulk insert marks ----
        if marks_to_add:
            db.session.bulk_save_objects(marks_to_add)

        try:
            db.session.commit()
            flash(f'{success_count} student(s) imported successfully.', 'success')
            if error_rows:
                flash('Some errors occurred: ' + '; '.join(error_rows), 'warning')
        except Exception as e:
            db.session.rollback()
            flash(f'Database error: {str(e)}', 'danger')
            return redirect(request.url)

        return redirect(url_for('main.upload_csv'))

    schools = School.query.all() if current_user.role == 'admin' else []
    return render_template('upload_csv.html', schools=schools)


# # ---------- Timetable ----------
# @main_bp.route('/timetable', methods=['GET', 'POST'])
# @login_required
# def timetable_page():
#     if current_user.role not in ['admin', 'principal']:
#         abort(403)

#     if request.method == 'POST':
#         if 'subjects_file' in request.files and 'alloc_file' in request.files:
#             subj_file = request.files['subjects_file']
#             alloc_file = request.files['alloc_file']
#             if subj_file.filename == '' or alloc_file.filename == '':
#                 flash('Both files are required.', 'danger')
#                 return redirect(url_for('main.timetable_page'))
#             if not subj_file.filename.endswith('.csv') or not alloc_file.filename.endswith('.csv'):
#                 flash('Only CSV files are allowed.', 'danger')
#                 return redirect(url_for('main.timetable_page'))

#             try:
#                 subs_df = pd.read_csv(subj_file)
#                 alloc_df = pd.read_csv(alloc_file)
#             except Exception as e:
#                 flash(f'Error reading CSV: {str(e)}', 'danger')
#                 return redirect(url_for('main.timetable_page'))

#             selected_grades = request.form.getlist('grades')
#             if not selected_grades:
#                 flash('Please select at least one grade.', 'danger')
#                 return redirect(url_for('main.timetable_page'))

#             try:
#                 timetable_df = generate_timetable(subs_df, alloc_df, grades=selected_grades)
#             except Exception as e:
#                 flash(f'Error: {str(e)}', 'danger')
#                 return redirect(url_for('main.timetable_page'))

#             output = io.BytesIO()
#             with pd.ExcelWriter(output, engine='openpyxl') as writer:
#                 timetable_df.to_excel(writer, sheet_name='Timetable', index=False)
#             output.seek(0)
#             return send_file(output, download_name='timetable.xlsx',
#                              as_attachment=True,
#                              mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

#         if 'download_subjects_template' in request.form or 'download_alloc_template' in request.form:
#             selected_grades = request.form.getlist('grades')
#             if not selected_grades:
#                 flash('Please select at least one grade.', 'warning')
#                 return redirect(url_for('main.timetable_page'))

#             if 'download_subjects_template' in request.form:
#                 df = generate_subjects_template(selected_grades)
#                 filename = 'subjects_template.csv'
#             else:
#                 df = generate_allocation_template(selected_grades)
#                 filename = 'allocation_template.csv'

#             output = io.BytesIO()
#             df.to_csv(output, index=False)
#             output.seek(0)
#             return send_file(output, download_name=filename,
#                              as_attachment=True, mimetype='text/csv')

#         flash('Invalid action.', 'danger')
#         return redirect(url_for('main.timetable_page'))

#     all_grades = ["PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4","Grade 5",
#                   "Grade 6","Grade 7","Grade 8","Grade 9"]
#     return render_template('timetable.html', all_grades=all_grades)


@main_bp.route('/analytics')
@login_required
def analytics():
    # 1. Read current request params
    school_id = request.args.get('school_id')
    grade = request.args.get('grade')
    exam = request.args.get('exam')
    year = request.args.get('year')
    term = request.args.get('term')

    # 2. Build updates dict (only keys that exist in request)
    updates = {}
    if 'school_id' in request.args:
        updates['school_id'] = school_id or ''
    if 'grade' in request.args:
        updates['grade'] = grade or ''
    if 'exam' in request.args:
        updates['exam'] = exam or ''
    if 'year' in request.args:
        updates['year'] = year or ''
    if 'term' in request.args:
        updates['term'] = term or ''

    if updates:
        # Merge into global filters (preserves other keys)
        merge_preferences(updates)

    # 3. Load from global preferences (with fallbacks)
    saved = get_preference('global_filters', {})
    school_id = saved.get('school_id', '')
    grade = saved.get('grade', 'Grade 9')
    exam = saved.get('exam', '')
    year = saved.get('year', '')
    term = saved.get('term', '')

    # 4. Render
    schools = School.query.all()
    grades = ALL_GRADES
    return render_template('analytics.html',
                           schools=schools,
                           grades=grades,
                           selected_school_id=school_id,
                           selected_grade=grade,
                           selected_exam=exam,
                           selected_year=year,
                           selected_term=term)

@main_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = current_user._get_current_object()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'change_username':
            new_username = request.form.get('username', '').strip()
            if new_username and new_username != user.username:
                existing = User.query.filter_by(username=new_username).first()
                if existing:
                    flash('Username already taken.', 'danger')
                    return redirect(url_for('main.profile'))
                user.username = new_username
                db.session.commit()
                flash('Username updated.', 'success')
                return redirect(url_for('main.profile'))

        elif action == 'change_password':
            new_password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            if not new_password:
                flash('Password cannot be empty.', 'danger')
                return redirect(url_for('main.profile'))
            if new_password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return redirect(url_for('main.profile'))
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Password updated.', 'success')
            return redirect(url_for('main.profile'))

        else:
            flash('Invalid action.', 'danger')
            return redirect(url_for('main.profile'))

    return render_template('profile.html', user=user)