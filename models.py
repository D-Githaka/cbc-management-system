from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from extensions import db


# -------------------------
# USER MODEL (ONLY ONE)
# -------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))

    role = db.Column(db.String(20))  # admin / principal / teacher

    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=True)
    grade = db.Column(db.String(20), nullable=True)  # teachers only
    is_superadmin = db.Column(db.Boolean, default=False)
    school = db.relationship('School', backref='users')
# -------------------------
# SCHOOL
# -------------------------
class School(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False, default='Public')  # Public or Private

    students = db.relationship('Student', backref='school', lazy=True)


# -------------------------
# STUDENT
# -------------------------
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(20), nullable=False)
    gender = db.Column(db.String(1), nullable=False, default='M')  
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)

    marks = db.relationship('Mark', backref='student', lazy=True)


# -------------------------
# SUBJECT
# -------------------------
class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(50), nullable=False)
    grade = db.Column(db.String(20), nullable=False)


# -------------------------
# MARKS
# -------------------------
class Mark(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'))

    score = db.Column(db.Float)

    term = db.Column(db.String(10))
    exam = db.Column(db.String(20), default='Exam 1')
    year = db.Column(db.Integer)

    cbc_level = db.Column(db.String(2))

    # Relationships
    subject = db.relationship('Subject')
