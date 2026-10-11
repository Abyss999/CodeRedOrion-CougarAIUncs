"""Standard error shape: {"error": {"code": "...", "message": "..."}}."""
import logging

from flask import jsonify
from sqlalchemy.exc import DataError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)

_HTTP_CODES = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "validation_error",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def validation_error(msg):
    return ApiError(400, "validation_error", msg)


def not_found(msg="Not found."):
    return ApiError(404, "not_found", msg)


def upstream_unavailable(msg="Upstream service unavailable."):
    return ApiError(502, "upstream_unavailable", msg)


def error_response(status: int, code: str, message: str):
    return jsonify(error={"code": code, "message": message}), status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api(e):
        return error_response(e.status, e.code, e.message)

    @app.errorhandler(HTTPException)
    def _http(e):
        code = _HTTP_CODES.get(e.code, "http_error")
        return error_response(e.code or 500, code, e.description or e.name)

    @app.errorhandler(DataError)
    def _data(e):
        from .extensions import db

        db.session.rollback()
        return error_response(400, "validation_error", "Invalid value.")

    @app.errorhandler(Exception)
    def _unhandled(e):
        log.exception("unhandled error")
        from .extensions import db

        db.session.rollback()
        return error_response(500, "internal_error", "Internal server error.")
