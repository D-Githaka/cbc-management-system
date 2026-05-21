from models import db, Subject

def seed_subjects():
    subjects_by_grade = {
        "PP1": ["Language Activities", "Mathematical Activities", "Environmental Activities"],
        # ... rest of your mapping
        "Grade 9": ["Math", "English", "Kiswahili", "Physics", "Chemistry", "Biology"]
    }
    if Subject.query.count() == 0:
        for grade, subjects in subjects_by_grade.items():
            for s in subjects:
                db.session.add(Subject(name=s, grade=grade))
        db.session.commit()