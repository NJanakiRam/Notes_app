# models.py

from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

    @staticmethod
    def get(user_id):
        from app import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()
        conn.close()
        if user_row:
            return User(user_row['id'], user_row['username'], user_row['password'])
        return None
