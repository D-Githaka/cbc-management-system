def cbc_grade(score):
    try:
        score = float(score)
    except:
        return None
    if score >= 75:
        return "EE"
    elif score >= 50:
        return "ME"
    elif score >= 30:
        return "AE"
    else:
        return "BE"