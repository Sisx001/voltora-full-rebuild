# CRITICAL DEFECT: Origin Mismatch Between Frontend and Backend

**Date**: 2026-10-08  
**Test**: test_voltora_recovery_focused.py  
**Status**: BLOCKING ALL OWNER/ADMIN TESTING

## Root Cause

Frontend and backend have mismatched origins:

- **Frontend** (`/app/frontend/.env`):  
  ```
  REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com
  ```

- **Backend** (`/app/backend/.env`):  
  ```
  APP_ORIGIN=https://a0f4fede-a6c1-4f9b-b1b6-5f4ad8e288c3.preview.emergentagent.com
  ```

## Evidence

Backend logs show origin rejection:
```
2026-10-08 08:00:18,481 WARNING security origin_rejected supplied='https://platform-complete-1.preview.emergentagent.com' expected='https://a0f4fede-a6c1-4f9b-b1b6-5f4ad8e288c3.preview.emergentagent.com'
```

Browser test shows 403 Forbidden on login:
```
[BROWSER] error: Failed to load resource: the server responded with a status of 403 ()
```

## Impact

- **BLOCKS**: All owner authentication
- **BLOCKS**: All MFA verification
- **BLOCKS**: All builder access
- **BLOCKS**: All admin functionality testing

## Historical Context

According to test_result.md line 205, this was supposedly fixed by creating `/app/backend/.env.local` with `ADDITIONAL_TRUSTED_ORIGINS`. However, this file does NOT exist:

```bash
$ ls -la /app/backend/.env*
-rw------- 1 root root 434 Oct  8 07:23 /app/backend/.env
-rw-r--r-- 1 root root 403 Oct  8 07:23 /app/backend/.env.example
```

The fix was either:
1. Never properly applied
2. Lost during a restart/rebuild
3. Removed by accident

## Required Fix

Main agent must either:

1. **Option A**: Create `/app/backend/.env.local` with:
   ```
   ADDITIONAL_TRUSTED_ORIGINS=https://platform-complete-1.preview.emergentagent.com
   ```
   Then restart backend: `sudo supervisorctl restart backend`

2. **Option B**: Update `/app/backend/.env` to match frontend:
   ```
   APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com
   ```
   Then restart backend: `sudo supervisorctl restart backend`

## Testing Cannot Proceed

Per review_request instructions:
- "Never modify app/env/Git changes by agent"
- "If real UI defect report exact selector+state, stop and return main for repair"

Testing agent CANNOT fix this. Main agent must resolve origin mismatch before any browser tests can proceed.
