from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext
from datetime import datetime

import os
data_dir = os.getenv("LOGBOOK_DATA_DIR", ".")
db_path = os.path.join(data_dir, "logbook.db")
DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    full_name = Column(String)
    pilot_name = Column(String)
    email = Column(String)
    license_type = Column(String)
    aircraft_type = Column(String)
    google_id = Column(String, unique=True, index=True)
    google_refresh_token = Column(String)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    login_count = Column(Integer, default=0)
    functions_used = Column(String, default="") # Comma separated list of features used
    ai_count = Column(Integer, default=0) # Total AI calls by this user

    organizations = relationship("Organization", back_populates="user")
    natures = relationship("FlightNature", back_populates="user")

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)

    user = relationship("User", back_populates="organizations")

class FlightNature(Base):
    __tablename__ = "flight_natures"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)

    user = relationship("User", back_populates="natures")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Self-healing migration for missing columns
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        # Check existing columns
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add missing columns if they don't exist
        if 'login_count' not in columns:
            print("[MIGRATION] Adding login_count column")
            cursor.execute("ALTER TABLE users ADD COLUMN login_count INTEGER DEFAULT 0")
        
        if 'functions_used' not in columns:
            print("[MIGRATION] Adding functions_used column")
            cursor.execute("ALTER TABLE users ADD COLUMN functions_used TEXT DEFAULT ''")
            
        if 'ai_count' not in columns:
            print("[MIGRATION] Adding ai_count column")
            cursor.execute("ALTER TABLE users ADD COLUMN ai_count INTEGER DEFAULT 0")
            
        conn.commit()
    except Exception as e:
        print(f"[MIGRATION] Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
