# Marks
from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import School, Student, Subject, Mark
from utils.helpers import cbc_grade
from sqlalchemy import func

marks_bp = Blueprint('marks', __name__)

@marks_bp.route('/marks')
@login_required
def marks():
    # For teachers: show their own submissions
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
        return render_template('marks_teacher.html', submissions=submissions)

    # For admin/principal: existing logic
    schools = School.query.all()
    return render_template('marks.html', schools=schools)

# Enter Marks
@marks_bp.route('/enter_marks', methods=['GET'])
@login_required
def enter_marks():

    grade = request.args.get('grade')
    term = request.args.get('term')
    year = request.args.get('year')
    exam = request.args.get('exam', 'Exam 1')

    # -------------------------
    # ROLE-BASED SCHOOL LOGIC
    # -------------------------
    if current_user.role == "admin":
        school_id = request.args.get('school_id')
        if not school_id:
            flash("Please select a school first.", "warning")
            return redirect(url_for('marks.marks'))
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
            year=year,
            exam=exam
        ).first()

        if existing:
            if existing.status == 'Approved':
                return jsonify({"error": "Cannot edit approved marks."}), 403
            existing.score = score
            existing.cbc_level = grade_level
        else:
            db.session.add(Mark(
                student_id=student.id,
                subject_id=int(subject_id),
                score=score,
                term=term,
                year=year,
                exam=exam,
                cbc_level=grade_level,
                status='Pending',          # <-- NEW
                submitted_by=current_user.id 
            ))

    try:
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500