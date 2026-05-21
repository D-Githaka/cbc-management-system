import random
import string
from models import db, School, Student, Subject, Mark, User
from app import app, generate_password_hash
from seed import seed_subjects  # reuse existing subject seeding

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
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller",
    "Davis","Rodriguez","Martinez","Hernandez","Lopez","Gonzalez",
    "Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin"
]

def random_student_name(gender):
    first = random.choice(FIRST_NAMES_MALE if gender == 'M' else FIRST_NAMES_FEMALE)
    last = random.choice(LAST_NAMES)
    # Add a random number to avoid duplicate names
    return f"{first} {last} {random.randint(100,999)}"

# ------------------------------------------------------------
# Main seeding function
# ------------------------------------------------------------
def seed_demo_data():
    print("🌱 Seeding demo data (20 schools, 50 students/grade each)...")

    # Ensure subjects are seeded first
    seed_subjects()

    # Fetch all subjects grouped by grade
    all_subjects = Subject.query.all()
    subjects_by_grade = {}
    for sub in all_subjects:
        subjects_by_grade.setdefault(sub.grade, []).append(sub)

    # School names
    school_names = [
        "Green Valley Academy", "Sunrise Primary", "Hilltop School",
        "Riverside Edu", "Maple Leaf School", "Oakwood Prep",
        "Silver Oak School", "Bluebell Academy", "Cedar Grove Primary",
        "Golden Gate Edu", "Pine View School", "Willow Creek Academy",
        "Lakeside Primary", "Elm Street School", "Birchwood Academy",
        "Spruce Hill Prep", "Cypress Lane School", "Redwood Primary",
        "Juniper Academy", "Ashford School"
    ]

    # Create 20 schools (alternate Public/Private)
    schools = []
    for i, name in enumerate(school_names):
        school = School(
            name=name,
            type="Public" if i % 3 != 0 else "Private"  # ~2/3 public
        )
        db.session.add(school)
        schools.append(school)
    db.session.commit()

    grades = ["PP1","PP2","Grade 1","Grade 2","Grade 3","Grade 4",
              "Grade 5","Grade 6","Grade 7","Grade 8","Grade 9"]

    # Define terms and years
    terms = ["Term 1","Term 2","Term 3"]
    year = 2026

    total_students = 0
    total_marks = 0

    for school in schools:
        for grade in grades:
            # Get subjects for this grade
            subjects = subjects_by_grade.get(grade, [])
            if not subjects:
                continue

            # Create 50 students
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
                db.session.flush()  # get student.id

                # Generate marks for all subjects and all terms
                for subject in subjects:
                    for term in terms:
                        # Random score between 20 and 100, biased lower for variety
                        score = random.randint(20, 100)
                        mark = Mark(
                            student_id=student.id,
                            subject_id=subject.id,
                            score=score,
                            term=term,
                            year=year,
                            cbc_level=cbc_grade(score)
                        )
                        db.session.add(mark)
                        total_marks += 1
                total_students += 1

        # Commit after each school to avoid huge transaction
        db.session.commit()
        print(f"  ✔ School '{school.name}' – {total_students} students so far...")

    # Create one admin user (optional)
    admin = User(
        username="admin",
        password=generate_password_hash("admin123"),
        role="admin"
    )
    db.session.add(admin)
    db.session.commit()

    print(f"✅ Done! Total students: {total_students}, Total marks: {total_marks}")

# Reuse the existing cbc_grade function
def cbc_grade(score):
    if score >= 75: return "EE"
    elif score >= 50: return "ME"
    elif score >= 30: return "AE"
    else: return "BE"

# ------------------------------------------------------------
# Allow running directly or via CLI
# ------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_demo_data()