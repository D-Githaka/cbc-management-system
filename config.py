import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key')
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'database.db')
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    SESSION_PERMANENT = False
    REMEMBER_COOKIE_SECURE = os.environ.get('FLASK_ENV') == True
    ADMIN_SECRET = os.environ.get('ADMIN_SECRET_KEY')

    CACHE_TYPE = 'FileSystemCache'
    CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
    CACHE_DEFAULT_TIMEOUT = 900  # 15 minutes

    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'your_email@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'your_app_password')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME', 'your_email@gmail.com')

    '''
    basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)
app.config['SESSION_PERMANENT'] = False
app.config['REMEMBER_COOKIE_SECURE'] = True   # only over HTTPS
app.config['SESSION_COOKIE_SECURE'] = True
app.config['ADMIN_SECRET'] = os.environ.get('ADMIN_SECRET_KEY')
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_app_password'
app.config['MAIL_DEFAULT_SENDER'] = 'your_email@gmail.com'
'''
