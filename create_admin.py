import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt

DATABASE_URL = os.getenv("DATABASE_URL")

def create_admin():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("Creating WAW firm (if not exists)...")
    cur.execute(
        "INSERT INTO firms (id, name) VALUES (1, 'WAW Law Firm') ON CONFLICT (id) DO NOTHING;"
    )
    
    print("Hashing new password...")
    new_password = os.environ["WAW_ADMIN_PASSWORD"]  # from env, never hardcode
    # Use bcrypt directly
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
    
    print("Creating admin user (if not exists)...")
    cur.execute(
        """
        INSERT INTO users (firm_id, email, username, password_hash, role, name)
        VALUES (1, 'admin@waw.com', 'waw_admin', %s, 'firm_admin', 'WAW Admin')
        ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash;
        """,
        (hashed_password,)
    )

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Admin user ready! Email: admin@waw.com (password taken from WAW_ADMIN_PASSWORD)")

if __name__ == "__main__":
    create_admin()