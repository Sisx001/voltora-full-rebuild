"""Cross-process MFA test synchronization helper.

Provides file-based locking to prevent concurrent TOTP code consumption
across parallel test workers, avoiding 409 replay errors.
"""
import hashlib
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

import pyotp
from filelock import FileLock


def _get_lock_path(base_url: str) -> Path:
    """Get lock file path based on base URL hash (no secrets)."""
    url_hash = hashlib.sha256(base_url.encode()).hexdigest()[:16]
    return Path(f"/tmp/voltora_mfa_test_lock_{url_hash}.lock")


@contextmanager
def mfa_lock(base_url: str, timeout: int = 60):
    """Cross-process lock for MFA operations.
    
    Args:
        base_url: Test base URL (for lock file naming)
        timeout: Lock acquisition timeout in seconds
    
    Usage:
        with mfa_lock(BASE_URL):
            code = pyotp.TOTP(secret).now()
            response = verify_mfa(code)
    """
    lock_file = _get_lock_path(base_url)
    lock = FileLock(str(lock_file), timeout=timeout)
    
    with lock:
        yield


def generate_and_verify_mfa(
    secret: str,
    verify_fn: Callable[[str], tuple[int, dict]],
    base_url: str,
    max_retries: int = 1
) -> tuple[int, dict]:
    """Generate TOTP code and verify with cross-process locking.
    
    Args:
        secret: TOTP secret
        verify_fn: Function that takes code and returns (status_code, response_data)
        base_url: Test base URL (for lock file naming)
        max_retries: Number of retries on 409 (default 1)
    
    Returns:
        Tuple of (status_code, response_data)
    
    Usage:
        def verify(code):
            resp = session.post("/api/auth/mfa/verify", json={"code": code})
            return resp.status_code, resp.json()
        
        status, data = generate_and_verify_mfa(secret, verify, BASE_URL)
    """
    with mfa_lock(base_url):
        totp = pyotp.TOTP(secret)
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                # Wait for next TOTP window
                remaining = totp.interval - (int(time.time()) % totp.interval)
                time.sleep(remaining + 1)
            
            code = totp.now()
            status_code, response_data = verify_fn(code)
            
            if status_code != 409:
                return status_code, response_data
        
        # Return last attempt result
        return status_code, response_data
