# import json
# from flask_login import current_user
# from extensions import db

# def get_preference(key, default=None):
#     if not current_user.is_authenticated:
#         return default
#     prefs = current_user.preferences
#     if prefs is None or prefs == '':
#         return default
#     try:
#         data = json.loads(prefs)
#     except json.JSONDecodeError:
#         return default
#     return data.get(key, default)

# def set_preference(key, value):
#     if not current_user.is_authenticated:
#         return
#     prefs = current_user.preferences
#     if prefs is None or prefs == '':
#         data = {}
#     else:
#         try:
#             data = json.loads(prefs)
#         except json.JSONDecodeError:
#             data = {}
#     data[key] = value
#     current_user.preferences = json.dumps(data)
#     db.session.commit()

# def set_preferences(data):
#     if not current_user.is_authenticated:
#         return
#     prefs = current_user.preferences
#     if prefs is None or prefs == '':
#         existing = {}
#     else:
#         try:
#             existing = json.loads(prefs)
#         except json.JSONDecodeError:
#             existing = {}
#     existing.update(data)
#     current_user.preferences = json.dumps(existing)
#     db.session.commit()

# def merge_preferences(updates):
#     """Merge updates into global preferences, preserving existing keys."""
#     if not current_user.is_authenticated:
#         return
#     prefs = current_user.preferences
#     if prefs is None or prefs == '':
#         data = {}
#     else:
#         try:
#             data = json.loads(prefs)
#         except json.JSONDecodeError:
#             data = {}
#     data.update(updates)
#     current_user.preferences = json.dumps(data)
#     db.session.commit()

import json
from flask_login import current_user
from extensions import db

def get_preference(key, default=None):
    if not current_user.is_authenticated:
        return default
    prefs = current_user.preferences
    if prefs is None or prefs == '':
        return default
    try:
        data = json.loads(prefs)
    except json.JSONDecodeError:
        return default
    return data.get(key, default)

def merge_preferences(updates):
    """Merge updates into a nested 'global_filters' key."""
    if not current_user.is_authenticated:
        return
    prefs = current_user.preferences
    if prefs is None or prefs == '':
        data = {}
    else:
        try:
            data = json.loads(prefs)
        except json.JSONDecodeError:
            data = {}
    # Ensure the nested key exists
    if 'global_filters' not in data:
        data['global_filters'] = {}
    data['global_filters'].update(updates)
    current_user.preferences = json.dumps(data)
    db.session.commit()