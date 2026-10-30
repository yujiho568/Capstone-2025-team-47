# app/api/v1/users.py  (예: 너가 보여준 라우터 파일)

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError

from app.schemas.user import UserCreate, UserRead, Token, UserLogin
from app.crud.user import create_user, get_user_by_email
from app.core.security import verify_password, create_access_token, decode_access_token
from app.models.user import User
from app.db.database import get_db

# boto3 추가
import boto3
from botocore.exceptions import NoCredentialsError, ClientError, EndpointConnectionError, BotoCoreError

router = APIRouter(prefix="/users", tags=["users"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login")


@router.post("/register", response_model=UserRead)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if get_user_by_email(db, str(user.email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    from sqlalchemy.exc import IntegrityError
    try: return create_user(db, user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Registration conflict")


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = (form_data.username or "").strip().lower()
    user = get_user_by_email(db, email)
    if not user or not user.is_active or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        email: str = payload.get("sub") if payload else None
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        raise credentials_exception
    return user


@router.get("/me", response_model=UserRead)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
