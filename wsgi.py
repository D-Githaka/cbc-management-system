import sys
from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Add project path if needed (usually already in sys.path)
# sys.path.insert(0, '/path/to/marks_project')

# Import the main app factory
from app import create_app as create_main_app
# Import the timetable app factory
from timetable_app import create_app as create_timetable_app

# Create both apps
main_app = create_main_app()
timetable_app = create_timetable_app()

# Dispatch requests based on path
application = DispatcherMiddleware(main_app, {
    '/timetable': timetable_app
})

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple('0.0.0.0', 5000, application, use_debugger=True, use_reloader=True)