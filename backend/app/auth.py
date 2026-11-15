"""Роли и доступ (раздел 2 ТЗ). Роль проверяется на сервере; район администрации берётся из учётки,
а не из запроса."""
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

STAFF = {"admin_district", "emercom", "sysadmin"}


@dataclass
class Principal:
    role: str                      # public | researcher | admin_district | emercom | sysadmin
    user_id: int | None = None
    username: str | None = None
    district_id: str | None = None

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF

    def district_scope(self) -> str | None:
        """Район, которым ограничен пользователь; None — без ограничения."""
        return self.district_id if self.role == "admin_district" else None


def hash_password(p: str) -> str:
    return pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)


def create_token(user) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_ttl_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role, "district": user.district_id, "exp": exp},
                      s.jwt_secret, algorithm="HS256")


def get_principal(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                  db: Session = Depends(get_db)) -> Principal:
    from app.models import ApiKey, User

    api_key = request.headers.get("X-API-Key")
    if api_key:
        k = db.scalar(select(ApiKey).where(ApiKey.key_hash == hashlib.sha256(api_key.encode()).hexdigest(),
                                           ApiKey.active.is_(True)))
        if not k:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "неверный ключ API")
        return Principal(role=k.role)
    if creds:
        try:
            payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
        except JWTError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "неверный или просроченный токен")
        user = db.get(User, int(payload["sub"]))
        if not user or not user.active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "пользователь отключён")
        return Principal(role=user.role, user_id=user.id, username=user.username,
                         district_id=user.district_id)
    return Principal(role="public")


def require(*roles: str):
    def dep(p: Principal = Depends(get_principal)) -> Principal:
        if p.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN if p.role != "public"
                                else status.HTTP_401_UNAUTHORIZED, "недостаточно прав")
        return p
    return dep


def check_district(p: Principal, district_id: str):
    scope = p.district_scope()
    if scope and scope != district_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "нет доступа к этому району")
