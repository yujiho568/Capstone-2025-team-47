from sqlalchemy import func
from app.models.user import User
from app.core.security import hash_password

def get_user_by_email(db,email):
    return db.query(User).filter(func.lower(User.email)==email.strip().lower()).first()
def create_user(db,user):
    row=User(email=str(user.email).strip().lower(),hashed_password=hash_password(user.password.get_secret_value()))
    db.add(row); db.commit(); db.refresh(row)
    return row
def get_user(db,user_id): return db.get(User,user_id)
