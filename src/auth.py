"""
Authentication module for Municipal Intel.

Magic link passwordless authentication with JWT session tokens.
"""

import secrets
import jwt
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Cookie, Response, Depends
from sqlalchemy.orm import Session

from .database import User, MagicLink

# Configuration from environment variables
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
APP_URL = os.getenv("APP_URL", "http://localhost:8000")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "Municipal Intel <noreply@govtechdiagnostic.com>")

# JWT configuration
ALGORITHM = "HS256"
SESSION_DURATION = timedelta(days=7)  # Sessions last 7 days
MAGIC_LINK_DURATION = timedelta(minutes=15)  # Magic links expire in 15 minutes


def generate_magic_token() -> str:
    """Generate a secure random token for magic links."""
    return secrets.token_urlsafe(32)


def send_magic_link_email(email: str, magic_url: str) -> bool:
    """
    Send magic link email via Resend.

    Returns True if sent successfully, False otherwise.
    """
    if not RESEND_API_KEY:
        print(f"[DEV MODE] Magic link for {email}: {magic_url}")
        return False  # Dev mode - no email sent

    try:
        import resend
        resend.api_key = RESEND_API_KEY

        params = {
            "from": RESEND_FROM_EMAIL,
            "to": [email],
            "subject": "Your Municipal Intel login link",
            "html": f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #1A1816; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 40px 20px; }}
                    .header {{ font-size: 24px; font-weight: 600; margin-bottom: 24px; }}
                    .button {{ display: inline-block; background: #2B4AE0; color: white; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: 500; }}
                    .footer {{ margin-top: 40px; font-size: 14px; color: #5C574F; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">Your Municipal Intel login link</div>
                    <p>Click the button below to securely access Municipal Intel:</p>
                    <p style="margin: 32px 0;">
                        <a href="{magic_url}" class="button">Access Municipal Intel</a>
                    </p>
                    <p style="color: #5C574F; font-size: 14px;">This link expires in 15 minutes and can only be used once.</p>
                    <p style="color: #5C574F; font-size: 14px;">If you didn't request this, you can safely ignore this email.</p>
                    <div class="footer">
                        GovTech Diagnostic<br>
                        ERP Intelligence for Government
                    </div>
                </div>
            </body>
            </html>
            """
        }

        resend.Emails.send(params)
        return True

    except Exception as e:
        print(f"Error sending magic link email: {e}")
        return False


def create_magic_link(db: Session, email: str) -> Optional[MagicLink]:
    """
    Create a magic link for an approved user.

    Only creates a magic link if the user already exists in the database
    (i.e., has been approved by an admin from the waitlist).
    Returns None if user not found — caller should still return 200 to avoid leaking existence.
    """
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user:
        return None

    # Create magic link
    token = generate_magic_token()
    expires_at = datetime.utcnow() + MAGIC_LINK_DURATION

    magic_link = MagicLink(
        user_id=user.id,
        token=token,
        expires_at=expires_at
    )
    db.add(magic_link)
    db.commit()
    db.refresh(magic_link)

    return magic_link


def verify_magic_link(db: Session, token: str) -> Optional[User]:
    """
    Verify a magic link token and return the user.

    Returns None if token is invalid, expired, or already used.
    Marks token as used on success.
    """
    magic_link = db.query(MagicLink).filter(MagicLink.token == token).first()

    if not magic_link:
        return None

    # Check if already used
    if magic_link.used:
        return None

    # Check if expired
    if datetime.utcnow() > magic_link.expires_at:
        return None

    # Mark as used
    magic_link.used = 1
    db.commit()

    # Update user last login
    user = magic_link.user
    user.last_login = datetime.utcnow()
    db.commit()

    return user


def create_session_token(user_id: str, email: str, role: str) -> str:
    """Create a JWT session token including the user's role."""
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + SESSION_DURATION
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_session_token(token: str) -> Optional[dict]:
    """
    Verify a JWT session token.

    Returns payload dict with user_id, email, and role if valid.
    Returns None if invalid or expired.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user(session_token: Optional[str] = Cookie(None)) -> dict:
    """
    FastAPI dependency to get current authenticated user from session cookie.

    Raises HTTPException (401) if not authenticated.
    Returns dict with user_id, email, role.
    """
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = verify_session_token(session_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return payload


def require_role(*roles: str):
    """
    FastAPI dependency factory that enforces role-based access.

    Usage:
        @app.get("/municipal-intel")
        async def page(user = Depends(require_role("consultant", "admin"))):
            ...
    """
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Access denied")
        return user
    return _check


def get_current_user_optional(session_token: Optional[str] = Cookie(None)) -> Optional[dict]:
    """
    Like get_current_user but returns None instead of raising on missing/invalid session.
    Used for routes that want to check auth without hard-requiring it.
    """
    if not session_token:
        return None
    return verify_session_token(session_token)


def set_session_cookie(response: Response, user: User):
    """Set session cookie in response."""
    token = create_session_token(user.id, user.email, user.role)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,  # Use HTTPS in production
        samesite="lax",
        max_age=int(SESSION_DURATION.total_seconds())
    )


def clear_session_cookie(response: Response):
    """Clear session cookie (logout)."""
    response.delete_cookie(key="session_token")
