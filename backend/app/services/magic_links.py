"""
Magic Link Token System for Tracky PM.

Provides secure, no-auth response capability via signed JWT tokens.

Key Features:
- JWT-based magic links (no login required)
- Updateable until deadline (not one-time use)
- Cryptographically signed with app secret
- Bound to specific resource + work item
- Expiry tied to task deadline

CRITICAL FIXES:
- CRIT_001: Null safety for token record lookups
- CRIT_004: All datetimes now timezone-aware (UTC)
- CRIT_008: Token revocation with atomic operations
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, date, timezone
from typing import Optional, Tuple
from uuid import UUID
import jwt

from app.core.config import settings
from app.core.database import get_supabase_client


logger = logging.getLogger(__name__)


# JWT Configuration
JWT_ALGORITHM = "HS256"
MAGIC_LINK_BASE_URL = settings.frontend_url or "http://localhost:5173"


class TokenError(Exception):
    """Base exception for token errors."""
    pass


class TokenExpiredError(TokenError):
    """Token has expired."""
    pass


class TokenInvalidError(TokenError):
    """Token is invalid or tampered."""
    pass


class TokenRevokedError(TokenError):
    """Token has been revoked."""
    pass


class TokenResourceMismatchError(TokenError):
    """Token doesn't belong to this resource."""
    pass


def _get_jwt_secret() -> str:
    """Get JWT signing secret from settings."""
    # Use a dedicated secret or fall back to app secret
    secret = getattr(settings, 'jwt_secret', None) or settings.supabase_anon_key
    if not secret:
        raise ValueError("JWT secret not configured")
    return secret


def _hash_token(token: str) -> str:
    """Create SHA256 hash of token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# Public alias for hash function (CRIT_008)
def hash_token(token: str) -> str:
    """
    Create SHA256 hash of token for storage/lookup.
    
    Public alias for use by other modules.
    """
    return _hash_token(token)


def get_token_record(token: str) -> Optional[dict]:
    """
    Get the database record for a token (CRIT_008).
    
    Used to check if a token has been used/revoked before processing response.
    
    Args:
        token: The JWT token string
        
    Returns:
        Token record dict or None if not found
    """
    token_hash = _hash_token(token)
    db = get_supabase_client()
    
    response = db.client.table("response_tokens").select(
        "id, token_hash, is_revoked, revoked, revoked_at, used_at, "
        "used_by_response_id, expires_at"
    ).eq("token_hash", token_hash).execute()
    
    if not response.data:
        return None
    
    record = response.data[0]
    
    # Normalize field names (handle both is_revoked and revoked)
    record["revoked"] = record.get("revoked") or record.get("is_revoked", False)
    
    return record


def generate_magic_link_token(
    work_item_id: UUID,
    resource_id: UUID,
    deadline: date,
    alert_id: Optional[UUID] = None,
    extra_claims: Optional[dict] = None
) -> Tuple[str, str, datetime]:
    """
    Generate a secure magic link token.
    
    The token is a JWT containing:
    - work_item_id: Which task this is for
    - resource_id: Who is authorized to respond
    - expires_at: When the token expires (deadline + buffer)
    - alert_id: (optional) Which alert triggered this
    - jti: Unique token ID for tracking
    
    Args:
        work_item_id: The work item UUID
        resource_id: The authorized responder's UUID
        deadline: Task deadline (token expires after this)
        alert_id: Optional alert ID
        extra_claims: Additional JWT claims
    
    Returns:
        Tuple of (token, token_hash, expiry_datetime)
    """
    # CRIT_004: Token expires at end of deadline day (23:59:59 UTC) - TIMEZONE AWARE
    # Add 1 day buffer to allow end-of-day responses
    expiry = datetime.combine(
        deadline + timedelta(days=1),
        datetime.max.time(),
        tzinfo=timezone.utc  # CRIT_004: Explicit UTC timezone
    )
    
    # Unique token ID
    jti = secrets.token_urlsafe(16)
    
    # Build JWT payload - CRIT_004: All timestamps UTC-aware
    payload = {
        "sub": str(resource_id),  # Subject = resource
        "wid": str(work_item_id),  # Work item ID
        "exp": expiry,
        "iat": datetime.now(timezone.utc),  # CRIT_004: UTC-aware
        "jti": jti,
        "type": "magic_link",
        "action": "respond_to_alert"
    }
    
    if alert_id:
        payload["aid"] = str(alert_id)
    
    if extra_claims:
        payload.update(extra_claims)
    
    # Sign the token
    token = jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)
    token_hash = _hash_token(token)
    
    return token, token_hash, expiry


def validate_magic_link_token(token: str) -> dict:
    """
    Validate a magic link token and return its claims.
    
    Checks:
    1. Token is properly signed
    2. Token has not expired
    3. Token has not been revoked
    4. Token contains required claims
    
    Args:
        token: The JWT token string
    
    Returns:
        Decoded token claims
    
    Raises:
        TokenExpiredError: If token is expired
        TokenInvalidError: If token is invalid
        TokenRevokedError: If token was revoked
    """
    try:
        # Decode and verify signature
        payload = jwt.decode(
            token,
            _get_jwt_secret(),
            algorithms=[JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("This link has expired")
    except jwt.InvalidTokenError as e:
        raise TokenInvalidError(f"Invalid token: {str(e)}")
    
    # Verify required claims
    required_claims = ["sub", "wid", "jti"]
    for claim in required_claims:
        if claim not in payload:
            raise TokenInvalidError(f"Missing required claim: {claim}")
    
    # Check if token is revoked in database
    token_hash = _hash_token(token)
    db = get_supabase_client()
    
    response = db.client.table("response_tokens").select(
        "is_revoked, revocation_reason"
    ).eq("token_hash", token_hash).execute()
    
    if response.data:
        token_record = response.data[0]
        if token_record.get("is_revoked"):
            raise TokenRevokedError(
                token_record.get("revocation_reason", "Token has been revoked")
            )
    
    return payload


def create_magic_link(
    work_item_id: UUID,
    resource_id: UUID,
    deadline: date,
    alert_id: Optional[UUID] = None
) -> str:
    """
    Create a full magic link URL for responding to status check.
    
    The URL format: {frontend_url}/respond?token={jwt_token}
    
    Args:
        work_item_id: The work item UUID
        resource_id: The authorized responder's UUID
        deadline: Task deadline
        alert_id: Optional alert ID
    
    Returns:
        Full magic link URL
    """
    token, token_hash, expiry = generate_magic_link_token(
        work_item_id=work_item_id,
        resource_id=resource_id,
        deadline=deadline,
        alert_id=alert_id
    )
    
    # Store token record in database
    db = get_supabase_client()
    
    db.client.table("response_tokens").insert({
        "token_hash": token_hash,
        "work_item_id": str(work_item_id),
        "resource_id": str(resource_id),
        "alert_id": str(alert_id) if alert_id else None,
        "expires_at": expiry.isoformat(),
        "allowed_actions": ["respond"]
    }).execute()
    
    # Build magic link URL
    magic_link = f"{MAGIC_LINK_BASE_URL}/respond?token={token}"
    
    return magic_link


def record_token_use(token: str, client_ip: Optional[str] = None) -> None:
    """
    Record that a token was used (for audit purposes).
    
    Args:
        token: The JWT token
        client_ip: Client IP address
    """
    token_hash = _hash_token(token)
    db = get_supabase_client()
    
    # CRIT_004: Use UTC-aware timestamp
    db.client.table("response_tokens").update({
        "last_used_at": datetime.now(timezone.utc).isoformat()
    }).eq("token_hash", token_hash).execute()


def revoke_token(
    token_hash: str,
    revoked_by: str,
    reason: str
) -> bool:
    """
    Revoke a token so it can no longer be used.
    
    Args:
        token_hash: Hash of the token to revoke
        revoked_by: Who is revoking (email or system)
        reason: Why the token is being revoked
    
    Returns:
        True if revoked, False if not found
    """
    db = get_supabase_client()
    
    # CRIT_004: Use timezone-aware datetime
    response = db.client.table("response_tokens").update({
        "is_revoked": True,
        "revoked_at": datetime.now(timezone.utc).isoformat(),
        "revoked_by": revoked_by,
        "revocation_reason": reason
    }).eq("token_hash", token_hash).execute()
    
    return len(response.data) > 0


def get_token_info(token: str) -> Optional[dict]:
    """
    Get information about a token.
    
    Args:
        token: The JWT token
    
    Returns:
        Token info dict or None if not found
    """
    try:
        payload = validate_magic_link_token(token)
        
        token_hash = _hash_token(token)
        db = get_supabase_client()
        
        response = db.client.table("response_tokens").select(
            "*, work_items(external_id, name, current_end), resources(name, email)"
        ).eq("token_hash", token_hash).execute()
        
        if response.data:
            record = response.data[0]
            return {
                "valid": True,
                "work_item_id": payload["wid"],
                "resource_id": payload["sub"],
                "expires_at": payload.get("exp"),
                "work_item": record.get("work_items"),
                "resource": record.get("resources"),
                "use_count": record.get("use_count", 0)
            }
        
        return {
            "valid": True,
            "work_item_id": payload["wid"],
            "resource_id": payload["sub"],
            "expires_at": payload.get("exp")
        }
        
    except TokenError as e:
        return {
            "valid": False,
            "error": str(e)
        }


def validate_token_for_work_item(
    token: str,
    work_item_id: UUID
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    Validate token and check it matches the work item.
    
    Args:
        token: JWT token
        work_item_id: Expected work item ID
    
    Returns:
        Tuple of (is_valid, error_message, claims)
    """
    try:
        claims = validate_magic_link_token(token)
        
        if claims.get("wid") != str(work_item_id):
            return False, "Token does not match this work item", None
        
        return True, None, claims
        
    except TokenExpiredError:
        return False, "This link has expired. Please request a new status check.", None
    except TokenRevokedError:
        return False, "This link has been disabled. Please contact your PM.", None
    except TokenInvalidError as e:
        return False, f"Invalid link: {str(e)}", None
    except Exception as e:
        return False, f"Error validating link: {str(e)}", None
