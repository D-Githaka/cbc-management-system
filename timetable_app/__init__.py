# timetable_app/__init__.py
from flask import Flask
from extensions import db, login_manager

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    app.debug = True
    db.init_app(app)
    login_manager.init_app(app)

    from . import routes
    app.register_blueprint(routes.bp)
    return app