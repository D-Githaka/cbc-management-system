from flask import Blueprint, render_template, request, abort, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from extensions import db
from models import Mark, Student, School, Subject, User
from sqlalchemy import func
from sqlalchemy.orm import aliased
from datetime import datetime

approvals_bp = Blueprint('approvals', __name__)

@approvals_bp.route('/approvals')
@login_required
def approvals_dashboard():
    if current_user.role not in ['admin', 'principal']:
        abort(403)

    school_id = current_user.school_id if current_user.role == 'principal' else request.args.get('school_id')

    Approver = aliased(User)

    submissions = db.session.query(
        Mark.submitted_by,
        User.username.label('teacher_name'),
        User.school_id.label('teacher_school_id'),
        User.grade.label('teacher_grade'), 
        Student.grade,
        Mark.term,
        Mark.year,
        Mark.exam,
        School.name.label('school_name'),
        func.count(Mark.id).label('mark_count'),
        func.sum(db.case((Mark.status == 'Approved', 1), else_=0)).label('approved_count'),
        func.min(Mark.created_at).label('submitted_at'),
        func.max(Mark.approved_at).label('last_approved_at'),
        func.max(Mark.approved_by).label('approved_by_id'),
        Approver.username.label('approved_by_name')   # now defined
    ).join(Student, Mark.student_id == Student.id)\
     .join(School, Student.school_id == School.id)\
     .join(User, Mark.submitted_by == User.id)\
     .outerjoin(Approver, Mark.approved_by == Approver.id)\
     .filter(Mark.submitted_by.isnot(None))   # backslash before this line ensures continuation

    if school_id:
        submissions = submissions.filter(Student.school_id == int(school_id))

    submissions = submissions.group_by(
        Mark.submitted_by,
        Student.grade,
        Mark.term,
        Mark.year,
        Mark.exam,
        School.name                 # added for SQL compliance
    ).order_by(func.min(Mark.created_at).desc()).all()

    # No separate approver query needed – we already have approved_by_name
    submissions_with_approver = []
    for s in submissions:
        submissions_with_approver.append({
            'submitted_by': s.submitted_by,
            'teacher_name': s.teacher_name,
            'teacher_school_id': s.teacher_school_id,
            'teacher_grade': s.teacher_grade,
            'grade': s.grade,
            'term': s.term,
            'year': s.year,
            'exam': s.exam,
            'school_name': s.school_name,
            'mark_count': s.mark_count,
            'approved_count': s.approved_count,
            'submitted_at': s.submitted_at,
            'approved_at': s.last_approved_at,
            'approved_by_name': s.approved_by_name or '-'
        })

    schools = School.query.all() if current_user.role == 'admin' else []

    return render_template('approvals_dashboard.html',
                           submissions=submissions_with_approver,
                           schools=schools)


@approvals_bp.route('/approvals/view')
@login_required
def view_submission():
    if current_user.role not in ['admin', 'principal']:
        abort(403)

    teacher_id = request.args.get('teacher_id', type=int)
    grade = request.args.get('grade')
    term = request.args.get('term')
    year = request.args.get('year', type=int)
    exam = request.args.get('exam')

    try:
        teacher = User.query.get(teacher_id)
        if not teacher or not teacher.school_id:
            flash("Teacher has no school assigned.", "danger")
            return redirect(url_for('approvals.approvals_dashboard'))

        marks = Mark.query.join(Student).filter(
            Mark.submitted_by == teacher_id,
            Student.grade == grade,
            Mark.term == term,
            Mark.year == year,
            Mark.exam == exam
        ).order_by(Student.name).all()

        students = Student.query.filter_by(grade=grade, school_id=teacher.school_id).all()
        subjects = Subject.query.filter_by(grade=grade).all()

        return render_template('view_submission.html',
                               marks=marks,
                               teacher=teacher,
                               grade=grade,
                               term=term,
                               year=year,
                               exam=exam,
                               students=students,
                               subjects=subjects)
    except Exception as e:
        flash(f"Error loading submission: {e}", "danger")
        return redirect(url_for('approvals.approvals_dashboard'))


@approvals_bp.route('/approvals/approve', methods=['POST'])
@login_required
def approve_submission():
    if current_user.role not in ['admin', 'principal']:
        abort(403)

    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    teacher_id = data.get('teacher_id')
    grade = data.get('grade')
    term = data.get('term')
    year = data.get('year')
    exam = data.get('exam')

    if not all([teacher_id, grade, term, year, exam]):
        return jsonify({"status": "error", "message": "Missing parameters"}), 400

    try:
        # Build subquery for pending marks that match the criteria
        subquery = db.session.query(Mark.id).join(Student).filter(
            Mark.submitted_by == teacher_id,
            Mark.term == term,
            Mark.year == int(year),
            Mark.exam == exam,
            Mark.status == 'Pending',
            Student.grade == grade
        )

        # Principal can only approve marks from their own school
        if current_user.role == 'principal':
            subquery = subquery.filter(Student.school_id == current_user.school_id)

        # Update using a subquery to avoid the join in the update statement
        updated = Mark.query.filter(Mark.id.in_(subquery.subquery())).update({
            'status': 'Approved',
            'approved_by': current_user.id,
            'approved_at': datetime.utcnow()
        }, synchronize_session='fetch')

        db.session.commit()
        return jsonify({'status': 'success', 'count': updated})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@approvals_bp.route('/approvals/delete', methods=['POST'])
@login_required
def delete_submission():
    if current_user.role not in ['admin', 'principal', 'teacher']:
        abort(403)

    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    teacher_id = data.get('teacher_id')
    grade = data.get('grade')
    term = data.get('term')
    year = data.get('year')
    exam = data.get('exam')

    if not all([teacher_id, grade, term, year, exam]):
        return jsonify({"status": "error", "message": "Missing parameters"}), 400

    try:
        # Permission checks
        if current_user.role == 'teacher' and current_user.id != teacher_id:
            return jsonify({"status": "error", "message": "You can only delete your own submissions."}), 403

        # Build subquery for marks to delete
        subquery = db.session.query(Mark.id).join(Student).filter(
            Mark.submitted_by == teacher_id,
            Mark.term == term,
            Mark.year == int(year),
            Mark.exam == exam,
            Student.grade == grade
        )

        # Principal can only delete marks from their own school
        if current_user.role == 'principal':
            subquery = subquery.filter(Student.school_id == current_user.school_id)
        # Admin: no restriction

        # Delete using subquery
        deleted = Mark.query.filter(Mark.id.in_(subquery.subquery())).delete(synchronize_session='fetch')

        db.session.commit()
        return jsonify({'status': 'success', 'count': deleted})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500