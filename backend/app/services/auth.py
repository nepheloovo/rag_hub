"""认证服务：密码哈希 + JWT 签发/校验 + 审计留痕"""
import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from app.models import AuditLog, User

JWT_ALGO = "HS256"
TOKEN_TTL_HOURS = 24 * 7

_secret = os.environ.get("AUTH_SECRET") or hashlib.sha256(
    ("zhishu-auth-" + settings.database_url).encode()
).hexdigest()


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120000).hex()
    return hmac.compare_digest(calc, digest)


def issue_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, _secret, algorithm=JWT_ALGO)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _secret, algorithms=[JWT_ALGO])
    except Exception:  # noqa: BLE001
        return None


def audit(
    db,
    action: str,
    target: str = "",
    detail: str = "",
    actor: str = "系统",
    role: str = "",
    ip: str = "",
) -> None:
    try:
        db.add(
            AuditLog(
                id=uuid.uuid4().hex,
                actor=actor,
                role=role,
                action=action,
                target=target[:256],
                detail=detail[:2000],
                ip=ip,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
