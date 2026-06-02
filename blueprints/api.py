from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import School, Student, Subject, Mark
from sqlalchemy import func
from utils.helpers import cbc_grade
from extensions import db, cache

api_bp = Blueprint('api', __name__)

@api_bp.route('/api/analytics')
@login_required
@cache.cached(timeout=900, query_string=True)
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
        grade = request.args.get('grade')

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

@api_bp.route('/api/grades')
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

@api_bp.route('/api/students')
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

@api_bp.route('/api/school_overview')
@login_required
@cache.cached(timeout=900, query_string=True)
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

@api_bp.route('/api/add_student_with_marks', methods=['POST'])
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

@api_bp.route('/api/school_comparison')
@login_required
def school_comparison():
    grade = request.args.get('grade')
    year = request.args.get('year')
    term = request.args.get('term')
    exam = request.args.get('exam')
    selected_school_id = request.args.get('school_id')   # optional, to highlight

    if not grade:
        return jsonify({"error": "grade is required"}), 400

    query = db.session.query(
        School.id.label('school_id'),
        School.name.label('school_name'),
        func.avg(Mark.score).label('avg_score')
    ).select_from(Mark)\
     .join(Student, Mark.student_id == Student.id)\
     .join(School, Student.school_id == School.id)\
     .filter(Student.grade == grade)

    if term:
        query = query.filter(Mark.term == term)
    if year:
        try:
            query = query.filter(Mark.year == int(year))
        except ValueError:
            pass
    if exam:
        query = query.filter(Mark.exam == exam)

    results = query.group_by(School.id, School.name).all()

    data = [
        {
            "school_id": r.school_id,
            "school_name": r.school_name,
            "avg_score": round(r.avg_score, 2),
        }
        for r in results
    ]

    # Sort by average score descending
    data.sort(key=lambda x: x['avg_score'], reverse=True)

    return jsonify({"data": data, "selected_school_id": selected_school_id})