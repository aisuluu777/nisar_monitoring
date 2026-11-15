from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, create_token, get_principal, verify_password
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    district_id: str | None


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "неверный логин или пароль")
    return TokenOut(access_token=create_token(user), role=user.role, district_id=user.district_id)


@router.get("/me")
def me(p: Principal = Depends(get_principal)):
    return {"role": p.role, "username": p.username, "district_id": p.district_id}
