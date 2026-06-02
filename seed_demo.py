import random
from extensions import db                   
from models import School, Student, Subject, Mark, User
from seed import seed_subjects
from utils.helpers import cbc_grade

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
    return f"{first} {last} {random.randint(100,999)}"

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
    for i, name in enumerate(school_names):
        school = School(
            name=name,
            type="Public" if i % 2 != 0 else "Private"
        )
        db.session.add(school)
        schools.append(school)
    db.session.commit()

    grades = ["PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4",
              "Grade 5","Grade 6","Grade 7","Grade 8","Grade 9"]

    terms = ["Term 1","Term 2","Term 3"]
    exams = ["Exam 1","Exam 2","Exam 3"]          # ← NEW
    year = 2026

    total_students = 0
    total_marks = 0

    for school in schools:
        for grade in grades:
            subjects = subjects_by_grade.get(grade, [])
            if not subjects:
                continue

            for _ in range(50):
                gender = random.choice(['M','F'])
                name = random_student_name(gender)
                student = Student(
                    name=name,
                    grade=grade,
                    gender=gender,
                    school_id=school.id
                )
                db.session.add(student)
                db.session.flush()

                for subject in subjects:
                    for term in terms:
                        for exam in exams:       # ← 3 exams per term
                            score = random.randint(20, 100)
                            mark = Mark(
                                student_id=student.id,
                                subject_id=subject.id,
                                score=score,
                                term=term,
                                year=year,
                                exam=exam,        # ← set exam
                                cbc_level=cbc_grade(score)
                            )
                            db.session.add(mark)
                            total_marks += 1
                total_students += 1

        db.session.commit()
        print(f"  ✔ School '{school.name}' – {total_students} students so far...")

    # Create admin user only if it doesn't exist
    from werkzeug.security import generate_password_hash
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

# ------------------------------------------------------------
if __name__ == "__main__":
    # This block only runs when executing the file directly.
    # It needs a Flask app context, so import app here.
    from app import app
    with app.app_context():
        db.create_all()
        seed_demo_data()