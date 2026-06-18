import random
from extensions import db                   
from models import School, Student, Subject, Mark, User
from seed import seed_subjects
from utils.helpers import cbc_grade
from werkzeug.security import generate_password_hash

# ------------------------------------------------------------
# Helper: random names
# ------------------------------------------------------------
FIRST_NAMES_MALE = [
    "Liam","Noah","Oliver","James","Elijah","William","Henry","Lucas",
    "Benjamin","Theodore","Jack","Levi","Alexander","Daniel","Michael",
    "Matthew","Samuel","Sebastian","David","Joseph","John","Owen","Dylan"
]
FIRST_NAMES_FEMALE = [
    "Olivia","Emma","Charlotte","Amelia","Sophia","Isabella","Ava",
    "Mia","Evelyn","Luna","Harper","Camila","Gianna","Abigail",
    "Emily","Sofia","Aria","Penelope","Chloe","Layla","Nora","Mila"
]
LAST_NAMES = [
    "Ndegwa","Muriithi","Lemayan","Mathenge","Njathi","Gichuki","Mugo",
    "Libese","Bundi","Ndungu","Ngari","Kemuma","Kihuma",
    "Liban","Odhiambo","Nyambero","Kiilu","Junior","Wambui","Galgalo"
]

def random_student_name(gender):
    first = random.choice(FIRST_NAMES_MALE if gender == 'M' else FIRST_NAMES_FEMALE)
    last = random.choice(LAST_NAMES)
    return f"{first} {last}"

# ------------------------------------------------------------
# Main seeding function
# ------------------------------------------------------------
def seed_demo_data():
    print("🌱 Seeding demo data (20 schools, 50 students/grade each)...")

    seed_subjects()

    all_subjects = Subject.query.all()
    subjects_by_grade = {}
    for sub in all_subjects:
        subjects_by_grade.setdefault(sub.grade, []).append(sub)

    school_names = [
        "Kerugoya Good Shepherds", "Hosannah Junior Academy", "Effort Junior School",
        "Thaita Light Academy", "Kaitheri Primary", "Kimandi Academy",
        "Kiandieri Primary", "Kangaita Primary", "Mugwandi Primary",
        "Kiabarikiri Primary", "PCEA Kerugoya Academy", "Valley Road Academy",
        "Waigiri Primary", "Kerugoya Municipality Boarding", "St. Joseph Primary",
        "Kiamuruga Primary", "St. Michael Girls Boarding", "Thaita Primary",
        "Kiranja Primary", "Kamuruana Hills Premier"
    ]

    schools = []
    for i, name in enumerate(school_names, start=1):
        school = School(name=name, type="Public" if i % 3 != 0 else "Private")
        db.session.add(school)
        schools.append(school)
    db.session.commit()

    grades = ["PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4",
              "Grade 5","Grade 6","Grade 7","Grade 8","Grade 9"]

    terms = ["Term 1","Term 2","Term 3"]
    exams = ["Exam 1","Exam 2","Exam 3"]
    year = 2026

    total_students = 0
    total_marks = 0

    # Pre‑compute hashed passwords (do once, not per school)
    principal_pw = generate_password_hash("principal123")
    teacher_pw = generate_password_hash("teacher123")

    for school in schools:
        # Batch users
        users = []
        users.append(User(
            username=f"principal{school.id}",
            password=principal_pw,
            role="principal",
            school_id=school.id
        ))

        for t in range(1, 4):
            users.append(User(
                username=f"teacher{school.id}_{t}",
                password=teacher_pw,
                role="teacher",
                school_id=school.id,
                grade=random.choice(grades)   # ← ADD THIS
            ))
        db.session.add_all(users)          # insert all 4 users at once

        students_batch = []
        marks_batch = []

        for grade in grades:
            subjects = subjects_by_grade.get(grade, [])
            if not subjects:
                continue
            for _ in range(50):
                gender = random.choice(['M','F'])
                student = Student(
                    name=random_student_name(gender),
                    grade=grade,
                    gender=gender,
                    school_id=school.id
                )
                db.session.add(student)
                db.session.flush()           # we need student.id for marks

                for subject in subjects:
                    for term in terms:
                        for exam in exams:
                            score = random.randint(20, 100)
                            marks_batch.append(Mark(
                                student_id=student.id,
                                subject_id=subject.id,
                                score=score,
                                term=term,
                                year=year,
                                exam=exam,
                                cbc_level=cbc_grade(score)
                            ))

                # Flush marks in larger batches (every 500 marks or so)
                if len(marks_batch) >= 500:
                    db.session.add_all(marks_batch)
                    db.session.flush()
                    total_marks += len(marks_batch)
                    marks_batch.clear()

                total_students += 1

    # Insert any remaining marks
    if marks_batch:
        db.session.add_all(marks_batch)
        db.session.flush()
        total_marks += len(marks_batch)
        marks_batch.clear()

    db.session.commit()

    # Create admin user if it doesn't exist
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username="admin",
            password=generate_password_hash("admin123"),
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin user 'admin' created.")
    else:
        print("ℹ️ Admin user already exists, skipping.")

    print(f"✅ Done! Total students: {total_students}, Total marks: {total_marks}")

# ------------------------------------------------------------
if __name__ == "__main__":
    from app import app
    with app.app_context():
        db.create_all()
        seed_demo_data()