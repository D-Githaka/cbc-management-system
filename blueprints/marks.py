# Marks
from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import School, Student, Subject, Mark
from utils.helpers import cbc_grade
from utils.preferences import get_preference, merge_preferences
from sqlalchemy import func
from datetime import datetime

marks_bp = Blueprint('marks', __name__)

@marks_bp.route('/marks')
@login_required
def marks():
    # For teachers: show submissions + entry form
    if current_user.role == 'teacher':
        subs = db.session.query(
            Student.grade,
            Mark.term,
            Mark.year,
            Mark.exam,
            func.count(Mark.id).label('total'),
            func.sum(db.case((Mark.status == 'Approved', 1), else_=0)).label('approved'),
            func.min(Mark.created_at).label('submitted_at')
        ).join(Student, Mark.student_id == Student.id)\
         .filter(Mark.submitted_by == current_user.id)\
         .group_by(Student.grade, Mark.term, Mark.year, Mark.exam)\
         .all()

        submissions = []
        for row in subs:
            submissions.append({
                'grade': row.grade,
                'term': row.term,
                'year': row.year,
                'exam': row.exam,
                'total': row.total,
                'approved': row.approved,
                'status': 'Approved' if row.approved == row.total else 'Pending',
                'submitted_at': row.submitted_at
            })

        # Reuse the same template, but mark teacher and pre‑fill school/grade
        teacher_school = School.query.get(current_user.school_id)
        return render_template(
            'marks.html',
            schools=[],                          # not used for teacher
            is_teacher=True,
            teacher_school=teacher_school,
            teacher_grade=current_user.grade,
            submissions=submissions
        )

    # Admin / Principal: existing logic
    school_id = request.args.get('school_id')
    grade = request.args.get('grade')
    term = request.args.get('term')
    year = request.args.get('year')
    exam = request.args.get('exam')

    updates = {}
    if 'school_id' in request.args:
        updates['school_id'] = school_id or ''
    if 'grade' in request.args:
        updates['grade'] = grade or ''
    if 'term' in request.args:
        updates['term'] = term or ''
    if 'year' in request.args:
        updates['year'] = year or ''
    if 'exam' in request.args:
        updates['exam'] = exam or ''

    if updates:
        merge_preferences(updates)

    saved = get_preference('global_filters', {})

    if current_user.role == 'principal':
        school_id = current_user.school_id
        grade = saved.get('grade', 'Grade 1')
        schools = [School.query.get(school_id)] if school_id else []
    else:  # admin
        schools = School.query.all()
        # Use saved school_id if exists, else default to first school
        school_id = saved.get('school_id')
        if not school_id and schools:
            school_id = schools[0].id
        else:
            school_id = int(school_id) if school_id else None
        grade = saved.get('grade', 'Grade 1')

    term = saved.get('term', 'Term 1')
    year = saved.get('year', str(datetime.now().year))
    exam = saved.get('exam', 'Exam 1')
    
    schools = School.query.all() if current_user.role == 'admin' else [School.query.get(school_id)]
    return render_template('marks.html',
                           schools=schools,
                           is_teacher=False,
                           selected_school_id=school_id,
                           selected_grade=grade,
                           selected_term=term,
                           selected_year=year,
                           selected_exam=exam)
# Enter Marks
@marks_bp.route('/enter_marks', methods=['GET'])
@login_required
def enter_marks():
    # Read params
    school_id = request.args.get('school_id')
    grade = request.args.get('grade')
    term = request.args.get('term')
    year = request.args.get('year')
    exam = request.args.get('exam', 'Exam 1')

    # Save any filter that is present
    updates = {}
    if 'school_id' in request.args:
        updates['school_id'] = school_id or ''
    if 'grade' in request.args:
        updates['grade'] = grade or ''
    if 'term' in request.args:
        updates['term'] = term or ''
    if 'year' in request.args:
        updates['year'] = year or ''
    if 'exam' in request.args:
        updates['exam'] = exam or ''

    if updates:
        merge_preferences(updates)

    # Load saved (if no params provided)
    saved = get_preference('global_filters', {})
    # Use request values if present, else saved
    school_id = school_id or saved.get('school_id')
    grade = grade or saved.get('grade')
    term = term or saved.get('term', 'Term 1')
    year = year or saved.get('year', str(datetime.now().year))
    exam = exam or saved.get('exam', 'Exam 1')

    # Role overrides
    if current_user.role == 'teacher':
        school_id = current_user.school_id
        grade = current_user.grade
    elif current_user.role == 'principal':
        school_id = current_user.school_id
        # grade may be None, fallback to saved or Grade 1
        grade = grade or saved.get('grade', 'Grade 1')
    else:  # admin
        # ensure school_id is set
        if not school_id:
            flash("Please select a school first.", "warning")
            return redirect(url_for('marks.marks'))

    # Validate school
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
                Mark.year == year,
                Mark.exam == exam
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
        exam = exam,
        year=year,
        students=students,
        subjects=subjects,
        marks_dict=marks_dict
    )

#Save Marks
@marks_bp.route('/save_marks', methods=['POST'])
@login_required
def save_marks():
    data = request.json
    student_id = data['student_id']
    term = data['term']
    year = data['year']
    marks = data['marks']
    exam = data.get('exam', 'Exam 1')

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

    # ---- Fetch existing marks for this student, term, year, exam ONCE ----
    existing_marks = Mark.query.filter_by(
        student_id=student_id,
        term=term,
        year=year,
        exam=exam
    ).all()
    existing_dict = {m.subject_id: m for m in existing_marks}   # key by subject_id

    # Prepare list of new marks to add (for bulk insert)
    new_marks = []

    for subject_id_str, score in marks.items():
        subject_id = int(subject_id_str)

        # Validate score
        try:
            score = float(score)
        except ValueError:
            return jsonify({"error": "Invalid score"}), 400
        if score < 0 or score > 100:
            return jsonify({"error": "Score out of range"}), 400

        # Validate subject
        subject = Subject.query.get(subject_id)
        if not subject or subject.grade != student.grade:
            return jsonify({"error": f"Subject #{subject_id} not valid for this student"}), 400

        grade_level = cbc_grade(score)

        if subject_id in existing_dict:
            # Update existing mark
            mark = existing_dict[subject_id]
            mark.score = score
            mark.cbc_level = grade_level
            mark.status = 'Pending'          # reset approval status on edit
            # Optionally update submitted_by to current user
            mark.submitted_by = current_user.id
        else:
            # New mark
            new_marks.append(Mark(
                student_id=student.id,
                subject_id=subject_id,
                score=score,
                term=term,
                year=year,
                exam=exam,
                cbc_level=grade_level,
                status='Pending',
                submitted_by=current_user.id
            ))

    # Bulk insert new marks
    if new_marks:
        db.session.bulk_save_objects(new_marks)

    try:
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500