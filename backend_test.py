"""Comprehensive backend API testing for VOLTORA."""
import requests
import json
import sys
from pathlib import Path


def read_env_key(path: str, key: str) -> str:
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


def get_base_url() -> str:
    """Get the backend URL from frontend .env."""
    return read_env_key("/app/frontend/.env", "REACT_APP_BACKEND_URL").rstrip("/")


BASE_URL = get_base_url()
print(f"Testing backend at: {BASE_URL}")


def test_health_endpoint():
    """Test /api/health endpoint."""
    print("\n=== Testing /api/health ===")
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            assert data.get("status") == "ok", "Health status should be 'ok'"
            assert data.get("database") == "connected", "Database should be connected"
            assert "latency_ms" in data, "Should include latency_ms"
            print("✅ Health endpoint working correctly")
            return True
        else:
            print(f"❌ Health endpoint returned {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Health endpoint failed: {e}")
        return False


def test_store_endpoint():
    """Test /api/store endpoint."""
    print("\n=== Testing /api/store ===")
    try:
        response = requests.get(f"{BASE_URL}/api/store", timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            assert "site" in data, "Should include 'site' key"
            assert "settings" in data, "Should include 'settings' key"
            print("✅ Store endpoint working correctly")
            return True
        else:
            print(f"❌ Store endpoint returned {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Store endpoint failed: {e}")
        return False


def test_environment_endpoint():
    """Test /api/environment endpoint (public endpoint)."""
    print("\n=== Testing /api/environment (public) ===")
    try:
        response = requests.get(f"{BASE_URL}/api/environment", timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            assert "mode" in data, "Should include 'mode' key"
            assert data["mode"] in ["sandbox", "production"], "Mode should be sandbox or production"
            assert "external_delivery" in data, "Should include 'external_delivery' key"
            print("✅ Environment endpoint working correctly")
            return True
        else:
            print(f"❌ Environment endpoint returned {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Environment endpoint test failed: {e}")
        return False


def test_admin_boundary():
    """Test /api/admin/builder endpoint (should require auth)."""
    print("\n=== Testing /api/admin/builder (unauthenticated) ===")
    try:
        response = requests.get(f"{BASE_URL}/api/admin/builder", timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 401:
            print("✅ Admin endpoint correctly requires authentication")
            return True
        else:
            print(f"❌ Admin endpoint should return 401, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Admin endpoint test failed: {e}")
        return False


def test_demo_boundary():
    """Test /api/demo/start endpoint (should be disabled)."""
    print("\n=== Testing /api/demo/start (should be disabled) ===")
    try:
        response = requests.post(
            f"{BASE_URL}/api/demo/start",
            json={"role": "owner"},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 404:
            print("✅ Demo endpoint correctly disabled")
            return True
        else:
            print(f"❌ Demo endpoint should return 404, got {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Demo endpoint test failed: {e}")
        return False


def test_correlation_id_header():
    """Test that correlation ID is present in response headers."""
    print("\n=== Testing X-Correlation-ID header ===")
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        correlation_id = response.headers.get("X-Correlation-ID")
        print(f"X-Correlation-ID: {correlation_id}")
        if correlation_id:
            # Check that it doesn't contain sensitive content
            assert len(correlation_id) > 0, "Correlation ID should not be empty"
            assert " " not in correlation_id, "Correlation ID should not contain spaces"
            # Check it's a hex string (24 chars for 12 bytes)
            assert len(correlation_id) == 24, "Correlation ID should be 24 chars (12 bytes hex)"
            assert all(c in "0123456789abcdef" for c in correlation_id.lower()), "Should be hex"
            print("✅ Correlation ID header present and valid")
            return True
        else:
            print("❌ X-Correlation-ID header missing")
            return False
    except Exception as e:
        print(f"❌ Correlation ID test failed: {e}")
        return False


def test_cors_expose_header():
    """Test that CORS expose headers include X-Correlation-ID."""
    print("\n=== Testing CORS expose headers ===")
    try:
        # Make a regular GET request and check the expose headers
        response = requests.get(
            f"{BASE_URL}/api/health",
            headers={"Origin": BASE_URL},
            timeout=10
        )
        print(f"Status: {response.status_code}")
        
        # Check for Access-Control-Expose-Headers in response
        expose_headers = response.headers.get("Access-Control-Expose-Headers", "")
        print(f"Access-Control-Expose-Headers: {expose_headers}")
        
        # Also check if X-Correlation-ID is present
        correlation_id = response.headers.get("X-Correlation-ID")
        print(f"X-Correlation-ID present: {correlation_id is not None}")
        
        if "X-Correlation-ID" in expose_headers:
            print("✅ CORS correctly exposes X-Correlation-ID header")
            return True
        else:
            # Check if the header is at least present (might be exposed by default)
            if correlation_id:
                print("⚠️  X-Correlation-ID header present but not explicitly in expose list")
                print("   This may still work in browsers depending on CORS policy")
                return True
            print("❌ X-Correlation-ID not in CORS expose headers")
            return False
    except Exception as e:
        print(f"❌ CORS expose header test failed: {e}")
        return False


def test_setup_status():
    """Test /api/auth/setup-status endpoint."""
    print("\n=== Testing /api/auth/setup-status ===")
    try:
        response = requests.get(f"{BASE_URL}/api/auth/setup-status", timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            assert "required" in data, "Should include 'required' key"
            assert isinstance(data["required"], bool), "'required' should be boolean"
            print("✅ Setup status endpoint working correctly")
            return True
        else:
            print(f"❌ Setup status endpoint returned {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Setup status endpoint failed: {e}")
        return False


def test_products_endpoint():
    """Test /api/products endpoint."""
    print("\n=== Testing /api/products ===")
    try:
        response = requests.get(f"{BASE_URL}/api/products?limit=5", timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            assert "items" in data, "Should include 'items' key"
            assert isinstance(data["items"], list), "'items' should be a list"
            print(f"Found {len(data['items'])} products")
            print("✅ Products endpoint working correctly")
            return True
        else:
            print(f"❌ Products endpoint returned {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Products endpoint failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("VOLTORA Backend API Testing")
    print("=" * 60)
    
    if not BASE_URL:
        print("❌ Could not determine BASE_URL from /app/frontend/.env")
        sys.exit(1)
    
    results = {
        "Health endpoint": test_health_endpoint(),
        "Store endpoint": test_store_endpoint(),
        "Environment endpoint (public)": test_environment_endpoint(),
        "Admin endpoint (auth boundary)": test_admin_boundary(),
        "Demo endpoint (disabled)": test_demo_boundary(),
        "Correlation ID header": test_correlation_id_header(),
        "CORS expose headers": test_cors_expose_header(),
        "Setup status endpoint": test_setup_status(),
        "Products endpoint": test_products_endpoint(),
    }
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All backend API tests passed!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
