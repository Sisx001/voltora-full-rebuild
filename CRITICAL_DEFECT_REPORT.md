# RESOLVED: Preview-Origin Mismatch (Historical Incident)

**Date**: 2026-10-08
**Severity at discovery**: Blocked owner browser authentication
**Current status**: RESOLVED and verified by Origin-aware backend tests plus real browser login/MFA/builder checks

Resolution: preserved both protected environment URLs and approved the exact current platform browser alias through fresh private `backend/.env.local` (`ADDITIONAL_TRUSTED_ORIGINS`). Added `scripts/check_environment.py`. No CORS reflection, cookie changes, MFA bypass or CSRF relaxation. See `docs/REBUILD_STATUS.md` for current evidence; the incident description below is historical.

## Issue Summary

Owner authentication is completely broken due to a configuration mismatch between frontend and backend origins. The backend rejects all POST requests from the frontend with HTTP 403 "Origin is not permitted".

## Root Cause

**Backend Configuration** (`/app/backend/.env`):
```
APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com
```

**Frontend Configuration** (`/app/frontend/.env`):
```
REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com
```

**The Problem**:
- Frontend makes API calls to `voltora-rebuild.preview.emergentagent.com`
- Browser sends `Origin: https://platform-complete-1.preview.emergentagent.com` header
- Backend only trusts `becdfce3-6d10-4070-be79-e95f62e6a958.preview.emergentagent.com`
- Backend middleware (`server.py` line ~40) rejects the request with 403

## Reproduction Steps

1. Navigate to `https://platform-complete-1.preview.emergentagent.com`
2. Trigger recovery (or go directly to `/admin`)
3. Click "Open owner workspace"
4. Fill in valid credentials:
   - Email: qa.owner.671e6551d3@example.com
   - Password: VoltoraQA!809f6e747b6e4e
5. Click "Open your workspace"
6. **RESULT**: HTTP 403 with "Origin is not permitted"

## Evidence

### Backend Logs
```
INFO: 10.11.1.73:51566 - "POST /api/auth/login HTTP/1.1" 403 Forbidden
```

### Backend Middleware Code (`server.py`)
```python
@app.middleware('http')
async def safeguards(request:Request,call_next):
    if request.method not in ['GET','HEAD','OPTIONS']:
        supplied=request.headers.get('origin')
        if supplied and supplied.rstrip('/') not in trusted_origins:
            logging.getLogger('security').warning('origin_rejected supplied=%r expected=%r',supplied,origin)
            return JSONResponse({'detail':'Origin is not permitted'},status_code=403)
```

### Browser Screenshot
See `/app/artifacts/06-owner-workspace.jpeg` - shows "Origin is not permitted" error on login form

## Impact

- **Owner authentication**: BLOCKED
- **MFA verification**: CANNOT TEST (blocked by login)
- **Builder access**: CANNOT TEST (requires authentication)
- **All admin functions**: BLOCKED

## Required Fix

The main agent must ensure APP_ORIGIN and REACT_APP_BACKEND_URL match. Options:

1. **Update backend** `/app/backend/.env`:
   ```
   APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com
   ```

2. **OR update frontend** `/app/frontend/.env`:
   ```
   REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com
   ```

3. **OR add to backend** `/app/backend/.env`:
   ```
   ADDITIONAL_TRUSTED_ORIGINS=https://platform-complete-1.preview.emergentagent.com
   ```

## Testing Notes

- This is NOT a test script issue
- This is NOT a CORS configuration issue
- This is a REAL application defect
- Previous testing agent's report was CORRECT about "Origin is not permitted"
- Cannot proceed with MFA/builder testing until this is fixed

## Next Steps

1. Main agent must fix the origin mismatch
2. Restart backend service: `sudo supervisorctl restart backend`
3. Re-run comprehensive tests
4. Verify owner authentication works
5. Continue with MFA and builder testing
