def query_user(user_id):
    clean_id = int(user_id)
    return f"SELECT * FROM users WHERE id = {clean_id}"
