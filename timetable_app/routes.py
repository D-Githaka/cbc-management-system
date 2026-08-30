# timetable_app/routes.py

import pandas as pd
from io import BytesIO
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user

from extensions import db
from .models import TimetableSubject, Teacher, Stream, Allocation, Timetable
from .solver import generate_timetable

bp = Blueprint('timetable', __name__, template_folder='../templates')

# KICD Subject Data (CBC Grades 4-9)
KICD_SUBJECTS = [
    {'name': 'English', 'middle_hours': 5, 'junior_hours': 5},
    {'name': 'Kiswahili', 'middle_hours': 5, 'junior_hours': 4},
    {'name': 'Mathematics', 'middle_hours': 5, 'junior_hours': 5},
    {'name': 'Integrated Science', 'middle_hours': 5, 'junior_hours': 5},
    {'name': 'Social Studies', 'middle_hours': 4, 'junior_hours': 4},
    {'name': 'CRE/HRE/IRE', 'middle_hours': 4, 'junior_hours': 4},
    {'name': 'Pre-Technical Studies', 'middle_hours': 0, 'junior_hours': 4},
    {'name': 'Agriculture', 'middle_hours': 4, 'junior_hours': 4},
    {'name': 'Braille Skills', 'middle_hours': 0, 'junior_hours': 0},
    {'name': 'Creative Arts', 'middle_hours': 5, 'junior_hours': 5},
    {'name': 'Foreign Language', 'middle_hours': 0, 'junior_hours': 0},
]

STEPS = [
    ('Subjects', 'timetable.manage_subjects'),
    ('Hours', 'timetable.manage_hours'),
    ('Streams', 'timetable.manage_streams'),
    ('Teachers', 'timetable.manage_teachers'),
    ('Allocations', 'timetable.manage_allocations'),
    ('Generate', 'timetable.generate'),
]

def get_step_context(current_step_name):
    step_names = [s[0] for s in STEPS]
    idx = step_names.index(current_step_name) if current_step_name in step_names else 0
    prev_url = url_for(STEPS[idx-1][1]) if idx > 0 else None
    next_url = url_for(STEPS[idx+1][1]) if idx < len(STEPS)-1 else None
    return {
        'current_step': current_step_name,
        'current_step_index': idx + 1,  # 1-based for display
        'prev_step_url': prev_url,
        'next_step_url': next_url,
        'total_steps': len(STEPS)
    }

# ---------------------------
# Home / Dashboard
# ---------------------------
@bp.route('/')
@login_required
def index():
    subjects = TimetableSubject.query.order_by(TimetableSubject.name).all()
    grades = [{'level': l} for l in range(4, 10)]           # simple list
    streams = Stream.query.order_by(Stream.grade_level, Stream.stream_name).all()
    teachers = Teacher.query.order_by(Teacher.name).all()
    allocations = Allocation.query.all()
    return render_template('timetable/index.html',
                           subjects=subjects,
                           grades=grades,
                           streams=streams,
                           teachers=teachers,
                           allocations=allocations)

# ---------------------------
# Subject Management (from KICD)
# ---------------------------
@bp.route('/subjects', methods=['GET', 'POST'])
@login_required
def manage_subjects():
    if request.method == 'POST':
        selected = request.form.getlist('selected_subjects')
        # Delete all existing timetable subjects
        TimetableSubject.query.delete()
        for name in selected:
            data = next((s for s in KICD_SUBJECTS if s['name'] == name), None)
            if data:
                db.session.add(TimetableSubject(
                    name=data['name'],
                    middle_hours=data['middle_hours'],
                    junior_hours=data['junior_hours']
                ))
        db.session.commit()
        flash('Subjects updated successfully!', 'success')
        return redirect(url_for('timetable.manage_subjects'))

    current = {s.name for s in TimetableSubject.query.all()}
    context = get_step_context('Subjects')
    context.update({'all_subjects': KICD_SUBJECTS, 'current_subjects': current})
    return render_template('timetable/subjects.html', **context)

# ---------------------------
# Hours Configuration
# ---------------------------
@bp.route('/hours', methods=['GET', 'POST'])
@login_required
def manage_hours():
    if request.method == 'POST':
        subjects = TimetableSubject.query.order_by(TimetableSubject.name).all()
        for subj in subjects:
            middle = int(request.form.get(f'middle_{subj.id}', 0))
            junior = int(request.form.get(f'junior_{subj.id}', 0))
            subj.middle_hours = middle
            subj.junior_hours = junior
        db.session.commit()
        flash('Hours updated successfully!', 'success')
        return redirect(url_for('timetable.manage_hours'))

    subjects = TimetableSubject.query.order_by(TimetableSubject.name).all()
    total_middle = sum(s.middle_hours for s in subjects)
    total_junior = sum(s.junior_hours for s in subjects)
    context = get_step_context('Hours')
    context.update({
        'subjects': subjects,
        'total_middle': total_middle,
        'total_junior': total_junior
    })
    return render_template('timetable/hours.html', **context)

# ---------------------------
# Streams Management
# ---------------------------
@bp.route('/streams', methods=['GET', 'POST'])
@login_required
def manage_streams():
    if request.method == 'POST':
        Stream.query.delete()
        for grade_level in range(4, 10):
            num = int(request.form.get(f'streams_{grade_level}', 1))
            if num == 1:
                # Single stream – use empty stream_name (no letter suffix)
                db.session.add(Stream(grade_level=grade_level, stream_name=''))
            else:
                # Multiple streams – use A, B, C, ...
                for i in range(1, num + 1):
                    stream_name = chr(64 + i)   # 'A', 'B', ...
                    db.session.add(Stream(grade_level=grade_level, stream_name=stream_name))
        db.session.commit()
        flash('Streams updated successfully!', 'success')
        return redirect(url_for('timetable.manage_streams'))

    streams_data = {}
    for grade_level in range(4, 10):
        streams = Stream.query.filter_by(grade_level=grade_level).order_by(Stream.stream_name).all()
        streams_data[grade_level] = [s.stream_name for s in streams]
    context = get_step_context('Streams')
    context.update({'streams_data': streams_data})
    return render_template('timetable/streams.html', **context)

# ---------------------------
# Teacher Management
# ---------------------------
@bp.route('/teachers', methods=['GET', 'POST'])
@login_required
def manage_teachers():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            name = request.form.get('name')
            code = int(request.form.get('code'))
            if name and code:
                existing = Teacher.query.filter_by(teacher_code=code).first()
                if existing:
                    flash('Teacher code must be unique. Please use a different code.', 'danger')
                else:
                    db.session.add(Teacher(name=name, teacher_code=code))
                    db.session.commit()
                    flash(f'Teacher "{name}" added successfully!', 'success')
        
        elif action == 'edit':
            teacher_id = int(request.form.get('teacher_id'))
            name = request.form.get('name')
            code = int(request.form.get('code'))
            teacher = Teacher.query.get(teacher_id)
            if teacher:
                # Check uniqueness of code (excluding this teacher)
                existing = Teacher.query.filter(Teacher.teacher_code == code, Teacher.id != teacher_id).first()
                if existing:
                    flash('Teacher code must be unique. Please use a different code.', 'danger')
                else:
                    teacher.name = name
                    teacher.teacher_code = code
                    db.session.commit()
                    flash(f'Teacher "{name}" updated successfully!', 'success')
            else:
                flash('Teacher not found.', 'danger')
        
        elif action == 'delete':
            teacher_id = int(request.form.get('teacher_id'))
            Teacher.query.filter_by(id=teacher_id).delete()
            db.session.commit()
            flash('Teacher deleted successfully.', 'success')
        
        return redirect(url_for('timetable.manage_teachers'))

    teachers = Teacher.query.order_by(Teacher.name).all()
    context = get_step_context('Teachers')
    context.update({'teachers': teachers})
    return render_template('timetable/teachers.html', **context)

# ---------------------------
# Teacher Allocations
# ---------------------------
@bp.route('/allocations', methods=['GET', 'POST'])
@login_required
def manage_allocations():
    if request.method == 'POST':
        Allocation.query.delete()
        alloc_data = request.form.getlist('allocations')
        for alloc_str in alloc_data:
            if alloc_str.strip():
                parts = alloc_str.split(',')
                if len(parts) == 3:
                    teacher_id, subject_id, grade_level = parts
                    db.session.add(Allocation(
                        teacher_id=int(teacher_id),
                        subject_id=int(subject_id),
                        grade_level=int(grade_level)
                    ))
        db.session.commit()
        flash('Allocations updated successfully!', 'success')
        return redirect(url_for('timetable.manage_allocations'))

    teachers = Teacher.query.order_by(Teacher.name).all()
    subjects = TimetableSubject.query.order_by(TimetableSubject.name).all()
    grades = [{'level': l} for l in range(4, 10)]
    allocations = Allocation.query.all()

    alloc_set = {(a.teacher_id, a.subject_id, a.grade_level) for a in allocations}

    # Compute teacher loads
    subject_hours = {}
    for subj in subjects:
        for level in range(4, 10):
            hours = subj.junior_hours if level >= 7 else subj.middle_hours
            subject_hours[(subj.id, level)] = hours

    teacher_loads = {}
    for teacher in teachers:
        total = 0
        for alloc in allocations:
            if alloc.teacher_id == teacher.id:
                total += subject_hours.get((alloc.subject_id, alloc.grade_level), 0)
        teacher_loads[teacher.id] = total

    teacher_load_list = [{'name': t.name, 'id': t.id, 'hours': teacher_loads.get(t.id, 0)}
                         for t in teachers]
    teacher_load_list.sort(key=lambda x: x['hours'], reverse=True)

    context = get_step_context('Allocations')
    context.update({
        'teachers': teachers,
        'subjects': subjects,
        'grades': grades,
        'alloc_set': alloc_set,
        'teacher_loads': teacher_load_list
    })
    return render_template('timetable/allocations.html', **context)

# ---------------------------
# Auto Allocation
# ---------------------------
@bp.route('/auto_allocate', methods=['POST'])
@login_required
def auto_allocate():
    teachers = Teacher.query.order_by(Teacher.id).all()
    if not teachers:
        flash('No teachers found. Please add teachers first.', 'danger')
        return redirect(url_for('timetable.manage_allocations'))

    subjects = TimetableSubject.query.order_by(TimetableSubject.name).all()
    if not subjects:
        flash('No subjects found. Please select subjects first.', 'danger')
        return redirect(url_for('timetable.manage_allocations'))

    grades = range(4, 10)

    teacher_load = {t.id: 0 for t in teachers}
    new_allocations = []

    for level in grades:
        is_junior = level >= 7
        for subj in subjects:
            hours = subj.junior_hours if is_junior else subj.middle_hours
            if hours <= 0:
                continue
            min_teacher_id = min(teacher_load, key=teacher_load.get)
            new_allocations.append((min_teacher_id, subj.id, level))
            teacher_load[min_teacher_id] += hours

    Allocation.query.delete()
    for (tid, sid, lev) in new_allocations:
        db.session.add(Allocation(teacher_id=tid, subject_id=sid, grade_level=lev))
    db.session.commit()

    flash(f'Auto‑allocation completed! {len(new_allocations)} assignments created.', 'success')
    return redirect(url_for('timetable.manage_allocations'))

# ---------------------------
# Timetable Generation
# ---------------------------
@bp.route('/generate', methods=['GET', 'POST'])
@login_required
def generate():
    if request.method == 'POST':
        periods_per_day = int(request.form.get('periods', 8))
        num_workers = int(request.form.get('workers', 8))
        core_subjects_str = request.form.get('core_subjects', 'Mathematics,English,Kiswahili,Integrated Science')
        core_subjects = {s.strip().upper() for s in core_subjects_str.split(',')}
        morning_slots_str = request.form.get('morning_slots', '1,2,3,4')
        morning_slots = {int(s) for s in morning_slots_str.split(',')}

        # Build DataFrames (same as before)
        subjects = TimetableSubject.query.all()
        subs_df = pd.DataFrame([{
            'Subject': s.name,
            'MiddleHours': s.middle_hours,
            'JuniorHours': s.junior_hours
        } for s in subjects])

        allocs = Allocation.query.join(Teacher).join(TimetableSubject).all()
        alloc_df = pd.DataFrame([{
            'Teacher': a.teacher.id,
            'Subject': a.subject.name,
            'Level': a.grade_level
        } for a in allocs])

        streams = Stream.query.all()
        streams_per_level = {}
        for st in streams:
            streams_per_level[st.grade_level] = streams_per_level.get(st.grade_level, 0) + 1

        result_df = generate_timetable(
            subs_df=subs_df,
            alloc_df=alloc_df,
            levels=list(range(4, 10)),
            days=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
            core_subjects=core_subjects,
            morning_slots=morning_slots,
            periods_per_day=periods_per_day,
            streams_per_level=streams_per_level,
            num_workers=num_workers
        )

        # Save to DB
        timetable = Timetable(data_json=result_df.to_json(orient='records'))
        db.session.add(timetable)
        db.session.commit()

        # Return Excel download
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            result_df.to_excel(writer, index=False)
        output.seek(0)
        return send_file(
            output,
            download_name=f'timetable_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
            as_attachment=True
        )

    # GET request
    context = get_step_context('Generate')
    return render_template('timetable/timetable.html', **context)

# ---------------------------
# Saved Timetables
# ---------------------------
@bp.route('/saved_timetables')
@login_required
def saved_timetables():
    timetables = Timetable.query.order_by(Timetable.generated_at.desc()).all()
    return render_template('timetable/saved_timetables.html', timetables=timetables)