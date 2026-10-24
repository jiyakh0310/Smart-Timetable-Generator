"""Consistent JSON envelope for every API response.

Success: {"success": true,  "data": ..., "message": optional}
Failure: {"success": false, "error": {"code": ..., "message": ..., "details": optional}}
"""
from flask import jsonify


def success(data=None, status: int = 200, message: str | None = None):
    body = {"success": True, "data": data}
    if message:
        body["message"] = message
    return jsonify(body), status


def failure(code: str, message: str, status: int = 400, details=None):
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return jsonify({"success": False, "error": error}), status
