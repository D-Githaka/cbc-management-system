# Reports blueprint
from flask import Blueprint, render_template, request, abort, send_file
from flask_login import login_required, current_user
from extensions import db
from models import School, Student, Subject, Mark
from sqlalchemy import func
import pandas as pd
import io
from collections import defaultdict

reports_bp = Blueprint('reports', __name__)

# Shared constant
ALL_GRADES = ["PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4","Grade 5",
              "Grade 6","Grade 7","Grade 8","Grade 9"]
TERMS = ["Term 1","Term 2","Term 3"]
EXAMS = ["Exam 1","Exam 2","Exam 3"]


# ====================== SCHOOL REPORTS ======================
@reports_bp.route('/reports/school')
@login_required
def reports_school():
    if current_user.role not in ['admin', 'principal', 'teacher']:
        abort(403)

    selected_term = request.args.get('term', 'Term 1')
    exam = request.args.get('exam')
    selected_year = request.args.get('year')
    top_n = int(request.args.get('top_n', 3))

    # Scoping
    if current_user.role == 'admin':
        school_id = request.args.get('school_id')
    elif current_user.role == 'principal':
        school_id = current_user.school_id
    else:
        school_id = current_user.school_id

    grade_filter = request.args.get('grade')

    # ---- Helper: apply term / year / exam to any Mark query ----
    def apply_filters(query):
        if selected_term:
            query = query.filter(Mark.term == selected_term)
        if selected_year:
            try:
                query = query.filter(Mark.year == int(selected_year))
            except ValueError:
                pass
        if exam:
            query = query.filter(Mark.exam == exam)
        return query

    # ======== ALL SCHOOLS VIEW ========
    if not school_id:
        # Subject list (filtered by grade if selected)
        if grade_filter:
            subjects = sorted({s.name for s in Subject.query.filter_by(grade=grade_filter).all()})
        else:
            subjects = sorted({s.name for s in Subject.query.all()})

        # Subquery: mark → subject, student, school
        marks_subq = db.session.query(
            Mark.student_id, Mark.subject_id, Mark.score,
            Subject.name.label('subject_name'),
            Student.school_id, Student.grade
        ).join(Subject, Mark.subject_id == Subject.id)\
         .join(Student, Mark.student_id == Student.id)

        marks_subq = apply_filters(marks_subq)
        if grade_filter:
            marks_subq = marks_subq.filter(Student.grade == grade_filter)

        marks_subq = marks_subq.subquery()

        # Aggregate per school & subject
        agg = db.session.query(
            School.id.label('school_id'),
            School.name.label('school_name'),
            School.type.label('school_type'),
            marks_subq.c.grade,
            marks_subq.c.subject_name,
            func.avg(marks_subq.c.score).label('avg_score')
        ).join(marks_subq, School.id == marks_subq.c.school_id)\
         .group_by(School.id, marks_subq.c.grade, marks_subq.c.subject_name)

        # Pivot
        school_scores = defaultdict(lambda: defaultdict(float))
        for row in agg.all():
            key = (row.school_id, row.school_name, row.school_type, row.grade)
            school_scores[key][row.subject_name] = round(row.avg_score, 2)

        all_school_rows = []
        for (sid, sname, stype, grade), scores in school_scores.items():
            total = round(sum(scores.values()), 2)
            all_school_rows.append({
                'school_name': sname,
                'school_type': stype,
                'grade': grade,
                'subjects': {subj: scores.get(subj, '-') for subj in subjects},
                'total': total
            })

        all_school_rows.sort(key=lambda r: r['total'], reverse=True)
        for idx, row in enumerate(all_school_rows, start=1):
            row['position'] = idx

        return render_template(
            'school_reports.html',
            all_schools=True,
            all_school_rows=all_school_rows,
            subjects=subjects,
            selected_term=selected_term,
            selected_year=selected_year,
            exam=exam,
            schools=School.query.all() if current_user.role == 'admin' else [],
            grades=ALL_GRADES,
            terms=TERMS,
            exams=EXAMS,
            school_name=None
        )

    # ======== SINGLE SCHOOL VIEW ========
    school = School.query.get_or_404(int(school_id))

    if grade_filter:
        # ---- Student level ----
        students = Student.query.filter_by(
            school_id=school.id, grade=grade_filter
        ).order_by(Student.name).all()
        student_ids = [s.id for s in students]

        marks_query = apply_filters(Mark.query).filter(
            Mark.student_id.in_(student_ids)
        ).join(Subject)

        grade_subjects = Subject.query.filter_by(grade=grade_filter).all()
        subject_names = sorted({s.name for s in grade_subjects})

        student_data = {s.id: {'id': s.id, 'name': s.name, 'gender': s.gender,
                               'scores': {subj: None for subj in subject_names},
                               'total': 0} for s in students}

        for m in marks_query.all():
            if m.subject and m.student_id in student_data:
                student_data[m.student_id]['scores'][m.subject.name] = m.score

        for sd in student_data.values():
            sd['total'] = sum(v for v in sd['scores'].values() if v is not None)

        # Summary rows
        totals_row = {subj: 0 for subj in subject_names}
        counts = {subj: 0 for subj in subject_names}
        for sd in student_data.values():
            for subj, score in sd['scores'].items():
                if score is not None:
                    totals_row[subj] += score
                    counts[subj] += 1
        avg_row = {}
        for subj in subject_names:
            avg_row[subj] = round(totals_row[subj] / counts[subj], 2) if counts[subj] else '-'

        grand_total = sum(totals_row.values())
        student_count = len(students) or 1
        grand_avg = round(grand_total / student_count, 2)

        return render_template(
            'school_reports.html',
            single_school=True,
            school=school,
            student_data=list(student_data.values()),
            subject_names=subject_names,
            totals_row=totals_row,
            avg_row=avg_row,
            grand_total=grand_total,
            grand_avg=grand_avg,
            grade=grade_filter,
            selected_term=selected_term,
            selected_year=selected_year,
            exam=exam,
            top_n=top_n,
            schools=School.query.all() if current_user.role == 'admin' else [],
            grades=ALL_GRADES,
            terms=TERMS,
            exams=EXAMS,
            school_name=school.name
        )

    # ---- No grade selected → grade averages ----
    grade_averages = []
    for g in ALL_GRADES:
        students_in_grade = Student.query.filter_by(school_id=school.id, grade=g).all()
        if not students_in_grade:
            continue
        st_ids = [s.id for s in students_in_grade]
        marks = apply_filters(Mark.query).filter(Mark.student_id.in_(st_ids)).join(Subject).all()
        subj_scores = defaultdict(list)
        for m in marks:
            if m.subject:
                subj_scores[m.subject.name].append(m.score)
        subj_avg = {subj: round(sum(scores)/len(scores), 2) for subj, scores in subj_scores.items()}
        total = round(sum(subj_avg.values()), 2)
        grade_averages.append({'grade': g, 'averages': subj_avg, 'total': total})

    all_subjects = sorted({s for row in grade_averages for s in row['averages']})
    for row in grade_averages:
        for s in all_subjects:
            row['averages'].setdefault(s, '-')
    grade_averages.sort(key=lambda r: r['total'], reverse=True)
    for idx, row in enumerate(grade_averages, start=1):
        row['position'] = idx

    return render_template(
        'school_reports.html',
        single_school=True,
        school=school,
        grade_averages=grade_averages,
        all_subjects=all_subjects,
        selected_term=selected_term,
        selected_year=selected_year,
        exam=exam,
        top_n=top_n,
        schools=School.query.all() if current_user.role == 'admin' else [],
        grades=ALL_GRADES,
        terms=TERMS,
        exams=EXAMS,
        school_name=school.name,
        grade_selected=False
    )


# ====================== EXCEL EXPORT ======================
@reports_bp.route('/reports/school/excel')
@login_required
def reports_school_excel():
    if current_user.role not in ['admin', 'principal', 'teacher']:
        abort(403)

    selected_term = request.args.get('term', 'Term 1')
    exam = request.args.get('exam')
    selected_year = request.args.get('year')
    grade_filter = request.args.get('grade')
    school_id = request.args.get('school_id') if current_user.role == 'admin' else (
        current_user.school_id if current_user.role in ['principal', 'teacher'] else None
    )

    school_name = "All Schools"
    if school_id:
        school = School.query.get(int(school_id))
        if school:
            school_name = school.name

    def apply_filters(query):
        if selected_term:
            query = query.filter(Mark.term == selected_term)
        if selected_year:
            try:
                query = query.filter(Mark.year == int(selected_year))
            except ValueError:
                pass
        if exam:
            query = query.filter(Mark.exam == exam)
        return query

    # ========== ALL SCHOOLS ==========
    if not school_id:
        if grade_filter:
            subjects = sorted({s.name for s in Subject.query.filter_by(grade=grade_filter).all()})
        else:
            subjects = sorted({s.name for s in Subject.query.all()})

        marks_subq = db.session.query(
            Mark.student_id, Mark.subject_id, Mark.score,
            Subject.name.label('subject_name'),
            Student.school_id, Student.grade
        ).join(Subject, Mark.subject_id == Subject.id)\
         .join(Student, Mark.student_id == Student.id)

        marks_subq = apply_filters(marks_subq)
        if grade_filter:
            marks_subq = marks_subq.filter(Student.grade == grade_filter)
        marks_subq = marks_subq.subquery()

        agg = db.session.query(
            School.name.label('school_name'),
            School.type.label('school_type'),
            marks_subq.c.grade,
            marks_subq.c.subject_name,
            func.avg(marks_subq.c.score).label('avg_score')
        ).join(marks_subq, School.id == marks_subq.c.school_id)\
         .group_by(School.name, School.type, marks_subq.c.grade, marks_subq.c.subject_name)

        school_scores = defaultdict(lambda: defaultdict(float))
        for r in agg.all():
            key = (r.school_name, r.school_type, r.grade)
            school_scores[key][r.subject_name] = round(r.avg_score, 2)

        rows = []
        for (sname, stype, grade), scores in school_scores.items():
            total = round(sum(scores.values()), 2)
            rows.append({
                'School': f"{sname} ({stype})",
                'Grade': grade,
                **{subj: scores.get(subj, '-') for subj in subjects},
                'Total': total
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values('Total', ascending=False)
            df['Position'] = df['Total'].rank(method='min', ascending=False).astype(int)
            cols = [c for c in df.columns if c != 'Position'] + ['Position']
            df = df[cols]

    else:
        # ========== SINGLE SCHOOL ==========
        school = School.query.get(int(school_id))
        if not school:
            abort(404)
        school_name = school.name

        if grade_filter:
            students = Student.query.filter_by(school_id=school.id, grade=grade_filter).all()
            student_ids = [s.id for s in students]
            marks_query = apply_filters(Mark.query).filter(Mark.student_id.in_(student_ids))
            grade_subjects = Subject.query.filter_by(grade=grade_filter).all()
            subject_names = sorted({s.name for s in grade_subjects})

            student_data = []
            for s in students:
                row = {'Student': s.name, 'Gender': s.gender}
                total = 0
                for subj in subject_names:
                    mark = marks_query.filter(Mark.subject.has(name=subj), Mark.student_id == s.id).first()
                    score = mark.score if mark else '-'
                    row[subj] = score
                    if isinstance(score, (int, float)):
                        total += score
                row['Total'] = total
                student_data.append(row)
            df = pd.DataFrame(student_data)
            if not df.empty:
                df = df.sort_values('Total', ascending=False)
                df['Position'] = df['Total'].rank(method='min', ascending=False).astype(int)
                cols = [c for c in df.columns if c != 'Position'] + ['Position']
                df = df[cols]
        else:
            grade_averages = []
            all_subjects_set = set()
            for g in ALL_GRADES:
                st_ids = [s.id for s in Student.query.filter_by(school_id=school.id, grade=g).all()]
                if not st_ids:
                    continue
                marks = apply_filters(Mark.query).filter(Mark.student_id.in_(st_ids)).all()
                subj_scores = defaultdict(list)
                for m in marks:
                    if m.subject:
                        subj_scores[m.subject.name].append(m.score)
                averages = {subj: round(sum(scores)/len(scores), 2) for subj, scores in subj_scores.items()}
                all_subjects_set.update(averages.keys())
                total = round(sum(averages.values()), 2)
                grade_averages.append({'Grade': g, 'Total Avg': total, **averages})
            all_subjects = sorted(all_subjects_set)
            for r in grade_averages:
                for s in all_subjects:
                    r.setdefault(s, '-')
            df = pd.DataFrame(grade_averages)
            if not df.empty:
                df = df.sort_values('Total Avg', ascending=False)
                df['Position'] = df['Total Avg'].rank(method='min', ascending=False).astype(int)
                cols = [c for c in df.columns if c != 'Position'] + ['Position']
                df = df[cols]

    # ========== Write Excel ==========
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        workbook = writer.book
        sheet = workbook.create_sheet("Report", 0)
        sheet.cell(row=1, column=1, value="School Name:")
        sheet.cell(row=1, column=2, value=school_name)
        sheet.cell(row=2, column=1, value="Grade:")
        sheet.cell(row=2, column=2, value=grade_filter if grade_filter else "All Grades")
        sheet.cell(row=2, column=3, value="Term:")
        sheet.cell(row=2, column=4, value=selected_term)
        sheet.cell(row=2, column=5, value="Year:")
        sheet.cell(row=2, column=6, value=selected_year if selected_year else "All")
        df.to_excel(writer, sheet_name="Report", startrow=3, index=False)
    output.seek(0)
    return send_file(output, download_name='school_report.xlsx', as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ====================== STUDENT REPORTS ======================
@reports_bp.route('/reports/student')
@login_required
def reports_student():
    if current_user.role not in ['admin', 'principal', 'teacher']:
        abort(403)

    selected_term = request.args.get('term', 'Term 1')
    exam = request.args.get('exam')
    selected_year = request.args.get('year')
    top_n = int(request.args.get('top_n', 3))

    if current_user.role == 'admin':
        school_id = request.args.get('school_id')
        grade = request.args.get('grade', 'Grade 1')
    elif current_user.role == 'principal':
        school_id = current_user.school_id
        grade = request.args.get('grade', 'Grade 1')
    else:
        school_id = current_user.school_id
        grade = current_user.grade

    # ---- Helper: top students by gender and school type ----
    def get_top_students(gender, school_type):
        results = []
        # Base grade list query
        grades_q = db.session.query(Student.grade).join(Mark).join(School).filter(
            Student.gender == gender,
            School.type == school_type
        )
        if school_id:
            grades_q = grades_q.filter(Student.school_id == int(school_id))
        if selected_term:
            grades_q = grades_q.filter(Mark.term == selected_term)
        if selected_year:
            grades_q = grades_q.filter(Mark.year == int(selected_year))
        if exam:
            grades_q = grades_q.filter(Mark.exam == exam)
        if grade:
            grades_q = grades_q.filter(Student.grade == grade)
        grades_list = [g[0] for g in grades_q.distinct().all()]

        for g in grades_list:
            sub = db.session.query(
                Student.id,
                func.sum(Mark.score).label('total_score')
            ).join(Mark).join(School).filter(
                Student.grade == g,
                Student.gender == gender,
                School.type == school_type
            )
            if school_id:
                sub = sub.filter(Student.school_id == int(school_id))
            if selected_term:
                sub = sub.filter(Mark.term == selected_term)
            if selected_year:
                sub = sub.filter(Mark.year == int(selected_year))
            if exam:
                sub = sub.filter(Mark.exam == exam)
            sub = sub.group_by(Student.id).order_by(func.sum(Mark.score).desc()).limit(top_n).subquery()

            rows = db.session.query(
                Student.id.label('student_id'),
                Student.name.label('student_name'),
                Student.grade.label('grade'),
                Student.gender.label('gender'),
                sub.c.total_score
            ).join(sub, Student.id == sub.c.id).all()

            for r in rows:
                results.append({
                    'grade': r.grade,
                    'student_id': r.student_id,
                    'student_name': r.student_name,
                    'gender': r.gender,
                    'total_score': r.total_score
                })
        return results

    top_male_public = get_top_students('M', 'Public')
    top_male_private = get_top_students('M', 'Private')
    top_female_public = get_top_students('F', 'Public')
    top_female_private = get_top_students('F', 'Private')

    # ---- Class Subject Averages ----
    class_avg = db.session.query(
        Subject.name.label('subject_name'),
        func.avg(Mark.score).label('avg_score')
    ).select_from(Mark)\
     .join(Subject, Mark.subject_id == Subject.id)\
     .join(Student, Mark.student_id == Student.id)\
     .join(School, Student.school_id == School.id)

    if selected_term:
        class_avg = class_avg.filter(Mark.term == selected_term)
    if selected_year:
        class_avg = class_avg.filter(Mark.year == int(selected_year))
    if exam:
        class_avg = class_avg.filter(Mark.exam == exam)
    if school_id:
        class_avg = class_avg.filter(Student.school_id == int(school_id))
    if grade:
        class_avg = class_avg.filter(Student.grade == grade)

    class_subject_averages = [
        {'subject_name': r.subject_name, 'avg_score': round(r.avg_score, 2)}
        for r in class_avg.group_by(Subject.name).all()
    ]

    schools = School.query.all() if current_user.role == 'admin' else []
    school_name = None
    if school_id:
        school_obj = School.query.get(int(school_id))
        if school_obj:
            school_name = school_obj.name
    all_students = []
    if school_id and grade:
        all_students = Student.query.filter_by(
            school_id=int(school_id), grade=grade
        ).order_by(Student.name).all()
    return render_template(
        'student_reports.html',
        top_male_public=top_male_public,
        top_male_private=top_male_private,
        top_female_public=top_female_public,
        top_female_private=top_female_private,
        class_subject_averages=class_subject_averages,
        selected_term=selected_term,
        selected_year=selected_year,
        exam=exam,
        top_n=top_n,
        schools=schools,
        grades=ALL_GRADES,
        terms=TERMS,
        exams=EXAMS,
        school_name=school_name,
        grade=grade,
        all_students=all_students
    )

@reports_bp.route('/student/<int:student_id>/term_report')
@login_required
def student_term_report(student_id):
    student = Student.query.get_or_404(student_id)
    school = School.query.get(student.school_id)

    # Permission check
    if current_user.role != 'admin':
        if current_user.school_id != student.school_id:
            abort(403)
        if current_user.role == 'teacher' and current_user.grade != student.grade:
            abort(403)

    term = request.args.get('term', 'Term 1')
    year = request.args.get('year', type=int)
    if not year:
        flash("Year is required.", "danger")
        return redirect(url_for('reports.reports_student'))

    grade = student.grade
    subjects = Subject.query.filter_by(grade=grade).order_by(Subject.name).all()
    subject_names = [s.name for s in subjects]

    # All exams that have at least one mark for this student in the given term/year
    exam_rows = db.session.query(Mark.exam).filter(
        Mark.student_id == student_id,
        Mark.term == term,
        Mark.year == year
    ).distinct().all()
    exams = sorted([e[0] for e in exam_rows if e[0]])

    if not exams:
        flash("No marks found for this term/year.", "info")
        return redirect(url_for('reports.reports_student'))

    # All students in the same school + grade (for ranking)
    all_student_ids = [s.id for s in Student.query.filter_by(
        school_id=student.school_id, grade=grade
    ).all()]

    # ===== Per‑Exam Data =====
    exam_data = []
    for exam in exams:
        # Student's scores
        marks_query = Mark.query.filter(
            Mark.student_id == student_id,
            Mark.term == term,
            Mark.year == year,
            Mark.exam == exam
        ).join(Subject).order_by(Subject.name)
        scores = {}
        total = 0
        for m in marks_query.all():
            scores[m.subject.name] = m.score
            total += m.score

        # Class totals & ranking for this exam
        class_totals = db.session.query(
            Mark.student_id,
            func.sum(Mark.score).label('total_score')
        ).filter(
            Mark.student_id.in_(all_student_ids),
            Mark.term == term,
            Mark.year == year,
            Mark.exam == exam
        ).group_by(Mark.student_id).all()

        sorted_totals = sorted(class_totals, key=lambda x: x.total_score, reverse=True)
        rank = next((i+1 for i, r in enumerate(sorted_totals) if r.student_id == student_id), None)

        exam_data.append({
            'exam': exam,
            'scores': scores,
            'total': total,
            'rank': rank,
            'class_size': len(sorted_totals)
        })

    # ===== Overall Rank (by average total) =====
    overall_totals = []
    for sid in all_student_ids:
        totals = []
        for exam in exams:
            t = db.session.query(func.sum(Mark.score)).filter(
                Mark.student_id == sid,
                Mark.term == term,
                Mark.year == year,
                Mark.exam == exam
            ).scalar()
            if t is not None:
                totals.append(t)
        if totals:
            overall_totals.append((sid, sum(totals) / len(totals)))

    overall_totals.sort(key=lambda x: x[1], reverse=True)
    overall_rank = next((i+1 for i, (sid, _) in enumerate(overall_totals) if sid == student_id), None)
    overall_class_size = len(overall_totals)

    avg_total = round(sum(e['total'] for e in exam_data) / len(exam_data), 2) if exam_data else 0

    return render_template(
        'student_term_report.html',
        student=student,
        school=school,
        grade=grade,
        term=term,
        year=year,
        subject_names=subject_names,
        exam_data=exam_data,
        exams=exams,
        avg_total=avg_total,
        overall_rank=overall_rank,
        overall_class_size=overall_class_size
    )