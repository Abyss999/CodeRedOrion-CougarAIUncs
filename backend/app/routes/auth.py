import re

from flask import Blueprint, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import make_token
from ..errors import ApiError, validation_error
from ..extensions import db
from ..models import User
from ._util import iso, json_body

bp = Blueprint("auth", __name__, url_prefix="/auth")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _user(u):
    return {"id": str(u.id), "email": u.email, "display_name": u.display_name,
            "created_at": iso(u.created_at)}


def _str(body, key):
    v = body.get(key)
    if not isinstance(v, str) or not v.strip():
        raise validation_error(f"{key} is required.")
    return v.strip()


@bp.post("/signup")
def signup():
    body = json_body()
    email = _str(body, "email").lower()
    name = _str(body, "display_name")
    password = body.get("password")
    if not _EMAIL.match(email):
        raise validation_error("email is not a valid address.")
    if not isinstance(password, str) or len(password) < 8:
        raise validation_error("password must be at least 8 characters.")
    if User.query.filter_by(email=email).first():
        raise ApiError(409, "email_taken", "An account with that email already exists.")
    user = User(email=email, display_name=name, password_hash=generate_password_hash(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError(409, "email_taken", "An account with that email already exists.")
    return jsonify(token=make_token(user.id), user=_user(user)), 201


@bp.post("/login")
def login():
    body = json_body()
    email = _str(body, "email").lower()
    password = body.get("password")
    user = User.query.filter_by(email=email).first()
    if not user or not isinstance(password, str) or not check_password_hash(user.password_hash, password):
        raise ApiError(401, "invalid_credentials", "Incorrect email or password.")
    return jsonify(token=make_token(user.id), user=_user(user))
