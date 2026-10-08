# VOLTORA isolated development startup

## Baseline and boundaries

Audited checkout: `01921b03ca990bb08206d7ad61561d22e9f41407`. Public repository lookup reported the same main HEAD; no Git fetch/commit performed. Use Emergent GitHub controls to import newer source or save reviewable changes. Never reuse archive secrets. This milestone does not authorize deployment or real external transactions.

## Prerequisites and installation

- Python environment matching `backend/requirements.txt`, Node and Yarn matching `frontend/package.json` and `yarn.lock`, MongoDB, supervisor.
- `python -m pip install -r backend/requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/`
- `cd frontend && yarn install --frozen-lockfile`
- Do not downgrade pinned dependencies to make installation pass. Existing environment dependencies may already be installed.

## Fresh private setup

Run from `/app`: `python scripts/setup_development.py --mongo-url "$LOCAL_MONGO_URL" --origin "$PREVIEW_ORIGIN"`.
Supply the current isolated MongoDB URI and HTTPS preview origin. On Emergent, `--origin` can be omitted to use supervisor's platform `APP_URL`. The command generates a unique database name and fresh private secrets, writes mode-0600 ignored environment files, and refuses to overwrite existing `.env` or combine old `.env.local` files. It never reads archives, creates accounts, or enables external actions. For an existing valid installation keep its protected URLs and secrets unchanged.

The fresh database contains the existing seed's **synthetic design catalog**, not imported business records. It is a development-only namespace. Do not migrate or activate this seed for production. Other databases are not modified. A prefix is not proof of multitenant isolation.

### Required names (values are private)

Backend: `MONGO_URL`, `DB_NAME`, `REBUILD_COLLECTION_PREFIX`, `APP_ORIGIN`, `APP_SECRET`. First owner setup: `OWNER_SETUP_KEY`. Safety: `RUNTIME_MODE=sandbox`, `EXTERNAL_ACTIONS_ENABLED=false`. Optional: `ADDITIONAL_TRUSTED_ORIGINS`.
Frontend: `REACT_APP_BACKEND_URL`, optional `REACT_APP_ADMIN_PATH`.
Sanitized templates are `backend/.env.example` and `frontend/.env.example`.

Frontend API base is exclusively `REACT_APP_BACKEND_URL` + `/api`; missing/invalid configuration blocks requests instead of constructing `undefined/api` or guessing another origin. `APP_ORIGIN` must match the HTTPS browser origin. Browser frontend/backend use the same platform origin, with `/api` ingress to the backend. Existing supervisor ports remain frontend 3000 and backend 8001. Do not change .env URLs to localhost for browser testing.

Owner/session cookies are Secure, HttpOnly, SameSite=Lax. Use HTTPS for browser auth, preserve CSRF checks and exact CORS origins, and never disable MFA to make tests pass. For first setup, open the configured owner path, use the private setup key, then enroll MFA. No demo or owner password is supplied in source.

## Platform preview aliases and configuration drift

The platform can replace the browser-facing preview URL after bootstrap (UUID alias to a named alias). A backend API test without `Origin` does not exercise the browser allowlist. Run `python scripts/check_environment.py` before browser tests and after platform URL changes. It validates names-only settings and checks the frontend/API origin against the configured primary and supplemental origins; it never silently approves a new origin.

If the current platform-provided `REACT_APP_BACKEND_URL` is an approved alias of this same isolated app but differs from `APP_ORIGIN`, keep both protected values unchanged. Explicitly approve only that exact HTTPS origin with `ADDITIONAL_TRUSTED_ORIGINS` in a **new private mode-0600 `backend/.env.local`** when this file/key is absent. Review existing settings rather than overwriting them. Do not restore an archived supplemental file, use wildcards, reflect incoming Origin headers, or change cookie security. `python-dotenv` loads existing environment and `.env` first, then fills missing names from `.env.local` (it does not override existing values).

Restart the backend after the new supplemental setting. Test allowed preflight and password+MFA requests with a real Origin, and confirm an untrusted Origin still receives 403. Frontend browser and API should use the same configured platform alias for cookies. Distinct-site deployments require separate review; this check is not proof of cross-site cookie support.

## Start and verify

Run `python scripts/check_environment.py`. Use `sudo supervisorctl restart backend frontend`; do not start separate servers. `sudo supervisorctl status` alone is not readiness: check `/api/health` and `/api/store`, browser requests and backend logs. Startup validates required variables with names-only diagnostics before importing app modules. MongoDB selection/connect timeout is bounded. Configuration changes require service restart; ordinary source changes hot reload.

- Build: `cd frontend && yarn build`
- Types: `cd frontend && yarn tsc --noEmit`
- Focused backend tests: `cd backend && python -m pytest tests/test_runtime_config.py tests/test_security_fixtures.py tests/test_sslcommerz_verify.py`
- Critical backend workflow suite: `cd backend && python -m pytest tests/test_voltora_e2e.py` (isolated environment only; creates a fresh owner and writes private test credentials)
- Browser tests are delegated to the frontend testing agent; see `test_result.md` and the milestone evidence document.

Never interpret these local tests as provider sandbox verification. Payments, delivery, AI and production messaging remain disabled/unverified. Frontend injected failures and unit-test doubles are tests only, not operational fallbacks.

## Recovery and rollback boundaries

Recovery retries only a configuration GET. It must not clear local cart/draft keys, replace owner sessions, publish drafts or change service mode. Owner entry and builder routing bypass storefront config errors where their own APIs are available. A total database/API outage cannot promise working auth or builder access.

Before any production migration, implement and test versioned storage backup/restore and version-bound owner/MFA activation. Neither is verified by this milestone. Rolling back source changes or a presentation release must never restore over orders, payments or customers. Do not delete databases or .git/.emergent directories.
