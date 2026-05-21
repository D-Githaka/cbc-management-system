import pandas as pd
from ortools.sat.python import cp_model

def _parse_level(raw):
    """Convert a Level value (e.g. 'PP1','grade 1','3') to a list of grade strings used in the model."""
    raw = str(raw).strip().lower()
    # PP1 / PP2
    if raw in ["pp1", "pp2"]:
        return [raw.upper()]                     # "PP1", "PP2"
    # "Grade 1" … "Grade 9"
    if raw.startswith("grade"):
        try:
            num = int(raw[5:].strip())
            if 1 <= num <= 9:
                return [f"Grade {num}"]
        except:
            pass
    # Plain number 1‑9
    if raw.isdigit():
        num = int(raw)
        if 1 <= num <= 9:
            return [f"Grade {num}"]
    raise ValueError(f"Cannot interpret Level value: '{raw}'")


def generate_timetable(subs_df, alloc_df, grades=None):
    """
    subs_df : DataFrame with column 'Subject' and one column per grade (e.g. 'PP1','Grade 1', …)
              holding weekly hours.
    alloc_df: DataFrame with columns Level, Subject, Teacher (teacher name or numeric ID).
    grades  : list of grade strings to include, e.g. ['PP1','Grade 1','Grade 4'].
    """
    if not grades:
        raise ValueError("At least one grade must be selected.")

    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    SLOTS = list(range(1, 9))               # 8 periods/day
    CORE_SUBJECTS = {'MATHS', 'ENG', 'KISW'}
    MORNING_SLOTS = {1, 2, 3, 4}

    # Clean up column names / string columns
    subs_df = subs_df.copy()
    alloc_df = alloc_df.copy()
    subs_df.columns = subs_df.columns.str.strip()
    alloc_df.columns = alloc_df.columns.str.strip()
    subs_df['Subject'] = subs_df['Subject'].str.strip()
    alloc_df['Subject'] = alloc_df['Subject'].str.strip()

    # ---- Auto‑assign numeric teacher IDs if names are given ----
    if not pd.api.types.is_numeric_dtype(alloc_df['Teacher']):
        unique = alloc_df['Teacher'].unique()
        mapping = {name: i + 1 for i, name in enumerate(unique)}
        alloc_df['Teacher'] = alloc_df['Teacher'].map(mapping)

    # ---- Build teacher map: (grade_string, subject) → teacher ID ----
    teach_map = {}
    for _, r in alloc_df.iterrows():
        try:
            levels = _parse_level(r['Level'])
        except ValueError:
            continue
        for g in levels:
            if g in grades:
                teach_map[(g, r['Subject'])] = int(r['Teacher'])

    # ---- Read subject hours from the grade columns ----
    hours_dict = {}
    for g in grades:
        col = g if g in subs_df.columns else None
        if col is None:
            hrs_series = pd.Series(0, index=subs_df.index)
        else:
            hrs_series = pd.to_numeric(subs_df[col], errors='coerce').fillna(0).astype(int)
        for idx, row in subs_df.iterrows():
            subj = row['Subject']
            h = int(hrs_series[idx])
            if h > 0:
                hours_dict[(g, subj)] = h

    subjects = subs_df['Subject'].tolist()
    if 'Free' not in subjects:
        subjects.append('Free')

    # Quick total‑hours sanity check
    for g in grades:
        total = sum(hours_dict.get((g, s), 0) for s in subjects if s != 'Free')
        if total > 40:
            raise RuntimeError(
                f"Grade {g}: total hours ({total}) exceeds 40 available slots."
            )

    # ---- CP‑SAT Model ----
    model = cp_model.CpModel()
    X = {}
    for g in grades:
        for d in DAYS:
            for s in SLOTS:
                for subj in subjects:
                    X[(g, d, s, subj)] = model.NewBoolVar(f"x_{g}_{d}_{s}_{subj}")

    # 1. Exactly one subject per grade per slot
    for g in grades:
        for d in DAYS:
            for s in SLOTS:
                model.AddExactlyOne(X[(g, d, s, subj)] for subj in subjects)

    # 2. Teacher non‑clash
    all_teachers = alloc_df['Teacher'].unique()
    for d in DAYS:
        for s in SLOTS:
            for t in all_teachers:
                teaches = []
                for g in grades:
                    for subj in subjects:
                        if subj == 'Free':
                            continue
                        key = (g, subj)
                        if key in teach_map and teach_map[key] == int(t):
                            teaches.append(X[(g, d, s, subj)])
                if teaches:
                    model.Add(sum(teaches) <= 1)

    # 3. Weekly hours (exact, with slack for missing hours)
    for g in grades:
        for subj in subjects:
            if subj == 'Free':
                continue
            target = hours_dict.get((g, subj), 0)
            vars_ = [X[(g, d, s, subj)] for d in DAYS for s in SLOTS]
            if target == 0:
                # subject not offered to this grade → never appear
                for v in vars_:
                    model.Add(v == 0)
                continue
            slack = model.NewIntVar(0, target, f"slack_{g}_{subj}")
            model.Add(sum(vars_) + slack == target)

    # 4. Only allow subjects that have a teacher for the grade
    for g in grades:
        for d in DAYS:
            for s in SLOTS:
                for subj in subjects:
                    if subj != 'Free' and (g, subj) not in teach_map:
                        model.Add(X[(g, d, s, subj)] == 0)

    # 5. At most one lesson of the same subject per day per grade
    for g in grades:
        for d in DAYS:
            for subj in subjects:
                if subj == 'Free':
                    continue
                model.Add(sum(X[(g, d, s, subj)] for s in SLOTS) <= 1)

    # ---- Objective ----
    penalties = []
    for g in grades:
        for d in DAYS:
            for s in SLOTS:
                # strong penalty for free slots
                penalties.append(X[(g, d, s, 'Free')] * 10)
                # core subjects in afternoon (mild penalty)
                if s not in MORNING_SLOTS:
                    for subj in CORE_SUBJECTS:
                        if subj in subjects:
                            penalties.append(X[(g, d, s, subj)] * 1)

    # Soft constraint: Friday slot 1 should be free for Grades 4‑9 (assembly)
    for g in grades:
        if g.startswith("Grade") and int(g[6:]) >= 4:
            for subj in subjects:
                if subj != 'Free':
                    penalties.append(X[(g, 'Friday', 1, subj)] * 100)

    model.Minimize(sum(penalties))

    # ---- Solve ----
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("No feasible timetable found – check subject hours or teacher allocation.")

    # ---- Build result ----
    rows = []
    for d in DAYS:
        for g in grades:
            row = {'Day': d, 'Grade': g}
            for s in SLOTS:
                assigned = 'Free'
                for subj in subjects:
                    if solver.Value(X[(g, d, s, subj)]):
                        if subj == 'Free':
                            assigned = 'Free'
                        else:
                            teacher = teach_map.get((g, subj), 'N/A')
                            assigned = f'{subj} (T{teacher})'
                        break
                row[f'Slot {s}'] = assigned
            rows.append(row)
    return pd.DataFrame(rows)


def generate_subjects_template(grades):
    """Return a DataFrame with Subject and empty columns for each selected grade."""
    from models import Subject                     # local import to avoid circular dependency
    subjects = Subject.query.filter(Subject.grade.in_(grades)).distinct().all()
    names = sorted({s.name for s in subjects})
    data = {'Subject': names}
    for g in grades:
        data[g] = ''
    return pd.DataFrame(data)


def generate_allocation_template(grades):
    """Return an empty allocation DataFrame with columns Level, Subject, Teacher."""
    return pd.DataFrame(columns=['Level', 'Subject', 'Teacher'])