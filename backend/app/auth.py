"""Minimal single-user authentication: username/password login -> signed JWT bearer token."""

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import Settings, get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_credentials(username: str, password: str, settings: Settings) -> bool:
    # constant-time comparison to avoid timing side channels
    user_ok = hmac.compare_digest(username.encode(), settings.app_username.encode())
    pass_ok = hmac.compare_digest(password.encode(), settings.app_password.encode())
    return user_ok and pass_ok


def create_access_token(subject: str, settings: Settings) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expire_minutes)
    payload = {"sub": subject, "exp": expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def require_user(
    token: str = Depends(oauth2_scheme), settings: Settings = Depends(get_settings)
) -> str:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise unauthorized from None
    subject = payload.get("sub")
    if subject != settings.app_username:
        raise unauthorized
    return subject
