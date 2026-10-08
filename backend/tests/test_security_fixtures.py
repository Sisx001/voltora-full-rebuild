"""Focused security regression fixtures for OAuth and external-action locks."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

import auth_ext
import providers_admin
import ai_tools


def _make_get_request(path: str, query: str, cookie: str = "") -> Request:
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "query_string": query.encode(),
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


class _FakeCollection:
    def __init__(self, by_provider=None, by_email=None):
        self.by_provider = by_provider
        self.by_email = by_email

    async def find_one(self, query, projection=None):
        if "oauth_google" in query:
            return self.by_provider
        if "email" in query:
            return self.by_email
        return None

    async def insert_one(self, payload):
        return SimpleNamespace(inserted_id="x")


class _FakeDb:
    def __init__(self, users):
        self.users = users


def test_oauth_callback_rejects_unverified_identity(monkeypatch):
    """OAuth callback must reject unverified provider identity/sub before login."""
    async def _oauth_config(provider):
        return {"client_id": "cid", "client_secret": "sec"}

    monkeypatch.setattr(auth_ext, "oauth_config", _oauth_config)

    async def _exchange(config, code):
        return {"sub": "", "email": "person@example.com", "name": "Person", "verified": False}

    monkeypatch.setattr(auth_ext, "exchange_google", _exchange)
    async def _optional_user(request):
        return None

    monkeypatch.setattr(auth_ext, "optional_user", _optional_user)
    monkeypatch.setattr(auth_ext, "db", _FakeDb(_FakeCollection()))

    req = _make_get_request(
        "/api/auth/oauth/google/callback",
        "state=abc&code=ok",
        "voltora_oauth=google:abc",
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_ext.oauth_callback("google", req, Response()))
    assert exc.value.status_code == 403
    assert "verified provider identity" in str(exc.value.detail)


def test_oauth_callback_rejects_authenticated_auto_link(monkeypatch):
    """Authenticated sessions must not auto-link social identities."""
    async def _oauth_config(provider):
        return {"client_id": "cid", "client_secret": "sec"}

    monkeypatch.setattr(auth_ext, "oauth_config", _oauth_config)

    async def _exchange(config, code):
        return {"sub": "sub-1", "email": "link@example.com", "name": "Link", "verified": True}

    async def _optional_user(request):
        return {"id": "u1", "email": "logged@in.example"}

    monkeypatch.setattr(auth_ext, "exchange_google", _exchange)
    monkeypatch.setattr(auth_ext, "optional_user", _optional_user)
    monkeypatch.setattr(auth_ext, "db", _FakeDb(_FakeCollection()))

    req = _make_get_request(
        "/api/auth/oauth/google/callback",
        "state=abc&code=ok",
        "voltora_oauth=google:abc",
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_ext.oauth_callback("google", req, Response()))
    assert exc.value.status_code == 409
    assert "Automatic account linking is disabled" in str(exc.value.detail)


def test_oauth_callback_existing_email_conflicts_instead_of_link(monkeypatch):
    """Existing email should return 409 and never auto-link to OAuth identity."""
    async def _oauth_config(provider):
        return {"client_id": "cid", "client_secret": "sec"}

    monkeypatch.setattr(auth_ext, "oauth_config", _oauth_config)

    async def _exchange(config, code):
        return {"sub": "sub-1", "email": "existing@example.com", "name": "Existing", "verified": True}

    async def _optional_user(request):
        return None

    users = _FakeCollection(by_provider=None, by_email={"_id": "mongo-id"})
    monkeypatch.setattr(auth_ext, "exchange_google", _exchange)
    monkeypatch.setattr(auth_ext, "optional_user", _optional_user)
    monkeypatch.setattr(auth_ext, "db", _FakeDb(users))

    req = _make_get_request(
        "/api/auth/oauth/google/callback",
        "state=abc&code=ok",
        "voltora_oauth=google:abc",
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_ext.oauth_callback("google", req, Response()))
    assert exc.value.status_code == 409
    assert "already exists" in str(exc.value.detail)


def test_oauth_callback_blocks_staff_and_banned_users(monkeypatch):
    """OAuth login should reject staff role and active bans."""
    async def _oauth_config(provider):
        return {"client_id": "cid", "client_secret": "sec"}

    monkeypatch.setattr(auth_ext, "oauth_config", _oauth_config)

    async def _exchange(config, code):
        return {"sub": "sub-1", "email": "staff@example.com", "name": "Staff", "verified": True}

    async def _optional_user(request):
        return None

    monkeypatch.setattr(auth_ext, "exchange_google", _exchange)
    monkeypatch.setattr(auth_ext, "optional_user", _optional_user)

    staff_user = {
        "id": "u1",
        "email": "staff@example.com",
        "role": "owner",
        "disabled": False,
    }
    monkeypatch.setattr(auth_ext, "db", _FakeDb(_FakeCollection(by_provider=staff_user, by_email=None)))
    req = _make_get_request(
        "/api/auth/oauth/google/callback",
        "state=abc&code=ok",
        "voltora_oauth=google:abc",
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_ext.oauth_callback("google", req, Response()))
    assert exc.value.status_code == 403
    assert "Staff must sign in" in str(exc.value.detail)

    banned_user = {
        "id": "u2",
        "email": "banned@example.com",
        "role": "customer",
        "disabled": False,
        "ban": {"active": True},
    }
    monkeypatch.setattr(auth_ext, "db", _FakeDb(_FakeCollection(by_provider=banned_user, by_email=None)))
    with pytest.raises(HTTPException) as exc2:
        asyncio.run(auth_ext.oauth_callback("google", req, Response()))
    assert exc2.value.status_code == 403
    assert "unavailable" in str(exc2.value.detail)


def test_facebook_identity_is_unverified(monkeypatch):
    """Facebook profile email presence must not be treated as verified ownership."""

    class _Resp:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            if "oauth/access_token" in url:
                return _Resp({"access_token": "abc"})
            return _Resp({"id": "fb-sub", "name": "FB User", "email": "fb@example.com"})

    monkeypatch.setattr(auth_ext.httpx, "AsyncClient", lambda timeout=20: _Client())
    result = asyncio.run(auth_ext.exchange_facebook({"client_id": "cid", "client_secret": "sec"}, "code"))
    assert result["sub"] == "fb-sub"
    assert result["verified"] is False


def _rsa_artifacts():
    cryptography = pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = "unit-kid"
    return private_key, jwk


def _stub_apple_jwks(monkeypatch, jwk):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"keys": [jwk]}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            return _Resp()

    monkeypatch.setattr(auth_ext.httpx, "AsyncClient", lambda timeout=20, follow_redirects=False: _Client())


def test_exchange_apple_accepts_rs256_and_handles_email_verified_false(monkeypatch):
    """Apple token should be RS256-verified and email_verified='false' must stay False."""
    private_key, jwk = _rsa_artifacts()
    _stub_apple_jwks(monkeypatch, jwk)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "iss": "https://appleid.apple.com",
        "aud": "client-123",
        "sub": "apple-sub-1",
        "email": "apple@example.com",
        "email_verified": "false",
        "iat": now_ts,
        "exp": now_ts + 300,
    }
    token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "unit-kid"})
    result = asyncio.run(auth_ext.exchange_apple({"client_id": "client-123"}, token))

    assert result["sub"] == "apple-sub-1"
    assert result["verified"] is False


@pytest.mark.parametrize(
    "payload_overrides,config_overrides,alg,secret",
    [
        ({"iss": "https://wrong-issuer.example"}, {}, "RS256", None),
        ({"aud": "wrong-aud"}, {}, "RS256", None),
        ({"exp": int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())}, {}, "RS256", None),
        ({}, {}, "HS256", "shared-secret"),
    ],
)
def test_exchange_apple_rejects_bad_tokens(monkeypatch, payload_overrides, config_overrides, alg, secret):
    """Apple verification must reject wrong issuer/audience/expiry/algorithm."""
    private_key, jwk = _rsa_artifacts()
    _stub_apple_jwks(monkeypatch, jwk)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "iss": "https://appleid.apple.com",
        "aud": "client-123",
        "sub": "apple-sub-1",
        "email": "apple@example.com",
        "email_verified": "true",
        "iat": now_ts,
        "exp": now_ts + 300,
    }
    payload.update(payload_overrides)
    config = {"client_id": "client-123", **config_overrides}

    if alg == "RS256":
        token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "unit-kid"})
    else:
        token = jwt.encode(payload, secret, algorithm="HS256", headers={"kid": "unit-kid"})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_ext.exchange_apple(config, token))
    assert exc.value.status_code == 400
    assert "could not be verified" in str(exc.value.detail)


def test_providers_admin_mock_provider_rejected():
    """Mock provider should be rejected with 404, not operational."""
    with pytest.raises(HTTPException) as mock_exc:
        asyncio.run(providers_admin.save_provider(
            "payment",
            "mock",
            providers_admin.ProviderSave(credentials={}, config={}, sandbox=True, enabled=False),
            channel="",
            user={"id": "u", "name": "U", "role": "owner"},
        ))
    assert mock_exc.value.status_code == 404
    assert "Test doubles are not operational providers" in str(mock_exc.value.detail)


def test_providers_admin_real_disabled_config_saves_allowed(monkeypatch):
    """Real provider disabled config save should succeed (local-only, no external call)."""
    # Stub DB and audit to avoid Motor event loop issues
    from unittest.mock import AsyncMock, MagicMock
    
    fake_db = MagicMock()
    fake_db.provider_configs.find_one = AsyncMock(return_value=None)
    fake_db.provider_configs.insert_one = AsyncMock(return_value=MagicMock(inserted_id='test-id'))
    fake_db.audit_logs.insert_one = AsyncMock()
    
    monkeypatch.setattr('provider_configuration.db', fake_db)
    monkeypatch.setattr('provider_configuration.audit', AsyncMock())
    monkeypatch.setattr('provider_configuration.seal', lambda x: f'sealed:{x}')
    
    result = asyncio.run(providers_admin.save_provider(
        "payment",
        "sslcommerz",
        providers_admin.ProviderSave(
            credentials={"store_id": "test", "store_passwd": "test"},
            config={},
            sandbox=True,
            enabled=False,  # Disabled config is local-only
            expected_version=0,
        ),
        channel="",
        user={"id": "u", "name": "U", "role": "owner"},
    ))
    assert result["version"] == 1
    assert result["enabled"] is False
    assert "Configuration saved locally" in result["message"]


def test_providers_admin_actions_blocked_when_external_actions_locked(monkeypatch):
    """Provider verify/action/enable must hard-fail when external actions locked."""
    from unittest.mock import AsyncMock, MagicMock
    
    # Action requires external actions - expects 503 from require_external_actions()
    with pytest.raises(HTTPException) as action_exc:
        asyncio.run(providers_admin.run_provider_action(
            "infra",
            "cloudflare",
            "purge_cache",
            providers_admin.InfraAction(params={}),
            user={"id": "u", "name": "U", "role": "owner"},
        ))
    assert action_exc.value.status_code == 503

    # Enable requires external actions - stub DB to avoid Motor event loop issues
    fake_db = MagicMock()
    fake_db.provider_configs.find_one = AsyncMock(return_value=None)
    fake_db.provider_configs.insert_one = AsyncMock(return_value=MagicMock(inserted_id='test-id'))
    fake_db.audit_logs.insert_one = AsyncMock()
    
    monkeypatch.setattr('provider_configuration.db', fake_db)
    monkeypatch.setattr('provider_configuration.audit', AsyncMock())
    monkeypatch.setattr('provider_configuration.seal', lambda x: f'sealed:{x}')
    
    with pytest.raises(HTTPException) as enable_exc:
        asyncio.run(providers_admin.save_provider(
            "payment",
            "sslcommerz",
            providers_admin.ProviderSave(
                credentials={"store_id": "test", "store_passwd": "test"},
                config={},
                sandbox=True,
                enabled=True,  # Trying to enable
                expected_version=0,
            ),
            channel="",
            user={"id": "u", "name": "U", "role": "owner"},
        ))
    # require_external_actions() returns 503, not 403
    assert enable_exc.value.status_code == 503
    assert "External actions are locked" in str(enable_exc.value.detail)


def test_ai_approve_action_blocked_when_external_actions_locked():
    """AI approval endpoint must reject while external actions remain locked."""
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ai_tools.approve_action("proposal-id", user={"id": "u", "name": "U"}))
    assert exc.value.status_code == 503
