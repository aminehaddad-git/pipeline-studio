from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# ─── Configuration ────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-fallback-key")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 480  # 8 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

load_dotenv()
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "options": "-c client_encoding=UTF8",
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# ─── Password helpers ─────────────────────────────────────
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# ─── Token helpers ────────────────────────────────────────
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# ─── User helpers ─────────────────────────────────────────
def get_user(username: str):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        "SELECT * FROM datawarehouse.users WHERE username = %s",
        (username,)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(user) if user else None

def create_user(username: str, full_name: str, password: str, role: str = "viewer"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO datawarehouse.users (username, full_name, hashed_password, role)
           VALUES (%s, %s, %s, %s)""",
        (username, full_name, hash_password(password), role)
    )
    conn.commit()
    cursor.close()
    conn.close()

def list_users():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        "SELECT id, username, full_name, role, created_at FROM datawarehouse.users ORDER BY id"
    )
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(u) for u in users]

def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user