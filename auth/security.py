
import secrets

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


def hash_password(password):
    """Create a secure password hash."""
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError(
            "Password must contain at least 12 characters."
        )

    return generate_password_hash(
        password,
        method="scrypt"
    )


def verify_password(password_hash, password):
    """Verify a password against its stored hash."""
    if not password_hash or not password:
        return False

    return check_password_hash(password_hash, password)


def generate_session_token():
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(32)
