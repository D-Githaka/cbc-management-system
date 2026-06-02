from models import Subject
from extensions import db

def seed_subjects():
    subjects_by_grade = {
        "PP1": ["Language Activities", "Mathematical Activities", "Environmental Activities"],
        "PP2": ["Language Activities", "Mathematical Activities", "Environmental Activities"],
        "Grade 1": ["Math", "English", "Kiswahili", "Environmental Activities"],
        "Grade 2": ["Math", "English", "Kiswahili", "Environmental Activities"],
        "Grade 3": ["Math", "English", "Kiswahili", "Science", "Social Studies"],
        "Grade 4": ["Math", "English", "Kiswahili", "Science", "Social Studies"],
        "Grade 5": ["Math", "English", "Kiswahili", "Science", "Social Studies"],
        "Grade 6": ["Math", "English", "Kiswahili", "Science", "Social Studies"],
        "Grade 7": ["Math", "English", "Kiswahili", "Integrated Science", "Social Studies"],
        "Grade 8": ["Math", "English", "Kiswahili", "Integrated Science", "Social Studies"],
        "Grade 9": ["Math", "English", "Kiswahili", "Physics", "Chemistry", "Biology"]
    }
    if Subject.query.count() == 0:
        for grade, subjects in subjects_by_grade.items():
            for s in subjects:
                db.session.add(Subject(name=s, grade=grade))
        db.session.commit()