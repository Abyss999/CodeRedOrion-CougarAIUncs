import functools
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from flask import current_app, g, request

from .errors import ApiError
from .extensions import db
from .models import User

TOKEN_TTL = timedelta(days=30)


def make_token(user_id) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + TOKEN_TTL},
                      current_app.config["JWT_SECRET"], algorithm="HS256")


def require_auth(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise ApiError(401, "unauthorized", "Missing bearer token.")
        secret = current_app.config["JWT_SECRET"]
        if not secret:
            raise ApiError(500, "internal_error", "Server JWT secret is not configured.")
        try:
            claims = jwt.decode(token.strip(), secret, algorithms=["HS256"])
            uid = uuid.UUID(claims["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            raise ApiError(401, "unauthorized", "Invalid or expired token.")
        user = db.session.get(User, uid)
        if user is None:
            raise ApiError(401, "unauthorized", "Unknown user.")
        g.user = user
        return fn(*args, **kwargs)

    return wrapper
