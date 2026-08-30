from extensions import db
from datetime import datetime

class TimetableSubject(db.Model):
    __tablename__ = 'timetable_subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    middle_hours = db.Column(db.Integer, default=0)
    junior_hours = db.Column(db.Integer, default=0)
    allocations = db.relationship('Allocation', backref='subject', lazy='dynamic')

class Teacher(db.Model):
    __tablename__ = 'teachers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_code = db.Column(db.Integer, unique=True, nullable=False)
    allocations = db.relationship('Allocation', backref='teacher', lazy='dynamic')

class Stream(db.Model):
    __tablename__ = 'streams'
    id = db.Column(db.Integer, primary_key=True)
    grade_level = db.Column(db.Integer, nullable=False)   # 4-9
    stream_name = db.Column(db.String(1), nullable=False) # A, B, C...

class Allocation(db.Model):
    __tablename__ = 'allocations'
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('timetable_subjects.id'), nullable=False)
    grade_level = db.Column(db.Integer, nullable=False)

class Timetable(db.Model):
    __tablename__ = 'timetables'
    id = db.Column(db.Integer, primary_key=True)
    data_json = db.Column(db.Text, nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)


# import sqlite3
# import os

# DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'timetable.db')


# def get_db():
#     """Get a database connection."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     return conn


# def init_db():
#     """Initialise the database with tables and default data."""
#     # Ensure instance directory exists
#     os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

#     conn = get_db()
#     cursor = conn.cursor()

#     # Create tables
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS subjects (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             name TEXT UNIQUE NOT NULL,
#             middle_hours INTEGER DEFAULT 0,
#             junior_hours INTEGER DEFAULT 0
#         )
#     ''')
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS grades (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             level INTEGER UNIQUE NOT NULL
#         )
#     ''')
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS streams (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             grade_level INTEGER NOT NULL,
#             stream_name TEXT NOT NULL,
#             FOREIGN KEY (grade_level) REFERENCES grades(level)
#         )
#     ''')
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS teachers (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             name TEXT NOT NULL,
#             teacher_code INTEGER UNIQUE NOT NULL
#         )
#     ''')
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS allocations (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             teacher_id INTEGER NOT NULL,
#             subject_id INTEGER NOT NULL,
#             grade_level INTEGER NOT NULL,
#             FOREIGN KEY (teacher_id) REFERENCES teachers(id),
#             FOREIGN KEY (subject_id) REFERENCES subjects(id),
#             FOREIGN KEY (grade_level) REFERENCES grades(level)
#         )
#     ''')
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS timetables (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             data_json TEXT
#         )
#     ''')

#     # Insert default grades (4-9) if not present
#     for level in range(4, 10):
#         cursor.execute('INSERT OR IGNORE INTO grades (level) VALUES (?)', (level,))

#     conn.commit()
#     conn.close()


# def query_db(query, args=(), one=False):
#     """Execute a SELECT query and return results."""
#     conn = get_db()
#     cursor = conn.cursor()
#     result = cursor.execute(query, args).fetchall()
#     conn.close()
#     return (result[0] if result else None) if one else result


# def insert_db(query, args=()):
#     """Execute an INSERT query and return the last row ID."""
#     conn = get_db()
#     cursor = conn.cursor()
#     cursor.execute(query, args)
#     conn.commit()
#     last_id = cursor.lastrowid
#     conn.close()
#     return last_id


# def update_db(query, args=()):
#     """Execute an UPDATE query."""
#     conn = get_db()
#     cursor = conn.cursor()
#     cursor.execute(query, args)
#     conn.commit()
#     conn.close()


# def delete_db(query, args=()):
#     """Execute a DELETE query."""
#     conn = get_db()
#     cursor = conn.cursor()
#     cursor.execute(query, args)
#     conn.commit()
#     conn.close()