import pandas as pd
from ortools.sat.python import cp_model


def generate_timetable(subs_df, alloc_df, levels, days, core_subjects, morning_slots,
                       periods_per_day=8, streams_per_level=None, num_workers=8):
    if streams_per_level is None:
        streams_per_level = {l: 1 for l in levels}

    # ---- Build grade strings ----
    grades = []
    for level in levels:
        num_streams = streams_per_level.get(level, 1)
        if num_streams == 1:
            grades.append(f"Grade {level}")
        else:
            for stream in range(1, num_streams + 1):
                stream_char = chr(64 + stream)
                grades.append(f"Grade {level}{stream_char}")

    SLOTS = list(range(1, periods_per_day + 1))
    CORE_SUBJECTS = set(core_subjects)
    MORNING_SLOTS = set(morning_slots)

    # Clean data
    subs_df = subs_df.copy()
    alloc_df = alloc_df.copy()
    subs_df['Subject'] = subs_df['Subject'].str.strip().str.upper()
    alloc_df['Subject'] = alloc_df['Subject'].str.strip().str.upper()

    # ---- Teacher map: (grade_string, subject) -> teacher_id ----
    teach_map = {}
    for _, row in alloc_df.iterrows():
        level = int(row['Level'])
        subject = row['Subject']
        teacher = int(row['Teacher'])
        num_streams = streams_per_level.get(level, 1)
        if num_streams == 1:
            g = f"Grade {level}"
            teach_map[(g, subject)] = teacher
        else:
            for stream in range(1, num_streams + 1):
                stream_char = chr(64 + stream)
                g = f"Grade {level}{stream_char}"
                teach_map[(g, subject)] = teacher

    # ---- Subject hours ----
    hours_dict = {}
    for g in grades:
        # Extract level from grade string (handles both "Grade 4" and "Grade 4A")
        parts = g.split()
        level_str = parts[1]
        if level_str[-1].isalpha():
            level = int(level_str[:-1])   # remove trailing letter
        else:
            level = int(level_str)
        for _, row in subs_df.iterrows():
            subj = row['Subject']
            hours = int(row['JuniorHours'] if level >= 7 else row['MiddleHours'])
            if hours > 0:
                hours_dict[(g, subj)] = hours

    subjects = subs_df['Subject'].tolist()
    if 'FREE' not in subjects:
        subjects.append('FREE')

    # Sanity check
    for g in grades:
        total = sum(hours_dict.get((g, s), 0) for s in subjects if s != 'FREE')
        max_slots = len(days) * periods_per_day
        if total > max_slots:
            raise RuntimeError(
                f"Grade {g}: total hours ({total}) exceeds {max_slots} available slots."
            )

    # ---- CP-SAT model ----
    model = cp_model.CpModel()
    X = {}
    for g in grades:
        for d in days:
            for s in SLOTS:
                for subj in subjects:
                    X[(g, d, s, subj)] = model.NewBoolVar(f"x_{g}_{d}_{s}_{subj}")

    # 1. Exactly one subject per slot
    for g in grades:
        for d in days:
            for s in SLOTS:
                model.AddExactlyOne(X[(g, d, s, subj)] for subj in subjects)

    # 2. Teacher non-clash
    all_teachers = alloc_df['Teacher'].unique()
    for d in days:
        for s in SLOTS:
            for t in all_teachers:
                teaches = []
                for g in grades:
                    for subj in subjects:
                        if subj == 'FREE':
                            continue
                        key = (g, subj)
                        if key in teach_map and teach_map[key] == int(t):
                            teaches.append(X[(g, d, s, subj)])
                if teaches:
                    model.Add(sum(teaches) <= 1)

    # 3. Weekly hours (exact with slack)
    for g in grades:
        for subj in subjects:
            if subj == 'FREE':
                continue
            target = hours_dict.get((g, subj), 0)
            vars_ = [X[(g, d, s, subj)] for d in days for s in SLOTS]
            if target == 0:
                for v in vars_:
                    model.Add(v == 0)
                continue
            slack = model.NewIntVar(0, target, f"slack_{g}_{subj}")
            model.Add(sum(vars_) + slack == target)

    # 4. Only subjects that have a teacher
    for g in grades:
        for d in days:
            for s in SLOTS:
                for subj in subjects:
                    if subj != 'FREE' and (g, subj) not in teach_map:
                        model.Add(X[(g, d, s, subj)] == 0)

    # 5. Daily limit: core can have 2, others 1
    for g in grades:
        for d in days:
            for subj in subjects:
                if subj == 'FREE':
                    continue
                daily_vars = [X[(g, d, s, subj)] for s in SLOTS]
                if subj in CORE_SUBJECTS:
                    model.Add(sum(daily_vars) <= 2)
                else:
                    model.Add(sum(daily_vars) <= 1)

    # ---- Objective ----
    penalties = []
    for g in grades:
        for d in days:
            for s in SLOTS:
                penalties.append(X[(g, d, s, 'FREE')] * 10)
                if s not in MORNING_SLOTS:
                    for subj in CORE_SUBJECTS:
                        if subj in subjects:
                            penalties.append(X[(g, d, s, subj)] * 1)

    # Friday slot 1 free for assembly
    for g in grades:
        parts = g.split()
        level_str = parts[1]
        if level_str[-1].isalpha():
            level = int(level_str[:-1])
        else:
            level = int(level_str)
        if level >= 4:
            for subj in subjects:
                if subj != 'FREE':
                    penalties.append(X[(g, 'Friday', 1, subj)] * 100)

    model.Minimize(sum(penalties))

    # ---- Solve ----
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.num_search_workers = num_workers
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("No feasible timetable found – check subject hours or teacher allocation.")

    # ---- Build result ----
    rows = []
    for d in days:
        for g in grades:
            row = {'Day': d, 'Grade': g}
            for s in SLOTS:
                assigned = 'FREE'
                for subj in subjects:
                    if solver.Value(X[(g, d, s, subj)]):
                        if subj == 'FREE':
                            assigned = 'FREE'
                        else:
                            teacher = teach_map.get((g, subj), 'N/A')
                            assigned = f'{subj} (T{teacher})'
                        break
                row[f'Slot {s}'] = assigned
            rows.append(row)
    return pd.DataFrame(rows)