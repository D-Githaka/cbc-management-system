
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from extensions import db
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20))
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=True)
    grade = db.Column(db.String(20), nullable=True)
    is_superadmin = db.Column(db.Boolean, default=False)
    school = db.relationship('School', backref='users')

class School(db.Model):
    __tablename__ = 'school'
    __table_args__ = (
        db.Index('idx_school_name', 'name'),
        db.Index('idx_school_type', 'type'),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False, default='Public')
    entry = db.Column(db.String(20), unique=True, nullable=True)   # ADDED
    students = db.relationship('Student', backref='school', lazy='dynamic')

class Student(db.Model):
    __tablename__ = 'student'
    __table_args__ = (
        db.Index('idx_student_school_id', 'school_id'),
        db.Index('idx_student_grade', 'grade'),
        db.Index('idx_student_school_grade', 'school_id', 'grade'),
        db.UniqueConstraint('admission_number', name='uq_student_admission_number'),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(20), nullable=False)
    gender = db.Column(db.String(1), nullable=False, default='M')
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    admission_number = db.Column(db.String(50), nullable=True)      # ADDED
    marks = db.relationship('Mark', backref='student', lazy='dynamic')

class Subject(db.Model):
    __tablename__ = 'subject'
    __table_args__ = (
        db.Index('idx_subject_grade', 'grade'),
        db.UniqueConstraint('name', 'grade', name='uq_subject_name_grade'),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    grade = db.Column(db.String(20), nullable=False)

class Mark(db.Model):
    __tablename__ = 'mark'
    __table_args__ = (
        db.Index('idx_mark_student_id', 'student_id'),
        db.Index('idx_mark_subject_id', 'subject_id'),
        db.Index('idx_mark_term_year_exam', 'term', 'year', 'exam'),
        db.Index('idx_mark_status', 'status'),
        db.Index('idx_mark_submitted_by', 'submitted_by'),
        db.Index('idx_mark_approved_by', 'approved_by'),
        db.Index('idx_mark_student_term_year', 'student_id', 'term', 'year'),
    )
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
    term = db.Column(db.String(10), nullable=False)
    exam = db.Column(db.String(20), default='Exam 1')
    year = db.Column(db.Integer, nullable=False)
    cbc_level = db.Column(db.String(2))
    status = db.Column(db.String(20), default='Pending')
    submitted_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subject = db.relationship('Subject')
    # (student relationship already defined)