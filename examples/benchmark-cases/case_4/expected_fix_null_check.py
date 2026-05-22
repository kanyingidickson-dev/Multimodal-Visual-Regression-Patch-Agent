def get_user_status(user):
    if user is None:
        return "offline"
    return user.status
