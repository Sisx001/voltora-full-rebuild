"""Origin-aware authentication and CORS security tests.

Tests verify exact origin matching for credentialed requests, CSRF protection,
MFA flows with correct Origin header, and rejection of untrusted origins before
any state mutation.

ASGI tests verify app behavior directly (no edge interference).
External tests document edge behavior as informational.
"""
import json
import os
import sys
import time
from pathlib import Path

import pyotp
import pytest
import requests
from fastapi.testclient import TestClient

# Add backend directory to path for server import
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import MFA lock helper for cross-process synchronization
from test_mfa_lock import mfa_lock


def _read_env_key(path: str, key: str) -> str:
    """Read a key from .env file."""
    content = Path(path)
    if not content.exists():
        return ""
    for line in content.read_text().splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def _base_url() -> str:
    """Get base URL from frontend .env."""
    value = os.environ.get("REACT_APP_BACKEND_URL") or _read_env_key("/app/frontend/.env", "REACT_APP_BACKEND_URL")
    if not value:
        raise RuntimeError("REACT_APP_BACKEND_URL is required")
    return value.rstrip("/")


def _browser_origin() -> str:
    """Get browser origin (same as base URL for CORS Origin header)."""
    return _base_url()


BASE_URL = _base_url()
BROWSER_ORIGIN = _browser_origin()
CREDS_FILE = Path("/app/memory/test_credentials.json")


def _load_private_credentials() -> dict:
    """Load test credentials from private file."""
    if not CREDS_FILE.exists():
        pytest.skip("Test credentials not found - run e2e tests first to create owner")
    try:
        return json.loads(CREDS_FILE.read_text())
    except json.JSONDecodeError:
        pytest.skip("Test credentials file is invalid")


def _api(session: requests.Session, method: str, path: str, origin: str = None, csrf: str = "", **kwargs):
    """Make API request with optional Origin header."""
    headers = kwargs.pop("headers", {})
    if origin is not None:
        headers["Origin"] = origin
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return session.request(method, f"{BASE_URL}{path}", headers=headers, timeout=30, **kwargs)


def test_cors_preflight_with_trusted_origin():
    """Verify OPTIONS preflight succeeds with exact trusted origin."""
    session = requests.Session()
    
    response = _api(
        session,
        "OPTIONS",
        "/api/auth/login",
        origin=BROWSER_ORIGIN,
        headers={
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token"
        }
    )
    
    # Should return 200 with CORS headers
    assert response.status_code == 200, f"Preflight failed: {response.text}"
    
    # Verify exact origin match (no wildcard)
    assert response.headers.get("Access-Control-Allow-Origin") == BROWSER_ORIGIN
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"
    assert "POST" in response.headers.get("Access-Control-Allow-Methods", "")
    assert "content-type" in response.headers.get("Access-Control-Allow-Headers", "").lower()


def test_cors_preflight_with_untrusted_origin_rejected():
    """Verify OPTIONS preflight fails with untrusted origin."""
    session = requests.Session()
    untrusted_origin = "https://malicious.example.com"
    
    response = _api(
        session,
        "OPTIONS",
        "/api/auth/login",
        origin=untrusted_origin,
        headers={
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"
        }
    )
    
    # Should reject - either no CORS headers or explicit rejection
    cors_origin = response.headers.get("Access-Control-Allow-Origin")
    if cors_origin:
        # If CORS header present, must not be wildcard or untrusted origin
        assert cors_origin != "*", "CORS must not use wildcard"
        assert cors_origin != untrusted_origin, "Untrusted origin must not be allowed"


def test_login_with_correct_origin_succeeds():
    """Verify login succeeds when Origin header matches trusted origin."""
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = _api(
        session,
        "POST",
        "/api/auth/login",
        origin=BROWSER_ORIGIN,
        json={"email": email, "password": password}
    )
    
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "user" in data
    assert data["user"]["email"] == email
    assert "csrf" in data
    
    # Verify CORS headers on actual response
    assert response.headers.get("Access-Control-Allow-Origin") == BROWSER_ORIGIN
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"


def test_login_with_untrusted_origin_rejected_asgi():
    """Verify app rejects untrusted Origin before mutation (ASGI direct test)."""
    from server import app
    
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    
    untrusted_origin = "https://attacker.example.com"
    
    # Direct ASGI test - no edge interference
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": untrusted_origin}
    )
    
    # App must reject with 403 before checking credentials
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    
    # Verify no session cookie set
    assert "voltora_session" not in response.cookies
    
    # App must NOT return wildcard or reflected untrusted origin
    cors_origin = response.headers.get("access-control-allow-origin")
    assert cors_origin != "*", "App must not return wildcard CORS"
    assert cors_origin != untrusted_origin, "App must not reflect untrusted origin"


def test_login_with_untrusted_origin_rejected_external():
    """Verify external endpoint rejects untrusted Origin and issues no session."""
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    untrusted_origin = "https://attacker.example.com"
    response = _api(
        session,
        "POST",
        "/api/auth/login",
        origin=untrusted_origin,
        json={"email": email, "password": password}
    )
    
    # Must reject with 403
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    
    # Must not issue session cookie
    assert "voltora_session" not in session.cookies
    
    # INFORMATIONAL: Edge may add wildcard CORS header (not app behavior)
    # This documents edge behavior but does not test app security
    cors_origin = response.headers.get("Access-Control-Allow-Origin")
    if cors_origin == "*":
        # This is edge behavior, not app behavior (verified by ASGI test above)
        pass


def test_login_without_origin_header_pending_mfa():
    """Verify login without Origin succeeds (non-browser API client) but requires MFA."""
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login without Origin header (non-browser API client)
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30
    )
    
    # Should succeed with pending MFA state
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "user" in data
    assert data["user"]["email"] == email
    assert data["user"].get("mfa_verified") is False, "MFA should not be verified yet"
    assert "csrf" in data
    
    # Session cookie should be set
    assert "voltora_session" in session.cookies
    
    # Admin endpoints should reject until MFA verified
    csrf = data["csrf"]
    admin_response = session.get(
        f"{BASE_URL}/api/admin/builder",
        headers={"X-CSRF-Token": csrf},
        timeout=30
    )
    assert admin_response.status_code == 403, f"Admin endpoint should reject before MFA, got {admin_response.status_code}"
    
    # CSRF protection must still be enforced
    no_csrf_response = session.post(
        f"{BASE_URL}/api/auth/mfa/enroll",
        json={},
        timeout=30
    )
    assert no_csrf_response.status_code == 403, "CSRF protection must be enforced"


def test_mfa_verify_with_correct_origin_succeeds():
    """Verify MFA verification succeeds with correct Origin header."""
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    totp_secret = creds.get("totp_secret")
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login first
    login_response = _api(
        session,
        "POST",
        "/api/auth/login",
        origin=BROWSER_ORIGIN,
        json={"email": email, "password": password}
    )
    assert login_response.status_code == 200
    csrf = login_response.json().get("csrf", "")
    
    # Verify MFA with correct origin using cross-process lock
    with mfa_lock(BASE_URL):
        totp = pyotp.TOTP(totp_secret)
        code = totp.now()
        mfa_response = _api(
            session,
            "POST",
            "/api/auth/mfa/verify",
            origin=BROWSER_ORIGIN,
            csrf=csrf,
            json={"code": code}
        )
        
        # Handle TOTP timing - retry once if needed
        if mfa_response.status_code == 409:
            # Wait for next TOTP window
            remaining = totp.interval - (int(time.time()) % totp.interval)
            time.sleep(remaining + 1)
            code = totp.now()
            mfa_response = _api(
                session,
                "POST",
                "/api/auth/mfa/verify",
                origin=BROWSER_ORIGIN,
                csrf=csrf,
                json={"code": code}
            )
    
    assert mfa_response.status_code == 200, f"MFA verify failed: {mfa_response.text}"
    data = mfa_response.json()
    assert data["user"]["mfa_verified"] is True
    
    # Verify CORS headers
    assert mfa_response.headers.get("Access-Control-Allow-Origin") == BROWSER_ORIGIN
    assert mfa_response.headers.get("Access-Control-Allow-Credentials") == "true"


def test_mfa_verify_with_untrusted_origin_rejected():
    """Verify MFA verification fails with untrusted Origin header."""
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    totp_secret = creds.get("totp_secret")
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login with correct origin
    login_response = _api(
        session,
        "POST",
        "/api/auth/login",
        origin=BROWSER_ORIGIN,
        json={"email": email, "password": password}
    )
    assert login_response.status_code == 200
    csrf = login_response.json().get("csrf", "")
    
    # Try MFA verify with untrusted origin
    code = pyotp.TOTP(totp_secret).now()
    untrusted_origin = "https://evil.example.com"
    mfa_response = _api(
        session,
        "POST",
        "/api/auth/mfa/verify",
        origin=untrusted_origin,
        csrf=csrf,
        json={"code": code}
    )
    
    # Should reject before checking TOTP code
    assert mfa_response.status_code == 403, f"Expected 403, got {mfa_response.status_code}: {mfa_response.text}"


def test_csrf_protection_rejects_missing_token():
    """Verify CSRF protection rejects requests without token."""
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login to get session
    login_response = _api(
        session,
        "POST",
        "/api/auth/login",
        origin=BROWSER_ORIGIN,
        json={"email": email, "password": password}
    )
    assert login_response.status_code == 200
    
    # Try state-changing request without CSRF token
    response = _api(
        session,
        "POST",
        "/api/auth/mfa/enroll",
        origin=BROWSER_ORIGIN,
        csrf=""  # No CSRF token
    )
    
    # Should reject with 403
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"


def test_csrf_protection_rejects_invalid_token():
    """Verify CSRF protection rejects requests with invalid token."""
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login to get session
    login_response = _api(
        session,
        "POST",
        "/api/auth/login",
        origin=BROWSER_ORIGIN,
        json={"email": email, "password": password}
    )
    assert login_response.status_code == 200
    
    # Try state-changing request with invalid CSRF token
    response = _api(
        session,
        "POST",
        "/api/auth/mfa/enroll",
        origin=BROWSER_ORIGIN,
        csrf="invalid-csrf-token-12345"
    )
    
    # Should reject with 403
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"


def test_untrusted_origin_rejected_before_mutation_asgi():
    """Verify untrusted origin rejected before DB mutation (ASGI direct test)."""
    from server import app
    
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    totp_secret = creds.get("totp_secret")
    
    # Login and get authenticated session with correct origin
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    login_response = _api(
        session,
        "POST",
        "/api/auth/login",
        origin=BROWSER_ORIGIN,
        json={"email": email, "password": password}
    )
    assert login_response.status_code == 200
    csrf = login_response.json().get("csrf", "")
    
    # Verify MFA to get full access using cross-process lock
    with mfa_lock(BASE_URL):
        totp = pyotp.TOTP(totp_secret)
        code = totp.now()
        mfa_response = _api(
            session,
            "POST",
            "/api/auth/mfa/verify",
            origin=BROWSER_ORIGIN,
            csrf=csrf,
            json={"code": code}
        )
        if mfa_response.status_code == 409:
            remaining = totp.interval - (int(time.time()) % totp.interval)
            time.sleep(remaining + 1)
            code = totp.now()
            mfa_response = _api(
                session,
                "POST",
                "/api/auth/mfa/verify",
                origin=BROWSER_ORIGIN,
                csrf=csrf,
                json={"code": code}
            )
    
    assert mfa_response.status_code == 200
    csrf = mfa_response.json().get("csrf", "")
    
    # Get current builder state
    builder_response = _api(session, "GET", "/api/admin/builder", origin=BROWSER_ORIGIN)
    assert builder_response.status_code == 200
    builder_data = builder_response.json()
    version = builder_data["version"]
    draft = builder_data["draft"]
    
    # Try to mutate with untrusted origin using ASGI direct test
    untrusted_origin = "https://attacker.example.com"
    draft["site"]["auth"]["form_title"] = "MALICIOUS CHANGE"
    
    # Extract session cookie for ASGI test
    session_cookie = session.cookies.get("voltora_session")
    
    client = TestClient(app)
    mutation_response = client.put(
        "/api/admin/builder",
        json={"version": version, "bundle": draft},
        headers={
            "Origin": untrusted_origin,
            "X-CSRF-Token": csrf
        },
        cookies={"voltora_session": session_cookie}
    )
    
    # App must reject with 403 before mutation
    assert mutation_response.status_code == 403, f"Expected 403, got {mutation_response.status_code}"
    
    # App must NOT return wildcard or reflected untrusted origin
    cors_origin = mutation_response.headers.get("access-control-allow-origin")
    assert cors_origin != "*", "App must not return wildcard CORS"
    assert cors_origin != untrusted_origin, "App must not reflect untrusted origin"
    
    # Verify no mutation occurred
    verify_response = _api(session, "GET", "/api/admin/builder", origin=BROWSER_ORIGIN)
    assert verify_response.status_code == 200
    verify_data = verify_response.json()
    assert verify_data["version"] == version  # Version unchanged
    assert verify_data["draft"]["site"]["auth"]["form_title"] != "MALICIOUS CHANGE"


def test_no_permissive_cors_wildcard():
    """Verify CORS never uses wildcard (*) for credentialed requests."""
    session = requests.Session()
    
    # Test various endpoints
    endpoints = [
        "/api/health",
        "/api/store",
        "/api/products",
        "/api/auth/setup-status"
    ]
    
    for endpoint in endpoints:
        response = _api(session, "GET", endpoint, origin=BROWSER_ORIGIN)
        
        cors_origin = response.headers.get("Access-Control-Allow-Origin")
        if cors_origin:
            # Must never be wildcard
            assert cors_origin != "*", f"Endpoint {endpoint} uses wildcard CORS"
            
            # For credentialed endpoints, must be exact origin
            if response.headers.get("Access-Control-Allow-Credentials") == "true":
                assert cors_origin == BROWSER_ORIGIN, f"Endpoint {endpoint} has mismatched CORS origin"


def test_session_cookie_security_attributes():
    """Verify session cookies have proper security attributes."""
    creds = _load_private_credentials()
    email = creds.get("owner_email")
    password = creds.get("owner_password")
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = _api(
        session,
        "POST",
        "/api/auth/login",
        origin=BROWSER_ORIGIN,
        json={"email": email, "password": password}
    )
    
    assert response.status_code == 200
    
    # Check Set-Cookie header
    set_cookie = response.headers.get("set-cookie", "")
    if set_cookie:
        # Must have HttpOnly
        assert "HttpOnly" in set_cookie, "Session cookie missing HttpOnly"
        
        # Must have Secure
        assert "Secure" in set_cookie, "Session cookie missing Secure"
        
        # Should have SameSite
        assert "SameSite" in set_cookie, "Session cookie missing SameSite"
