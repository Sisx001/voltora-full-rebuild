"""
VOLTORA Recovery UI and Browser Integration Tests - COMPATIBILITY WRAPPER

This file is deprecated. Use test_voltora_recovery_comprehensive.py for all new tests.
This wrapper exists only for backward compatibility.
"""

import sys
import subprocess
from pathlib import Path

# Redirect to canonical comprehensive test
CANONICAL_TEST = Path("/app/tests/test_voltora_recovery_comprehensive.py")

def main():
    """Run canonical comprehensive test"""
    print("=" * 80)
    print("DEPRECATED: test_voltora_recovery_ui.py")
    print("Redirecting to canonical test: test_voltora_recovery_comprehensive.py")
    print("=" * 80)
    
    if not CANONICAL_TEST.exists():
        print(f"ERROR: Canonical test not found: {CANONICAL_TEST}")
        return False
    
    result = subprocess.run(
        [sys.executable, str(CANONICAL_TEST)],
        cwd="/app/tests"
    )
    
    return result.returncode == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

# ============================================================================
# ARCHIVED CODE BELOW - DO NOT USE
# ============================================================================

"""
import asyncio
import json
import pyotp
from playwright.async_api import async_playwright, Page, BrowserContext
from pathlib import Path

# DEPRECATED: Hardcoded URL - use frontend/.env instead
# Test configuration
FRONTEND_URL = "https://platform-complete-1.preview.emergentagent.com"
ARTIFACTS_DIR = Path("/app/artifacts")

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

print(f"Loaded credentials: {credentials.get('email', 'NOT FOUND')}")


async def seed_realistic_storage(page: Page):
    """Seed realistic cart and builder draft in localStorage"""
    await page.evaluate("""() => {
        // Realistic cart data
        const cart = [
            {
                product_id: "prod_001",
                variant_id: "var_001",
                quantity: 2,
                expected_price: 4500,
                name: "Premium Cotton T-Shirt",
                slug: "premium-cotton-tshirt",
                image: "https://example.com/tshirt.jpg",
                options: {size: "M", color: "Navy"}
            },
            {
                product_id: "prod_002",
                variant_id: "var_002",
                quantity: 1,
                expected_price: 8900,
                name: "Leather Messenger Bag",
                slug: "leather-messenger-bag",
                image: "https://example.com/bag.jpg",
                options: {color: "Brown"}
            }
        ];
        
        // Realistic builder draft (will be set after login)
        const builderDraft = {
            version: 1,
            bundle: {
                theme: {id: "forest", name: "Forest"},
                site: {
                    header: {layout: "centered", logo_text: "VOLTORA"},
                    footer: {style: "minimal"}
                },
                pages: {
                    home: {slug: "home", sections: []}
                }
            }
        };
        
        try {
            localStorage.setItem('voltora-cart', JSON.stringify(cart));
            localStorage.setItem('voltora-wishlist', JSON.stringify(["prod_003", "prod_004"]));
            localStorage.setItem('voltora-compare', JSON.stringify(["prod_005"]));
            localStorage.setItem('voltora-language', 'en');
            localStorage.setItem('voltora-currency', 'BDT');
            localStorage.setItem('voltora-mode', 'light');
            console.log('✓ Seeded realistic storage data');
        } catch (e) {
            console.error('Failed to seed storage:', e);
        }
    }""")


async def get_storage_snapshot(page: Page) -> dict:
    """Get byte-for-byte snapshot of localStorage"""
    return await page.evaluate("""() => {
        const snapshot = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            snapshot[key] = localStorage.getItem(key);
        }
        return snapshot;
    }""")


async def verify_storage_unchanged(page: Page, before: dict, context: str):
    """Verify localStorage is byte-for-byte unchanged"""
    after = await get_storage_snapshot(page)
    
    # Compare keys
    before_keys = set(before.keys())
    after_keys = set(after.keys())
    
    if before_keys != after_keys:
        print(f"✗ {context}: Storage keys changed!")
        print(f"  Added: {after_keys - before_keys}")
        print(f"  Removed: {before_keys - after_keys}")
        return False
    
    # Compare values byte-for-byte
    for key in before_keys:
        if before[key] != after[key]:
            print(f"✗ {context}: Storage value changed for key '{key}'")
            print(f"  Before: {before[key][:100]}...")
            print(f"  After: {after[key][:100]}...")
            return False
    
    print(f"✓ {context}: Storage unchanged (byte-for-byte)")
    return True


async def test_normal_storefront_load(page: Page):
    """Test 1: Inspect live storefront normal load and no undefined/api requests"""
    print("\n=== Test 1: Normal Storefront Load ===")
    
    # Monitor console for errors
    console_messages = []
    def handle_console(msg):
        console_messages.append(f"{msg.type}: {msg.text}")
    page.on("console", handle_console)
    
    # Monitor network for failed requests
    failed_requests = []
    def handle_failed(req):
        failed_requests.append(f"{req.method} {req.url} - {req.failure}")
    page.on("requestfailed", handle_failed)
    
    # Monitor API requests
    api_requests = []
    def handle_request(req):
        if '/api/' in req.url:
            api_requests.append(req.url)
    page.on("request", handle_request)
    
    try:
        # Navigate to storefront
        response = await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
        print(f"✓ Page loaded with status: {response.status}")
        
        # Wait for store to load
        await page.wait_for_selector('[data-testid="boot-splash"], .store-header', timeout=15000)
        print("✓ Store UI rendered")
        
        # Check for undefined errors in console
        undefined_errors = [msg for msg in console_messages if 'undefined' in msg.lower() or 'is not defined' in msg.lower()]
        if undefined_errors:
            print(f"✗ Found undefined errors in console:")
            for err in undefined_errors[:5]:
                print(f"  {err}")
        else:
            print("✓ No undefined errors in console")
        
        # Check for failed API requests (excluding overlay endpoints)
        real_failed = [req for req in failed_requests if '__emergent_overlay__' not in req]
        if real_failed:
            print(f"✗ Found failed requests:")
            for req in real_failed[:5]:
                print(f"  {req}")
        else:
            print("✓ No failed requests")
        
        # Verify API requests are valid
        print(f"✓ API requests made: {len(api_requests)}")
        for url in api_requests[:10]:
            print(f"  {url}")
        
        return len(undefined_errors) == 0 and len(real_failed) == 0
        
    except Exception as e:
        print(f"✗ Normal load test failed: {e}")
        return False


async def test_recovery_503_injection(page: Page, context: BrowserContext):
    """Test 2: Intercept /api/store returning 503 and verify StoreRecovery appears"""
    print("\n=== Test 2: Recovery 503 Injection ===")
    
    try:
        # Seed storage before failure
        await seed_realistic_storage(page)
        storage_before = await get_storage_snapshot(page)
        
        # Intercept /api/store to return 503
        await context.route("**/api/store*", lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({
                "detail": "Service temporarily unavailable",
                "correlation_id": "test-correlation-503-abc123"
            })
        ))
        
        # Navigate to trigger store load
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        
        # Wait for StoreRecovery to appear
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
        print("✓ StoreRecovery component rendered")
        
        # Verify error reference is displayed
        reference = await page.locator('[data-testid="recovery-reference"]').text_content()
        print(f"✓ Error reference displayed: {reference}")
        
        if "test-correlation-503-abc123" not in reference:
            print(f"✗ Expected correlation ID not found in reference")
            return False
        
        # Verify accessible elements
        heading = await page.locator('h1').first.text_content()
        print(f"✓ Heading: {heading}")
        
        if "A small pause" not in heading or "Not a lost bag" not in heading:
            print(f"✗ Expected heading text not found")
            return False
        
        # Verify retry button exists and is accessible
        retry_button = page.locator('[data-testid="retry-store"]')
        await retry_button.wait_for(state="visible")
        is_disabled = await retry_button.is_disabled()
        print(f"✓ Retry button visible, disabled: {is_disabled}")
        
        # Verify owner link exists
        owner_link = page.locator('[data-testid="store-recovery-admin"]')
        await owner_link.wait_for(state="visible")
        print("✓ Owner workspace link visible")
        
        # Verify details section
        details = page.locator('.recovery-details')
        await details.wait_for(state="visible")
        print("✓ Connection details section visible")
        
        # Verify copy button
        copy_button = page.locator('[data-testid="copy-recovery-reference"]')
        await copy_button.wait_for(state="visible")
        print("✓ Copy reference button visible")
        
        # Verify storage unchanged after failure
        await verify_storage_unchanged(page, storage_before, "After 503 failure")
        
        # Test retry button (should remain disabled while offline or make single request)
        await retry_button.click(force=True)
        await page.wait_for_timeout(500)
        
        # Verify button shows loading state
        button_text = await retry_button.text_content()
        print(f"✓ Button text after click: {button_text}")
        
        # Verify storage still unchanged after retry
        await verify_storage_unchanged(page, storage_before, "After retry click")
        
        # Take screenshot
        await page.set_viewport_size({"width": 1920, "height": 800})
        await page.screenshot(path=str(ARTIFACTS_DIR / "recovery-503-desktop.png"), type="jpeg", quality=40, full_page=False)
        print(f"✓ Screenshot saved: recovery-503-desktop.png")
        
        return True
        
    except Exception as e:
        print(f"✗ Recovery 503 test failed: {e}")
        await page.screenshot(path=str(ARTIFACTS_DIR / "recovery-503-error.png"), type="jpeg", quality=40, full_page=False)
        return False


async def test_malformed_responses(page: Page, context: BrowserContext):
    """Test 3: Aborted connection, malformed JSON/HTML, delayed request, offline/online"""
    print("\n=== Test 3: Malformed Responses ===")
    
    test_results = []
    
    # Test 3a: Malformed JSON response
    print("\n--- Test 3a: Malformed JSON ---")
    try:
        await seed_realistic_storage(page)
        storage_before = await get_storage_snapshot(page)
        
        await context.route("**/api/store*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body="{ invalid json"
        ))
        
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
        print("✓ Recovery shown for malformed JSON")
        
        # Verify it's marked as invalid-response
        details_text = await page.locator('.recovery-diagnostics').text_content()
        if "invalid" in details_text.lower():
            print("✓ Error kind indicates invalid response")
        
        await verify_storage_unchanged(page, storage_before, "After malformed JSON")
        test_results.append(True)
        
    except Exception as e:
        print(f"✗ Malformed JSON test failed: {e}")
        test_results.append(False)
    
    # Test 3b: HTML response instead of JSON
    print("\n--- Test 3b: HTML Response ---")
    try:
        await context.unroute("**/api/store*")
        await seed_realistic_storage(page)
        storage_before = await get_storage_snapshot(page)
        
        await context.route("**/api/store*", lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="<html><body>Error page</body></html>"
        ))
        
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
        print("✓ Recovery shown for HTML response")
        
        await verify_storage_unchanged(page, storage_before, "After HTML response")
        test_results.append(True)
        
    except Exception as e:
        print(f"✗ HTML response test failed: {e}")
        test_results.append(False)
    
    # Test 3c: Timeout (delayed beyond 12s)
    print("\n--- Test 3c: Timeout ---")
    try:
        await context.unroute("**/api/store*")
        await seed_realistic_storage(page)
        storage_before = await get_storage_snapshot(page)
        
        async def delay_route(route):
            await asyncio.sleep(13)  # Exceed 12s timeout
            await route.fulfill(status=200, body=json.dumps({"test": "data"}))
        
        await context.route("**/api/store*", delay_route)
        
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=20000)
        print("✓ Recovery shown for timeout")
        
        details_text = await page.locator('.recovery-diagnostics').text_content()
        if "timeout" in details_text.lower():
            print("✓ Error kind indicates timeout")
        
        await verify_storage_unchanged(page, storage_before, "After timeout")
        test_results.append(True)
        
    except Exception as e:
        print(f"✗ Timeout test failed: {e}")
        test_results.append(False)
    
    # Test 3d: Offline then online
    print("\n--- Test 3d: Offline/Online ---")
    try:
        await context.unroute("**/api/store*")
        await seed_realistic_storage(page)
        storage_before = await get_storage_snapshot(page)
        
        # Simulate offline
        await context.set_offline(True)
        
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
        print("✓ Recovery shown when offline")
        
        # Verify retry button is disabled when offline
        retry_button = page.locator('[data-testid="retry-store"]')
        is_disabled = await retry_button.is_disabled()
        if is_disabled:
            print("✓ Retry button disabled when offline")
        else:
            print("✗ Retry button should be disabled when offline")
        
        # Go back online
        await context.set_offline(False)
        await page.wait_for_timeout(1000)
        
        # Verify retry button becomes enabled
        is_disabled = await retry_button.is_disabled()
        if not is_disabled:
            print("✓ Retry button enabled when online")
        else:
            print("✗ Retry button should be enabled when online")
        
        await verify_storage_unchanged(page, storage_before, "After offline/online")
        test_results.append(True)
        
    except Exception as e:
        print(f"✗ Offline/online test failed: {e}")
        test_results.append(False)
    
    return all(test_results)


async def test_malformed_cart_preservation(page: Page):
    """Test 3e: Malformed cart JSON preserved (not erased)"""
    print("\n=== Test 3e: Malformed Cart Preservation ===")
    
    try:
        # Set malformed cart data
        await page.evaluate("""() => {
            localStorage.setItem('voltora-cart', '{ malformed json');
            localStorage.setItem('voltora-wishlist', 'not an array');
        }""")
        
        storage_before = await get_storage_snapshot(page)
        
        # Navigate to site
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        
        # Verify malformed data is preserved
        await verify_storage_unchanged(page, storage_before, "Malformed cart preservation")
        
        print("✓ Malformed cart data preserved (not erased)")
        return True
        
    except Exception as e:
        print(f"✗ Malformed cart preservation test failed: {e}")
        return False


async def test_denied_localstorage(page: Page, context: BrowserContext):
    """Test 3f: Denied localStorage should still render recovery, not crash"""
    print("\n=== Test 3f: Denied localStorage ===")
    
    try:
        # Inject script to throw SecurityError on localStorage access
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
        
        # Intercept store to force recovery
        await context.route("**/api/store*", lambda route: route.fulfill(
            status=503,
            body=json.dumps({"detail": "Service unavailable", "correlation_id": "test-storage-denied"})
        ))
        
        # Navigate
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        
        # Verify recovery renders without crash
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
        print("✓ Recovery rendered despite localStorage denial")
        
        # Verify owner link is still accessible
        owner_link = page.locator('[data-testid="store-recovery-admin"]')
        await owner_link.wait_for(state="visible")
        print("✓ Owner link accessible despite localStorage denial")
        
        return True
        
    except Exception as e:
        print(f"✗ Denied localStorage test failed: {e}")
        return False


async def test_owner_login_and_builder(page: Page, context: BrowserContext):
    """Test 4: Owner login with MFA and builder access while /store fails"""
    print("\n=== Test 4: Owner Login and Builder Access ===")
    
    try:
        # Keep /store failing
        await context.route("**/api/store*", lambda route: route.fulfill(
            status=503,
            body=json.dumps({"detail": "Store unavailable", "correlation_id": "test-owner-access"})
        ))
        
        # Navigate to recovery
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
        print("✓ Recovery page loaded")
        
        # Click owner workspace link
        owner_link = page.locator('[data-testid="store-recovery-admin"]')
        await owner_link.click()
        
        # Wait for owner entry page
        await page.wait_for_url("**/admin**", timeout=10000)
        print(f"✓ Navigated to owner workspace: {page.url}")
        
        # Wait for login form
        await page.wait_for_selector('input[type="email"], input[name="email"]', timeout=10000)
        print("✓ Owner login form loaded")
        
        # Fill in credentials
        email_input = page.locator('input[type="email"], input[name="email"]').first
        await email_input.fill(credentials['email'])
        print(f"✓ Filled email: {credentials['email']}")
        
        password_input = page.locator('input[type="password"], input[name="password"]').first
        await password_input.fill(credentials['password'])
        print("✓ Filled password")
        
        # Submit login
        submit_button = page.locator('button[type="submit"]').first
        await submit_button.click()
        print("✓ Submitted login")
        
        # Wait for MFA prompt
        await page.wait_for_selector('input[type="text"][maxlength="6"], input[name="code"], .otp-input', timeout=10000)
        print("✓ MFA prompt appeared")
        
        # Generate TOTP code
        totp = pyotp.TOTP(credentials['totp_secret'])
        code = totp.now()
        print(f"✓ Generated TOTP code: {code}")
        
        # Fill MFA code
        mfa_input = page.locator('input[type="text"][maxlength="6"], input[name="code"], .otp-input').first
        await mfa_input.fill(code)
        print("✓ Filled MFA code")
        
        # Submit MFA
        mfa_submit = page.locator('button[type="submit"]').first
        await mfa_submit.click()
        print("✓ Submitted MFA")
        
        # Wait for workspace to load
        await page.wait_for_timeout(3000)
        
        # Check if we're in the admin workspace
        current_url = page.url
        if '/admin' in current_url:
            print(f"✓ Successfully logged into workspace: {current_url}")
        else:
            print(f"✗ Not in admin workspace: {current_url}")
            return False
        
        # Take screenshot of authenticated workspace
        await page.screenshot(path=str(ARTIFACTS_DIR / "owner-workspace-authenticated.png"), type="jpeg", quality=40, full_page=False)
        print("✓ Screenshot saved: owner-workspace-authenticated.png")
        
        # Navigate to website builder
        await page.goto(f"{FRONTEND_URL}/admin/website", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        print("✓ Navigated to website builder")
        
        # Verify builder loads independently (check for /api/admin/builder request)
        builder_loaded = False
        try:
            # Wait for builder interface elements
            await page.wait_for_selector('[data-testid="builder-canvas"], iframe[name="voltora-preview"]', timeout=10000)
            print("✓ Website builder interface loaded")
            builder_loaded = True
        except:
            print("✗ Website builder interface not found")
        
        # Take screenshot of builder
        await page.screenshot(path=str(ARTIFACTS_DIR / "website-builder-loaded.png"), type="jpeg", quality=40, full_page=False)
        print("✓ Screenshot saved: website-builder-loaded.png")
        
        return builder_loaded
        
    except Exception as e:
        print(f"✗ Owner login and builder test failed: {e}")
        await page.screenshot(path=str(ARTIFACTS_DIR / "owner-login-error.png"), type="jpeg", quality=40, full_page=False)
        return False


async def test_builder_preview_modes(page: Page, context: BrowserContext):
    """Test 5: Remove /store failure and test Login/Footer previews + device switching"""
    print("\n=== Test 5: Builder Preview Modes ===")
    
    try:
        # Remove /store failure
        await context.unroute("**/api/store*")
        
        # Ensure we're on builder page (should already be logged in from previous test)
        if '/admin/website' not in page.url:
            await page.goto(f"{FRONTEND_URL}/admin/website", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
        
        print("✓ On website builder page")
        
        # Look for device switcher buttons
        desktop_button = page.locator('button:has-text("Desktop"), [data-testid="device-desktop"]').first
        tablet_button = page.locator('button:has-text("Tablet"), [data-testid="device-tablet"]').first
        mobile_button = page.locator('button:has-text("Mobile"), [data-testid="device-mobile"]').first
        
        # Test desktop view
        if await desktop_button.count() > 0:
            await desktop_button.click()
            await page.wait_for_timeout(1000)
            print("✓ Switched to desktop view")
            await page.screenshot(path=str(ARTIFACTS_DIR / "builder-preview-desktop.png"), type="jpeg", quality=40, full_page=False)
        
        # Test tablet view
        if await tablet_button.count() > 0:
            await tablet_button.click()
            await page.wait_for_timeout(1000)
            print("✓ Switched to tablet view")
            await page.screenshot(path=str(ARTIFACTS_DIR / "builder-preview-tablet.png"), type="jpeg", quality=40, full_page=False)
        
        # Test mobile view
        if await mobile_button.count() > 0:
            await mobile_button.click()
            await page.wait_for_timeout(1000)
            print("✓ Switched to mobile view")
            await page.screenshot(path=str(ARTIFACTS_DIR / "builder-preview-mobile.png"), type="jpeg", quality=40, full_page=False)
        
        # Look for section selectors (Login, Footer, etc.)
        login_selector = page.locator('button:has-text("Login"), [data-testid="select-login"]').first
        footer_selector = page.locator('button:has-text("Footer"), [data-testid="select-footer"]').first
        
        # Test Login preview
        if await login_selector.count() > 0:
            await login_selector.click()
            await page.wait_for_timeout(1000)
            print("✓ Selected Login section")
        
        # Test Footer preview
        if await footer_selector.count() > 0:
            await footer_selector.click()
            await page.wait_for_timeout(1000)
            print("✓ Selected Footer section")
        
        print("✓ Builder preview modes tested")
        return True
        
    except Exception as e:
        print(f"✗ Builder preview modes test failed: {e}")
        return False


async def test_mobile_responsive(page: Page, context: BrowserContext):
    """Test 6: Mobile 390x844 and 320px - no overflow/overlap, keyboard focus"""
    print("\n=== Test 6: Mobile Responsive ===")
    
    try:
        # Remove any routes
        await context.unroute("**/api/store*")
        
        # Inject 503 for recovery testing
        await context.route("**/api/store*", lambda route: route.fulfill(
            status=503,
            body=json.dumps({"detail": "Service unavailable", "correlation_id": "test-mobile-recovery"})
        ))
        
        # Test 390x844 (iPhone 12 Pro)
        print("\n--- Test 6a: 390x844 Mobile ---")
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
        
        # Check for overflow
        has_overflow = await page.evaluate("""() => {
            const body = document.body;
            return body.scrollWidth > window.innerWidth;
        }""")
        
        if has_overflow:
            print("✗ Horizontal overflow detected on 390px")
        else:
            print("✓ No horizontal overflow on 390px")
        
        # Test keyboard focus
        await page.keyboard.press("Tab")
        focused_element = await page.evaluate("document.activeElement.tagName")
        print(f"✓ First tab focus: {focused_element}")
        
        # Verify heading has focus
        heading = page.locator('h1').first
        heading_focused = await heading.evaluate("el => el === document.activeElement || el.contains(document.activeElement)")
        if heading_focused:
            print("✓ Heading receives initial focus")
        
        # Tab through interactive elements
        for i in range(5):
            await page.keyboard.press("Tab")
            await page.wait_for_timeout(100)
        
        # Verify retry button is reachable
        retry_button = page.locator('[data-testid="retry-store"]')
        retry_focused = await retry_button.evaluate("el => el === document.activeElement")
        print(f"✓ Retry button keyboard reachable: {retry_focused or 'via tab sequence'}")
        
        # Verify owner link is reachable
        await page.keyboard.press("Tab")
        owner_link = page.locator('[data-testid="store-recovery-admin"]')
        owner_focused = await owner_link.evaluate("el => el === document.activeElement")
        print(f"✓ Owner link keyboard reachable: {owner_focused or 'via tab sequence'}")
        
        # Take screenshot
        await page.screenshot(path=str(ARTIFACTS_DIR / "recovery-mobile-390.png"), type="jpeg", quality=40, full_page=False)
        print("✓ Screenshot saved: recovery-mobile-390.png")
        
        # Test 320px (smallest common mobile)
        print("\n--- Test 6b: 320px Mobile ---")
        await page.set_viewport_size({"width": 320, "height": 568})
        await page.wait_for_timeout(1000)
        
        # Check for overflow
        has_overflow = await page.evaluate("""() => {
            const body = document.body;
            return body.scrollWidth > window.innerWidth;
        }""")
        
        if has_overflow:
            print("⚠ Horizontal overflow detected on 320px (acceptable if minor)")
        else:
            print("✓ No horizontal overflow on 320px")
        
        # Verify critical elements are visible
        retry_visible = await retry_button.is_visible()
        owner_visible = await owner_link.is_visible()
        
        print(f"✓ Retry button visible on 320px: {retry_visible}")
        print(f"✓ Owner link visible on 320px: {owner_visible}")
        
        # Take screenshot
        await page.screenshot(path=str(ARTIFACTS_DIR / "recovery-mobile-320.png"), type="jpeg", quality=40, full_page=False)
        print("✓ Screenshot saved: recovery-mobile-320.png")
        
        return True
        
    except Exception as e:
        print(f"✗ Mobile responsive test failed: {e}")
        return False


async def test_reduced_motion(page: Page, context: BrowserContext):
    """Test 7: Reduced-motion emulation - animations/transitions disabled"""
    print("\n=== Test 7: Reduced Motion ===")
    
    try:
        # Emulate prefers-reduced-motion
        await page.emulate_media(media="screen", color_scheme="light", reduced_motion="reduce")
        
        # Inject 503 for recovery
        await context.route("**/api/store*", lambda route: route.fulfill(
            status=503,
            body=json.dumps({"detail": "Service unavailable", "correlation_id": "test-reduced-motion"})
        ))
        
        # Set desktop viewport
        await page.set_viewport_size({"width": 1920, "height": 800})
        
        # Navigate
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
        print("✓ Recovery loaded with reduced motion")
        
        # Check if animations are disabled via CSS
        animations_disabled = await page.evaluate("""() => {
            const style = getComputedStyle(document.documentElement);
            const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
            return mediaQuery.matches;
        }""")
        
        if animations_disabled:
            print("✓ Reduced motion media query active")
        else:
            print("⚠ Reduced motion media query not detected")
        
        # Verify no spinning animation on retry button
        retry_button = page.locator('[data-testid="retry-store"]')
        await retry_button.click(force=True)
        await page.wait_for_timeout(500)
        
        # Check if spinning class is present (it shouldn't animate with reduced motion)
        spinning_element = page.locator('.recovery-spinning')
        spinning_count = await spinning_element.count()
        print(f"✓ Spinning elements: {spinning_count} (animation should be disabled via CSS)")
        
        # Take screenshot
        await page.screenshot(path=str(ARTIFACTS_DIR / "recovery-reduced-motion.png"), type="jpeg", quality=40, full_page=False)
        print("✓ Screenshot saved: recovery-reduced-motion.png")
        
        return True
        
    except Exception as e:
        print(f"✗ Reduced motion test failed: {e}")
        return False


async def test_single_flight_retry(page: Page, context: BrowserContext):
    """Test 8: Verify repeated retry clicks are single-flight, button busy/disabled"""
    print("\n=== Test 8: Single-Flight Retry ===")
    
    try:
        # Inject slow 503 response
        async def slow_503(route):
            await asyncio.sleep(2)
            await route.fulfill(
                status=503,
                body=json.dumps({"detail": "Still unavailable", "correlation_id": "test-single-flight"})
            )
        
        await context.route("**/api/store*", slow_503)
        
        await page.set_viewport_size({"width": 1920, "height": 800})
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_selector('[data-testid="store-recovery"]', timeout=15000)
        
        retry_button = page.locator('[data-testid="retry-store"]')
        
        # Click retry multiple times rapidly
        print("✓ Clicking retry button 5 times rapidly...")
        for i in range(5):
            await retry_button.click(force=True)
            await page.wait_for_timeout(100)
        
        # Verify button is disabled/busy
        is_disabled = await retry_button.is_disabled()
        button_text = await retry_button.text_content()
        
        print(f"✓ Button disabled: {is_disabled}")
        print(f"✓ Button text: {button_text}")
        
        if "Reconnecting" in button_text or is_disabled:
            print("✓ Button shows busy state")
        else:
            print("⚠ Button may not show busy state clearly")
        
        # Wait for request to complete
        await page.wait_for_timeout(3000)
        
        # Verify no full reload occurred (check if recovery is still visible)
        recovery_still_visible = await page.locator('[data-testid="store-recovery"]').is_visible()
        if recovery_still_visible:
            print("✓ No full page reload occurred")
        else:
            print("✗ Page may have reloaded")
        
        return True
        
    except Exception as e:
        print(f"✗ Single-flight retry test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("=" * 80)
    print("VOLTORA Recovery UI and Browser Integration Tests")
    print("=" * 80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
            permissions=["clipboard-read", "clipboard-write"]
        )
        page = await context.new_page()
        
        # Enable console logging
        page.on("console", lambda msg: None)  # Suppress console spam in main output
        
        results = {}
        
        # Run tests
        results['normal_load'] = await test_normal_storefront_load(page)
        
        # Create new context for route interception tests
        await page.close()
        await context.close()
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
            permissions=["clipboard-read", "clipboard-write"]
        )
        page = await context.new_page()
        
        results['recovery_503'] = await test_recovery_503_injection(page, context)
        results['malformed_responses'] = await test_malformed_responses(page, context)
        results['malformed_cart'] = await test_malformed_cart_preservation(page)
        results['denied_storage'] = await test_denied_localstorage(page, context)
        results['owner_login'] = await test_owner_login_and_builder(page, context)
        results['builder_preview'] = await test_builder_preview_modes(page, context)
        results['mobile_responsive'] = await test_mobile_responsive(page, context)
        results['reduced_motion'] = await test_reduced_motion(page, context)
        results['single_flight'] = await test_single_flight_retry(page, context)
        
        await browser.close()
        
        # Print summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        for test_name, passed in results.items():
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"{status}: {test_name}")
        
        total = len(results)
        passed = sum(1 for v in results.values() if v)
        print(f"\nTotal: {passed}/{total} tests passed")
        
        return passed == total


if __name__ == "__main__":
    import sys
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
