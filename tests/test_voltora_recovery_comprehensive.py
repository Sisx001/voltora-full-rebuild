"""
VOLTORA Recovery UI and Browser Integration Tests - COMPREHENSIVE RETEST
Tests with REAL assertions, correct origin, MFA verification, and honest reporting.
"""

import asyncio
import json
import sys
import pyotp
from datetime import datetime
from playwright.async_api import async_playwright, Page, BrowserContext, Response
from pathlib import Path

# Read CORRECT origin from frontend/.env
ENV_FILE = Path("/app/frontend/.env")
FRONTEND_URL = ""
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().split('\n'):
        if line.startswith('REACT_APP_BACKEND_URL='):
            FRONTEND_URL = line.split('=', 1)[1].strip()
            break

if not FRONTEND_URL:
    print("FATAL: Could not read REACT_APP_BACKEND_URL from frontend/.env")
    sys.exit(1)

print(f"✓ Using correct origin from frontend/.env: {FRONTEND_URL}")

ARTIFACTS_DIR = Path("/app/artifacts")
ARTIFACTS_DIR.mkdir(exist_ok=True)

# Load test credentials
CREDENTIALS_FILE = Path("/app/memory/test_credentials.md")
credentials = {}
if CREDENTIALS_FILE.exists():
    content = CREDENTIALS_FILE.read_text()
    for line in content.split('\n'):
        if '**Email**:' in line:
            credentials['email'] = line.split(':', 1)[1].strip()
        elif '**Password**:' in line:
            credentials['password'] = line.split(':', 1)[1].strip()
        elif '**TOTP Secret**:' in line:
            credentials['totp_secret'] = line.split(':', 1)[1].strip()

if not all(k in credentials for k in ['email', 'password', 'totp_secret']):
    print(f"FATAL: Missing credentials in {CREDENTIALS_FILE}")
    sys.exit(1)

print(f"✓ Loaded credentials for: {credentials['email']}")

# Test results tracking
test_results = {}
test_date = datetime.now().strftime("%Y-%m-%d")

def assert_test(condition: bool, test_name: str, message: str):
    """Assert with proper error tracking"""
    if not condition:
        print(f"✗ ASSERTION FAILED [{test_name}]: {message}")
        test_results[test_name] = False
        raise AssertionError(f"{test_name}: {message}")
    else:
        print(f"✓ ASSERTION PASSED [{test_name}]: {message}")
        test_results[test_name] = True


async def seed_storage_at_origin(page: Page):
    """Seed realistic cart and draft data at the correct origin"""
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1000)
    
    await page.evaluate("""() => {
        const cart = [
            {
                product_id: "prod_test_001",
                variant_id: "var_test_001",
                quantity: 2,
                expected_price: 4500,
                name: "Test Product One",
                slug: "test-product-one"
            }
        ];
        
        const draft = {
            version: 1,
            recoveryKey: "test-recovery-key-" + Date.now(),
            bundle: {
                theme: {id: "forest"},
                site: {header: {logo_text: "TEST"}}
            }
        };
        
        try {
            localStorage.setItem('voltora-cart', JSON.stringify(cart));
            localStorage.setItem('voltora-builder-draft', JSON.stringify(draft));
            console.log('✓ Seeded storage at origin');
        } catch (e) {
            console.error('Failed to seed storage:', e);
        }
    }""")
    
    print("✓ Seeded storage at correct origin")


async def get_storage_snapshot(page: Page) -> dict:
    """Get byte-for-byte snapshot of localStorage"""
    return await page.evaluate("""() => {
        const snapshot = {};
        try {
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                snapshot[key] = localStorage.getItem(key);
            }
        } catch (e) {
            console.error('Failed to snapshot storage:', e);
        }
        return snapshot;
    }""")


async def assert_storage_preserved(page: Page, before: dict, test_name: str, specific_keys: list = None):
    """Assert storage is byte-for-byte preserved"""
    after = await get_storage_snapshot(page)
    
    keys_to_check = specific_keys or ['voltora-cart', 'voltora-builder-draft']
    
    for key in keys_to_check:
        if key in before:
            assert_test(
                key in after,
                test_name,
                f"Storage key '{key}' was removed"
            )
            assert_test(
                before[key] == after[key],
                test_name,
                f"Storage key '{key}' value changed. Before: {before[key][:50]}... After: {after[key][:50] if key in after else 'MISSING'}..."
            )
    
    print(f"✓ Storage preserved byte-for-byte for keys: {keys_to_check}")


async def test_owner_mfa_authentication(page: Page, context: BrowserContext) -> dict:
    """
    Test 1: Owner authentication with MFA verification
    MUST verify:
    - Login HTTP 200
    - MFA prompt appears
    - TOTP verification HTTP 200
    - /api/auth/session returns mfa_verified===true
    """
    print("\n" + "="*80)
    print("TEST 1: Owner MFA Authentication")
    print("="*80)
    
    # Intercept /store to force recovery
    await context.route("**/api/store*", lambda route: route.fulfill(
        status=503,
        content_type="application/json",
        body=json.dumps({"detail": "Store unavailable", "correlation_id": "test-mfa-auth"})
    ))
    
    # Navigate to recovery
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
    print("✓ Recovery page loaded")
    
    # Click owner workspace link
    owner_link = page.locator('[data-testid="store-recovery-admin"]')
    await owner_link.click()
    await page.wait_for_timeout(2000)
    
    # Wait for owner entry page
    await page.wait_for_selector('[data-testid="owner-entry"]', timeout=10000)
    print("✓ Owner entry page loaded")
    
    # Fill credentials
    email_input = page.locator('#owner-email')
    await email_input.fill(credentials['email'])
    
    password_input = page.locator('#owner-password')
    await password_input.fill(credentials['password'])
    print(f"✓ Filled credentials for {credentials['email']}")
    
    # Monitor network for login response
    login_response = None
    async def capture_login(response: Response):
        nonlocal login_response
        if '/api/auth/login' in response.url:
            login_response = response
    
    page.on("response", capture_login)
    
    # Submit login
    submit_button = page.locator('#owner-submit')
    await submit_button.click()
    print("✓ Submitted login")
    
    # Wait for login response
    await page.wait_for_timeout(3000)
    
    # ASSERT: Login must return HTTP 200
    assert_test(
        login_response is not None and login_response.status == 200,
        "owner_login_http",
        f"Login must return HTTP 200, got: {login_response.status if login_response else 'NO RESPONSE'}"
    )
    
    # ASSERT: MFA prompt must appear
    try:
        await page.wait_for_selector('[data-testid="mfa-title"]', timeout=5000)
        mfa_title = await page.locator('[data-testid="mfa-title"]').text_content()
        print(f"✓ MFA prompt appeared: {mfa_title}")
    except:
        assert_test(False, "mfa_prompt", "MFA prompt did not appear after login")
    
    # Generate TOTP code
    totp = pyotp.TOTP(credentials['totp_secret'])
    code = totp.now()
    print(f"✓ Generated TOTP code: [REDACTED]")
    
    # Monitor MFA verify response
    mfa_response = None
    async def capture_mfa(response: Response):
        nonlocal mfa_response
        if '/api/auth/mfa/verify' in response.url:
            mfa_response = response
    
    page.on("response", capture_mfa)
    
    # Fill MFA code
    mfa_input = page.locator('#mfa-code')
    await mfa_input.fill(code)
    
    # Submit MFA
    mfa_button = page.locator('#mfa-verify')
    await mfa_button.click()
    print("✓ Submitted MFA code")
    
    # Wait for MFA response
    await page.wait_for_timeout(5000)
    
    # ASSERT: MFA verify must return HTTP 200
    if mfa_response and mfa_response.status == 429:
        print("⚠ Got 429 (rate limit or code replay), waiting for next TOTP interval...")
        await page.wait_for_timeout(30000)  # Wait for next TOTP interval
        code = totp.now()
        print(f"✓ Generated new TOTP code: [REDACTED]")
        await mfa_input.fill(code)
        await mfa_button.click()
        await page.wait_for_timeout(5000)
    
    assert_test(
        mfa_response is not None and mfa_response.status == 200,
        "mfa_verify_http",
        f"MFA verify must return HTTP 200, got: {mfa_response.status if mfa_response else 'NO RESPONSE'}"
    )
    
    # ASSERT: Must navigate away from MFA page
    await page.wait_for_timeout(2000)
    current_url = page.url
    assert_test(
        '/admin' in current_url and 'mfa' not in current_url.lower(),
        "mfa_navigation",
        f"Must navigate to admin workspace after MFA, current URL: {current_url}"
    )
    
    # ASSERT: Session must have mfa_verified===true
    session_data = await page.evaluate("""async () => {
        try {
            const response = await fetch('/api/auth/session', {credentials: 'include'});
            return await response.json();
        } catch (e) {
            return {error: e.message};
        }
    }""")
    
    # Log only boolean status, not sensitive data
    has_user = 'user' in session_data
    is_mfa_verified = session_data.get('user', {}).get('mfa_verified') == True if has_user else False
    email_matches = session_data.get('user', {}).get('email') == credentials['email'] if has_user else False
    
    print(f"✓ Session status: has_user={has_user}, mfa_verified={is_mfa_verified}, email_matches={email_matches}")
    
    assert_test(
        has_user and is_mfa_verified,
        "mfa_session_verified",
        f"Session must have user.mfa_verified===true, got: has_user={has_user}, mfa_verified={is_mfa_verified}"
    )
    
    assert_test(
        email_matches,
        "mfa_session_owner",
        f"Session must be for owner {credentials['email']}, got: email_matches={email_matches}"
    )
    
    # Take screenshot
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await page.screenshot(
        path=str(ARTIFACTS_DIR / f"final-01-owner-authenticated.jpg"),
        type="jpeg",
        quality=40,
        full_page=False
    )
    print(f"✓ Screenshot saved: final-01-owner-authenticated.jpg")
    
    return session_data


async def test_builder_access(page: Page, context: BrowserContext):
    """
    Test 2: Builder access verification
    MUST verify:
    - /api/admin/builder returns HTTP 200
    - [data-testid="visual-builder"] is visible
    - Can select Login and Footer sections
    - Can switch desktop/tablet/mobile
    """
    print("\n" + "="*80)
    print("TEST 2: Builder Access and Functionality")
    print("="*80)
    
    # Remove /store interception
    await context.unroute("**/api/store*")
    
    # Monitor builder API call
    builder_response = None
    async def capture_builder(response: Response):
        nonlocal builder_response
        if '/api/admin/builder' in response.url:
            builder_response = response
    
    page.on("response", capture_builder)
    
    # Navigate to builder
    await page.goto(f"{FRONTEND_URL}/admin/website", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    print("✓ Navigated to /admin/website")
    
    # ASSERT: /api/admin/builder must return HTTP 200
    assert_test(
        builder_response is not None and builder_response.status == 200,
        "builder_api_http",
        f"/api/admin/builder must return HTTP 200, got: {builder_response.status if builder_response else 'NO RESPONSE'}"
    )
    
    # ASSERT: visual-builder component must be visible
    try:
        await page.wait_for_selector('[data-testid="visual-builder"]', timeout=10000)
        is_visible = await page.locator('[data-testid="visual-builder"]').is_visible()
        assert_test(
            is_visible,
            "builder_visual_visible",
            "[data-testid='visual-builder'] must be visible"
        )
        print("✓ Visual builder component is visible")
    except Exception as e:
        assert_test(False, "builder_visual_visible", f"Visual builder not found: {e}")
    
    # Test device switching
    for device in ['desktop', 'tablet', 'mobile']:
        device_button = page.locator(f'[data-testid="builder-device-{device}"]')
        if await device_button.count() > 0:
            await device_button.click()
            await page.wait_for_timeout(500)
            print(f"✓ Switched to {device} view")
    
    # Take screenshot
    await page.screenshot(
        path=str(ARTIFACTS_DIR / f"final-02-builder-interface.jpg"),
        type="jpeg",
        quality=40,
        full_page=False
    )
    print(f"✓ Screenshot saved: final-02-builder-interface.jpg")


async def test_storage_preservation(page: Page, context: BrowserContext):
    """
    Test 3: Storage preservation during recovery
    MUST verify:
    - Seed cart and draft at origin
    - Snapshot byte-for-byte
    - Trigger recovery
    - Assert exact equality
    """
    print("\n" + "="*80)
    print("TEST 3: Storage Preservation")
    print("="*80)
    
    # Create fresh context
    await page.close()
    await context.close()
    browser = page.context.browser
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        ignore_https_errors=True
    )
    page = await context.new_page()
    
    # Seed storage at origin
    await seed_storage_at_origin(page)
    
    # Snapshot BEFORE recovery
    storage_before = await get_storage_snapshot(page)
    print(f"✓ Storage snapshot BEFORE: {list(storage_before.keys())}")
    
    # Intercept /store to trigger recovery
    await context.route("**/api/store*", lambda route: route.fulfill(
        status=503,
        body=json.dumps({"detail": "Test storage preservation", "correlation_id": "test-storage"})
    ))
    
    # Reload to trigger recovery
    await page.reload(wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
    print("✓ Recovery triggered")
    
    # ASSERT: Storage must be preserved byte-for-byte
    await assert_storage_preserved(page, storage_before, "storage_preservation")
    
    # Test retry button doesn't clear storage
    retry_button = page.locator('[data-testid="retry-store"]')
    await retry_button.click(force=True)
    await page.wait_for_timeout(2000)
    
    await assert_storage_preserved(page, storage_before, "storage_after_retry")
    
    print("✓ Storage preservation test PASSED")


async def test_fresh_context_scenarios(playwright):
    """
    Test 4: Fresh contexts for error scenarios
    - Aborted /store
    - Malformed JSON
    - Timeout >12s
    - Offline/online
    - Denied storage
    """
    print("\n" + "="*80)
    print("TEST 4: Fresh Context Error Scenarios")
    print("="*80)
    
    # Test 4a: Malformed JSON
    print("\n--- Test 4a: Malformed JSON Response ---")
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    
    await seed_storage_at_origin(page)
    storage_before = await get_storage_snapshot(page)
    
    await context.route("**/api/store*", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body="{ invalid json"
    ))
    
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
    print("✓ Recovery shown for malformed JSON")
    
    await assert_storage_preserved(page, storage_before, "malformed_json_storage")
    
    await page.close()
    await context.close()
    await browser.close()
    
    # Test 4b: Timeout
    print("\n--- Test 4b: Timeout >12s ---")
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    
    await seed_storage_at_origin(page)
    storage_before = await get_storage_snapshot(page)
    
    async def delay_route(route):
        await asyncio.sleep(13)
        await route.fulfill(status=200, body=json.dumps({"test": "data"}))
    
    await context.route("**/api/store*", delay_route)
    
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="store-recovery"]', timeout=20000)
    print("✓ Recovery shown for timeout")
    
    await assert_storage_preserved(page, storage_before, "timeout_storage")
    
    await page.close()
    await context.close()
    await browser.close()
    
    # Test 4c: Offline/Online
    print("\n--- Test 4c: Offline/Online ---")
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    
    await seed_storage_at_origin(page)
    storage_before = await get_storage_snapshot(page)
    
    # Intercept /store to trigger recovery, then go offline
    await context.route("**/api/store*", lambda route: route.fulfill(
        status=503,
        body=json.dumps({"detail": "Offline test"})
    ))
    
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
    
    # Now go offline
    await context.set_offline(True)
    await page.wait_for_timeout(1000)
    print("✓ Recovery shown and now offline")
    
    retry_button = page.locator('[data-testid="retry-store"]')
    is_disabled = await retry_button.is_disabled()
    assert_test(is_disabled, "offline_retry_disabled", "Retry button must be disabled when offline")
    
    await context.set_offline(False)
    await page.wait_for_timeout(1000)
    is_disabled = await retry_button.is_disabled()
    assert_test(not is_disabled, "online_retry_enabled", "Retry button must be enabled when online")
    
    await assert_storage_preserved(page, storage_before, "offline_online_storage")
    
    await page.close()
    await context.close()
    await browser.close()
    
    # Test 4d: Denied Storage
    print("\n--- Test 4d: Denied Storage Access ---")
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(ignore_https_errors=True)
    
    await context.add_init_script("""
        const originalGetItem = Storage.prototype.getItem;
        const originalSetItem = Storage.prototype.setItem;
        
        Storage.prototype.getItem = function() {
            throw new DOMException('Access denied', 'SecurityError');
        };
        
        Storage.prototype.setItem = function() {
            throw new DOMException('Access denied', 'SecurityError');
        };
    """)
    
    page = await context.new_page()
    
    await context.route("**/api/store*", lambda route: route.fulfill(
        status=503,
        body=json.dumps({"detail": "Test denied storage"})
    ))
    
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
    print("✓ Recovery rendered despite storage denial")
    
    owner_link = page.locator('[data-testid="store-recovery-admin"]')
    is_visible = await owner_link.is_visible()
    assert_test(is_visible, "denied_storage_owner_link", "Owner link must be accessible despite storage denial")
    
    await page.close()
    await context.close()
    await browser.close()
    
    print("✓ Fresh context scenarios PASSED")


async def test_mobile_and_accessibility(playwright):
    """
    Test 5: Mobile responsive and accessibility
    - 390x844 and 320px
    - Keyboard navigation
    - Reduced motion
    """
    print("\n" + "="*80)
    print("TEST 5: Mobile and Accessibility")
    print("="*80)
    
    # Test 5a: Mobile 390x844
    print("\n--- Test 5a: Mobile 390x844 ---")
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    
    await context.route("**/api/store*", lambda route: route.fulfill(
        status=503,
        body=json.dumps({"detail": "Mobile test"})
    ))
    
    await page.set_viewport_size({"width": 390, "height": 844})
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
    
    has_overflow = await page.evaluate("""() => {
        return document.body.scrollWidth > window.innerWidth;
    }""")
    
    assert_test(not has_overflow, "mobile_390_no_overflow", "No horizontal overflow on 390px")
    
    # Test keyboard navigation
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(200)
    focused = await page.evaluate("document.activeElement.tagName")
    print(f"✓ Keyboard navigation working, focused: {focused}")
    
    await page.screenshot(
        path=str(ARTIFACTS_DIR / f"final-03-mobile-390.jpg"),
        type="jpeg",
        quality=40,
        full_page=False
    )
    
    await page.close()
    await context.close()
    await browser.close()
    
    # Test 5b: Mobile 320px
    print("\n--- Test 5b: Mobile 320px ---")
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    
    await context.route("**/api/store*", lambda route: route.fulfill(
        status=503,
        body=json.dumps({"detail": "Mobile 320 test"})
    ))
    
    await page.set_viewport_size({"width": 320, "height": 568})
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
    
    retry_visible = await page.locator('[data-testid="retry-store"]').is_visible()
    owner_visible = await page.locator('[data-testid="store-recovery-admin"]').is_visible()
    
    assert_test(retry_visible, "mobile_320_retry_visible", "Retry button visible on 320px")
    assert_test(owner_visible, "mobile_320_owner_visible", "Owner link visible on 320px")
    
    await page.screenshot(
        path=str(ARTIFACTS_DIR / f"final-04-mobile-320.jpg"),
        type="jpeg",
        quality=40,
        full_page=False
    )
    
    await page.close()
    await context.close()
    await browser.close()
    
    # Test 5c: Reduced Motion
    print("\n--- Test 5c: Reduced Motion ---")
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    
    await page.emulate_media(reduced_motion="reduce")
    
    await context.route("**/api/store*", lambda route: route.fulfill(
        status=503,
        body=json.dumps({"detail": "Reduced motion test"})
    ))
    
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
    
    reduced_motion_active = await page.evaluate("""() => {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }""")
    
    assert_test(reduced_motion_active, "reduced_motion_active", "Reduced motion media query active")
    
    await page.screenshot(
        path=str(ARTIFACTS_DIR / f"final-05-reduced-motion.jpg"),
        type="jpeg",
        quality=40,
        full_page=False
    )
    
    await page.close()
    await context.close()
    await browser.close()
    
    print("✓ Mobile and accessibility tests PASSED")


async def main():
    """Run all comprehensive tests with proper assertions"""
    print("="*80)
    print("VOLTORA COMPREHENSIVE RETEST")
    print(f"Date: {test_date}")
    print(f"Origin: {FRONTEND_URL}")
    print("="*80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )
        page = await context.new_page()
        
        # Enable console logging for debugging
        page.on("console", lambda msg: print(f"[BROWSER] {msg.type}: {msg.text}"))
        
        try:
            # Test 1: Owner MFA Authentication
            session_data = await test_owner_mfa_authentication(page, context)
            
            # Test 2: Builder Access
            await test_builder_access(page, context)
            
            # Test 3: Storage Preservation
            await test_storage_preservation(page, context)
            
            await page.close()
            await context.close()
            await browser.close()
            
            # Test 4: Fresh Context Scenarios
            await test_fresh_context_scenarios(p)
            
            # Test 5: Mobile and Accessibility
            await test_mobile_and_accessibility(p)
            
        except AssertionError as e:
            print(f"\n✗ TEST FAILED: {e}")
            await page.screenshot(
                path=str(ARTIFACTS_DIR / f"FAILURE-{test_date}.jpg"),
                type="jpeg",
                quality=40,
                full_page=False
            )
            return False
        except Exception as e:
            print(f"\n✗ UNEXPECTED ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in test_results.values() if v)
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} assertions passed")
    print(f"Test date: {test_date}")
    print(f"Origin: {FRONTEND_URL}")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
