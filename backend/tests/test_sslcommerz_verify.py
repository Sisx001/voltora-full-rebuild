"""Regression tests for SSLCommerz verification strict matching logic."""
import sys
import asyncio
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.base import ProviderError
from providers.payments.sslcommerz import SSLCommerz


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, body):
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return _FakeResponse(self.body)


def test_sslcommerz_verify_accepts_exact_match(monkeypatch):
    """Exact tran_id + amount(minor units) + currency should pass as paid."""
    body = {"status": "VALID", "amount": "123.45", "tran_id": "tx-abc", "currency": "BDT"}

    import providers.payments.sslcommerz as ssl_module

    monkeypatch.setattr(ssl_module.httpx, "AsyncClient", lambda timeout=20: _FakeClient(body))
    provider = SSLCommerz()
    status = asyncio.run(
        provider.verify(
            transaction={"id": "tx-abc", "amount": 12345, "currency": "BDT", "sandbox": True},
            credentials={"store_id": "s", "store_passwd": "p"},
            params={"val_id": "val-1"},
        )
    )
    assert status == "paid"


@pytest.mark.parametrize(
    "body",
    [
        {"status": "VALID", "amount": "123.45", "tran_id": "wrong-id", "currency": "BDT"},
        {"status": "VALID", "amount": "999.99", "tran_id": "tx-abc", "currency": "BDT"},
        {"status": "VALID", "amount": "123.45", "tran_id": "tx-abc", "currency": "USD"},
    ],
)
def test_sslcommerz_verify_rejects_mismatch(monkeypatch, body):
    """Any mismatch in tran_id/amount/currency must raise ProviderError."""
    import providers.payments.sslcommerz as ssl_module

    monkeypatch.setattr(ssl_module.httpx, "AsyncClient", lambda timeout=20: _FakeClient(body))
    provider = SSLCommerz()
    with pytest.raises(ProviderError):
        asyncio.run(
            provider.verify(
                transaction={"id": "tx-abc", "amount": 12345, "currency": "BDT", "sandbox": True},
                credentials={"store_id": "s", "store_passwd": "p"},
                params={"val_id": "val-1"},
            )
        )
