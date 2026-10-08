"""Critical backend integration tests for VOLTORA staged rebuild flows."""
import json
import os
import time
import uuid
from urllib.parse import urlparse
from pathlib import Path

import pyotp
import pytest
import requests

# Import MFA lock helper for cross-process synchronization
from tests.test_mfa_lock import mfa_lock


def _read_env_key(path: str, key: str) -> str:
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
    value = os.environ.get("REACT_APP_BACKEND_URL") or _read_env_key("/app/frontend/.env", "REACT_APP_BACKEND_URL")
    if not value:
        raise RuntimeError("REACT_APP_BACKEND_URL is required")
    return value.rstrip("/")


BASE_URL = _base_url()
CREDS_FILE = Path("/app/memory/test_credentials.json")
CREDS_MD_FILE = Path("/app/memory/test_credentials.md")


def _api(session: requests.Session, method: str, path: str, csrf: str = "", **kwargs):
    headers = kwargs.pop("headers", {})
    # Always send Origin header matching browser origin for CORS validation
    if "Origin" not in headers:
        headers["Origin"] = BASE_URL
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return session.request(method, f"{BASE_URL}{path}", headers=headers, timeout=30, **kwargs)


def _save_private_credentials(payload: dict):
    CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(json.dumps(payload, indent=2))
    
    # Also write to test_credentials.md for frontend agent
    md_content = f"""# Private isolated development test accounts

## Owner Account (Created via Setup API)
- **Email**: {payload.get('owner_email', 'N/A')}
- **Password**: {payload.get('owner_password', 'N/A')}
- **TOTP Secret**: {payload.get('totp_secret', 'N/A')}

## Test Customer Accounts
"""
    if 'customer_accounts' in payload:
        for i, customer in enumerate(payload['customer_accounts'], 1):
            md_content += f"\n### Customer {i}\n"
            md_content += f"- **Email**: {customer.get('email', 'N/A')}\n"
            md_content += f"- **Password**: {customer.get('password', 'N/A')}\n"
    
    md_content += "\n**Note**: These credentials are for isolated testing only. Never reuse archived credentials.\n"
    CREDS_MD_FILE.write_text(md_content)


def _load_private_credentials() -> dict:
    if not CREDS_FILE.exists():
        return {}
    try:
        return json.loads(CREDS_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def _wait_next_totp_step(secret: str):
    totp = pyotp.TOTP(secret)
    remaining = totp.interval - (int(time.time()) % totp.interval)
    time.sleep(remaining + 1)


def _owner_setup_key() -> str:
    # First try backend/.env, then fall back to .env.local
    key = _read_env_key("/app/backend/.env", "OWNER_SETUP_KEY")
    if not key:
        key = os.environ.get("OWNER_SETUP_KEY") or _read_env_key("/app/backend/.env.local", "OWNER_SETUP_KEY")
    return key


def _login_with_mfa(email: str, password: str, secret: str):
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    login = _api(session, "POST", "/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    login_data = login.json()
    csrf = login_data.get("csrf", "")

    user = login_data.get("user", {})
    if user.get("requires_mfa"):
        # Use cross-process lock to prevent concurrent TOTP consumption
        with mfa_lock(BASE_URL):
            totp = pyotp.TOTP(secret)
            code = totp.now()
            verify = _api(session, "POST", "/api/auth/mfa/verify", csrf=csrf, json={"code": code})
            if verify.status_code == 409:
                # Wait for next TOTP window
                remaining = totp.interval - (int(time.time()) % totp.interval)
                time.sleep(remaining + 1)
                code = totp.now()
                verify = _api(session, "POST", "/api/auth/mfa/verify", csrf=csrf, json={"code": code})
            assert verify.status_code == 200, verify.text
            csrf = verify.json().get("csrf", "")

    return session, csrf


@pytest.fixture(scope="session")
def context():
    """Auth and workspace setup flow including owner creation + MFA bootstrap."""
    data = {
        "base_url": BASE_URL,
        "created_owner": False,
    }

    anon = requests.Session()
    anon.headers.update({"Content-Type": "application/json"})
    status = _api(anon, "GET", "/api/auth/setup-status")
    assert status.status_code == 200
    status_body = status.json()
    assert isinstance(status_body.get("required"), bool)
    data["setup_required_initial"] = status_body["required"]

    key = _owner_setup_key()
    assert key, "OWNER_SETUP_KEY is required"

    if status_body["required"]:
        email = f"qa.owner.{uuid.uuid4().hex[:10]}@example.com"
        password = f"VoltoraQA!{uuid.uuid4().hex[:14]}"
        name = "QA Owner"

        invalid = _api(
            anon,
            "POST",
            "/api/auth/setup",
            json={"name": name, "email": email, "password": password, "setup_key": "invalid-key"},
        )
        data["invalid_setup_status"] = invalid.status_code

        setup_session = requests.Session()
        setup_session.headers.update({"Content-Type": "application/json"})
        setup = _api(
            setup_session,
            "POST",
            "/api/auth/setup",
            json={"name": name, "email": email, "password": password, "setup_key": key},
        )
        assert setup.status_code == 200, setup.text
        setup_body = setup.json()
        csrf = setup_body.get("csrf", "")

        # Before MFA verification, admin routes are expected to block with 403.
        mfa_guard = _api(setup_session, "GET", "/api/admin/builder")
        data["mfa_guard_status"] = mfa_guard.status_code

        enroll = _api(setup_session, "POST", "/api/auth/mfa/enroll", csrf=csrf)
        assert enroll.status_code == 200, enroll.text
        secret = enroll.json().get("secret", "")
        assert secret

        # Use cross-process lock for MFA verification during setup
        with mfa_lock(BASE_URL):
            code = pyotp.TOTP(secret).now()
            verify = _api(setup_session, "POST", "/api/auth/mfa/verify", csrf=csrf, json={"code": code})
            assert verify.status_code == 200, verify.text
            verify_body = verify.json()
            assert verify_body["user"]["mfa_verified"] is True

        replay = _api(setup_session, "POST", "/api/auth/mfa/verify", csrf=verify_body["csrf"], json={"code": code})
        data["mfa_replay_status"] = replay.status_code

        duplicate = _api(
            anon,
            "POST",
            "/api/auth/setup",
            json={"name": "Another", "email": f"dup.{uuid.uuid4().hex[:6]}@example.com", "password": "DuplicatedPass!1234", "setup_key": key},
        )
        data["duplicate_setup_status"] = duplicate.status_code

        _save_private_credentials({"owner_email": email, "owner_password": password, "totp_secret": secret})
        data["created_owner"] = True
        data["set_cookie_header"] = setup.headers.get("set-cookie", "")
    else:
        stored = _load_private_credentials()
        if not stored:
            pytest.skip("Owner already exists and /app/memory/test_credentials.json is missing")

    creds = _load_private_credentials()
    assert creds.get("owner_email") and creds.get("owner_password") and creds.get("totp_secret")

    auth_session, csrf = _login_with_mfa(creds["owner_email"], creds["owner_password"], creds["totp_secret"])
    data["auth_session"] = auth_session
    data["csrf"] = csrf
    data["owner_email"] = creds["owner_email"]
    return data


def test_auth_security_and_route_guards(context):
    """Auth and isolation guarantees: setup, cookies, private routes, demo lock."""
    anon = requests.Session()
    anon.headers.update({"Content-Type": "application/json"})

    private = _api(anon, "GET", "/api/admin/builder")
    assert private.status_code == 401

    setup_status = _api(anon, "GET", "/api/auth/setup-status")
    assert setup_status.status_code == 200
    assert setup_status.json()["required"] is False

    demo = _api(anon, "POST", "/api/demo/start", json={"role": "owner"})
    assert demo.status_code == 404

    spoof = requests.Session()
    spoof.cookies.set("voltora_workspace", "d0123456789abcdef0123456", domain=urlparse(BASE_URL).hostname, path="/")
    spoof_resp = _api(spoof, "GET", "/api/environment")
    assert spoof_resp.status_code == 401

    session = context["auth_session"]
    me = _api(session, "GET", "/api/auth/session")
    assert me.status_code == 200
    me_data = me.json()
    assert me_data["user"]["email"] == context["owner_email"]
    assert isinstance(me_data.get("csrf"), str)

    set_cookie = context.get("set_cookie_header", "")
    if set_cookie:
        assert "voltora_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "Secure" in set_cookie

    if context.get("created_owner"):
        assert context.get("invalid_setup_status") == 403
        assert context.get("mfa_guard_status") == 403
        assert context.get("duplicate_setup_status") == 409
        assert context.get("mfa_replay_status") in (400, 409)


def test_builder_draft_publish_and_conflict(context):
    """Atomic builder flow: save draft, publish, conflict handling, revisions."""
    session, csrf = context["auth_session"], context["csrf"]

    pre_store = _api(session, "GET", "/api/store")
    assert pre_store.status_code == 200
    live_before = pre_store.json()
    old_form_title = live_before["site"]["auth"].get("form_title", "")

    builder = _api(session, "GET", "/api/admin/builder")
    assert builder.status_code == 200
    builder_data = builder.json()
    version = builder_data["version"]
    draft = builder_data["draft"]

    marker = f"QA Login {uuid.uuid4().hex[:6]}"
    draft["site"]["auth"]["form_title"] = marker

    save = _api(session, "PUT", "/api/admin/builder", csrf=csrf, json={"version": version, "bundle": draft})
    assert save.status_code == 200, save.text
    new_version = save.json()["version"]

    stale_save = _api(session, "PUT", "/api/admin/builder", csrf=csrf, json={"version": version, "bundle": draft})
    assert stale_save.status_code == 409

    mid_store = _api(session, "GET", "/api/store")
    assert mid_store.status_code == 200
    assert mid_store.json()["site"]["auth"].get("form_title", "") == old_form_title

    publish = _api(session, "POST", "/api/admin/builder/publish", csrf=csrf, json={"version": new_version, "summary": "QA publish auth title"})
    assert publish.status_code == 200, publish.text

    publish_again = _api(session, "POST", "/api/admin/builder/publish", csrf=csrf, json={"version": new_version + 1, "summary": "duplicate"})
    assert publish_again.status_code == 409

    post_store = _api(session, "GET", "/api/store")
    assert post_store.status_code == 200
    assert post_store.json()["site"]["auth"].get("form_title") == marker

    revisions = _api(session, "GET", "/api/admin/builder/revisions")
    assert revisions.status_code == 200
    rows = revisions.json()
    assert isinstance(rows, list) and len(rows) >= 1


def test_builder_pages_restore_and_rollback(context):
    """Page creation + release history restore/rollback without touching commerce state."""
    session, csrf = context["auth_session"], context["csrf"]

    builder = _api(session, "GET", "/api/admin/builder")
    assert builder.status_code == 200
    data = builder.json()
    version = data["version"]

    slug = f"qa-page-{uuid.uuid4().hex[:6]}"
    page_payload = {
        "title": "QA Page",
        "slug": slug,
        "seo_title": "QA Page",
        "seo_description": "QA validation page",
        "indexable": True,
        "sections": [{"id": f"intro-{uuid.uuid4().hex[:6]}", "type": "text", "title": "QA Heading", "subtitle": "QA Subtitle", "enabled": True}],
    }
    create_page = _api(session, "POST", "/api/admin/pages", csrf=csrf, json=page_payload)
    assert create_page.status_code == 200, create_page.text

    refreshed = _api(session, "GET", "/api/admin/builder")
    assert refreshed.status_code == 200
    v2 = refreshed.json()["version"]
    publish = _api(session, "POST", "/api/admin/builder/publish", csrf=csrf, json={"version": v2, "summary": "QA publish custom page"})
    assert publish.status_code == 200, publish.text

    public_page = _api(requests.Session(), "GET", f"/api/pages/{slug}")
    assert public_page.status_code == 200
    assert public_page.json()["slug"] == slug

    revisions = _api(session, "GET", "/api/admin/builder/revisions")
    assert revisions.status_code == 200
    rows = revisions.json()
    assert len(rows) >= 2

    workspace = _api(session, "GET", "/api/admin/builder")
    assert workspace.status_code == 200
    current = workspace.json()
    active = current["active_revision"]
    target = next((r for r in rows if r["id"] != active), None)
    assert target is not None

    restore = _api(session, "POST", "/api/admin/builder/restore", csrf=csrf, json={"version": current["version"], "revision_id": target["id"], "summary": "QA restore draft"})
    assert restore.status_code == 200, restore.text

    latest = _api(session, "GET", "/api/admin/builder")
    assert latest.status_code == 200
    rollback = _api(session, "POST", "/api/admin/builder/rollback", csrf=csrf, json={"version": latest.json()["version"], "revision_id": target["id"], "summary": "QA rollback live"})
    assert rollback.status_code == 200, rollback.text


def test_mira_config_persistence_and_conflict(context):
    """Mira settings visual config, optimistic locking, and persistence checks."""
    session, csrf = context["auth_session"], context["csrf"]

    read = _api(session, "GET", "/api/admin/mira")
    assert read.status_code == 200
    payload = read.json()
    version = payload["version"]
    settings = payload["settings"]
    assert payload["generation_enabled"] is False

    settings["title"] = f"Mira QA {uuid.uuid4().hex[:4]}"
    settings["greeting"] = "Hello from QA validation"
    settings["accent"] = "#A1B2C3"
    settings["position"] = "bottom_left"
    settings["personality"] = "concise"
    settings["language"] = "bn"
    settings["knowledge"] = "QA persisted business knowledge"
    settings["provider"] = "anthropic"
    settings["product_search"] = True
    settings["policy_lookup"] = True
    settings["order_status"] = False

    save = _api(session, "PUT", "/api/admin/mira", csrf=csrf, json={"version": version, "settings": settings})
    assert save.status_code == 200, save.text
    after = save.json()
    assert after["version"] == version + 1
    assert after["settings"]["title"] == settings["title"]

    stale = _api(session, "PUT", "/api/admin/mira", csrf=csrf, json={"version": version, "settings": settings})
    assert stale.status_code == 409

    reread = _api(session, "GET", "/api/admin/mira")
    assert reread.status_code == 200
    assert reread.json()["settings"]["greeting"] == "Hello from QA validation"


def test_external_actions_lock_and_basic_commerce(context):
    """External integration lock + core storefront quote/checkout idempotency."""
    session, csrf = context["auth_session"], context["csrf"]

    ai_block = _api(
        session,
        "PUT",
        "/api/admin/ai",
        csrf=csrf,
        json={"api_key": "x", "base_url": "https://example.invalid", "model": "x", "daily_requests": 1, "prompt": "x"},
    )
    assert ai_block.status_code == 403

    provider_block = _api(session, "POST", "/api/admin/providers/test-route", csrf=csrf, json={"x": 1})
    assert provider_block.status_code == 403

    oauth_block = _api(session, "POST", "/api/admin/oauth/test-route", csrf=csrf, json={"x": 1})
    assert oauth_block.status_code == 403

    products = _api(requests.Session(), "GET", "/api/products?limit=1")
    assert products.status_code == 200
    items = products.json().get("items", [])
    assert items, "No published products returned"
    first = items[0]
    variant = first["variants"][0]

    store = _api(requests.Session(), "GET", "/api/store")
    assert store.status_code == 200
    shipping = next((s for s in store.json()["settings"]["shipping"] if s.get("enabled")), None)
    assert shipping is not None

    quote_payload = {
        "items": [{"product_id": first["id"], "variant_id": variant["id"], "quantity": 1, "expected_price": variant["price"]}],
        "shipping_id": shipping["id"],
        "coupon": "",
    }
    quote = _api(requests.Session(), "POST", "/api/cart/quote", json=quote_payload)
    assert quote.status_code == 200, quote.text
    quote_data = quote.json()
    assert quote_data["total"] >= 0
    assert quote_data["currency"]

    idem = f"qa-idem-{uuid.uuid4().hex[:24]}"
    checkout_payload = {
        **quote_payload,
        "name": "QA Customer",
        "email": f"customer.{uuid.uuid4().hex[:8]}@example.com",
        "phone": "01700000000",
        "address": "QA street",
        "city": "Dhaka",
        "postal_code": "1207",
        "payment_method": "cod",
        "notes": "",
        "terms": True,
        "marketing": False,
    }
    checkout = _api(requests.Session(), "POST", "/api/checkout", json=checkout_payload, headers={"Idempotency-Key": idem})
    assert checkout.status_code == 200, checkout.text
    order = checkout.json()
    assert order["id"]
    assert order["payment_status"] == "unpaid"

    replay_same = _api(requests.Session(), "POST", "/api/checkout", json=checkout_payload, headers={"Idempotency-Key": idem})
    assert replay_same.status_code == 200
    assert replay_same.json()["id"] == order["id"]

    changed = dict(checkout_payload)
    changed["notes"] = "different"
    replay_diff = _api(requests.Session(), "POST", "/api/checkout", json=changed, headers={"Idempotency-Key": idem})
    assert replay_diff.status_code == 409
