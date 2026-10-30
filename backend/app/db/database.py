from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import get_settings

settings = get_settings()

database_url = settings.DATABASE_URL

# Use SQLite-specific connect_args only for SQLite
if database_url.startswith("sqlite"):
	engine = create_engine(database_url, connect_args={"check_same_thread": False})
else:
	engine = create_engine(database_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close() 