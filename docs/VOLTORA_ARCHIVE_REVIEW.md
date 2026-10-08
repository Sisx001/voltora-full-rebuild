# VOLTORA — uploaded project inspection

Date: 2026-10-08

## Scope and evidence boundary

This is an initial **static source inspection**, including a separate read-only security assessment, of the uploaded `project_complete.zip`. The archived application has not been started, connected to a database, or used to contact any provider. Existing production infrastructure has not been accessed. Historical test reports are supplied evidence, not tests performed in this environment.

No original source, credentials, business records, or active application files were replaced. The active `/app/backend` and `/app/frontend` remain the starter project. Uploaded material is isolated under `/app/legacy_audit/`, excluded from Git. The previously generated design proposal predates the upload; its temporary wordmark must NOT replace the now-located original logo.

## 1. Archive integrity and preservation

- All three uploaded files have identical SHA-256: `af72468c1695946dd84bda7735017767070bff07ed25a8e884e3f47034d384f8`.
- Each is approximately 153 MiB compressed, with 840 outer archive entries and approximately 158.13 MiB expanded contents.
- Outer entry paths were checked for absolute paths, parent traversal and symlinks before extraction. None were found. This is not a malware certification.
- Primary snapshot: `backend/`, `frontend/`, `docs/`, `test_reports/`.
- Historical source: `original/source/voltora-main/voltora-main/` and `rebuild/preserved/`.
- Nested archives: `original/voltora-main.zip` (73,392 entries; inventoried but not extracted) and `frontend/public/downloads/voltora-rebuild-source.zip` (238 entries; inventoried but not extracted).
- No MongoDB BSON dump or recognizable database-backup artifact was found in the outer or nested archive inventories. JSON files include application definitions and sample catalogs; these are not a verified production database backup.
- Original V-mark markup and CSS exist in the historical and current frontend. Current `frontend/public/assets/favicon.svg` also contains a V mark. Preserve the historical mark and compare rendering before redesign.

## 2. Infrastructure and integration inventory

| Area | Evidence in source | Verification status |
|---|---|---|
| Frontend | React 19, TypeScript 4.9.5, React Router, CRACO, Tailwind/Shadcn, Axios | Source/dependency declarations only; no build run here |
| Backend | FastAPI, Motor/PyMongo, Pydantic, HTTPX | 231 route decorator declarations across 33 modules; all active backend Python files parsed as AST without syntax errors |
| Database | MongoDB via environment configuration; namespace-prefixed collections and request ContextVar | No connection attempted; source does not establish live database contents |
| Hosting | Documentation describes Supervisor and `/api` ingress, with historical preview URLs | Actual production host/domain/runtime unverified; no infrastructure access supplied |
| Sessions | Argon2, hashed opaque sessions, HttpOnly cookies, CSRF, role lookup, TOTP modules | Present in code; full runtime/auth acceptance not performed |
| Payments | Stripe, PayPal, bKash, SSLCommerz; Nagad/Rocket/Upay represented through SSLCommerz; mock adapter | Adapter source exists. No sandbox or live transaction verified here |
| Couriers | Pathao, Steadfast, RedX; mock courier | Adapter source exists; no booking, tracking or webhook verified |
| Email/messaging | SMTP notification adapter, mock messaging; mailbox drafts/plans | Mailbox delivery explicitly unimplemented/blocked; inbound ingestion and IMAP absent from documented completed scope |
| AI | DeepSeek-focused gateway and assistant/tools modules | Not a verified provider-independent AI layer; no model/provider request made |
| OAuth | Google, Facebook, Apple modules | Source only; credentials, callbacks and provider acceptance unverified |
| CAPTCHA | reCAPTCHA, hCaptcha, Cloudflare Turnstile | Source only; not connection-tested |
| Infrastructure/notifications | Cloudflare and Telegram adapters | Source only; not connection-tested |
| Media | Pillow validation and WebP conversion; MongoDB `media_blobs` and attachment blobs | Not the requested versioned object-storage architecture |
| Scheduled work | `.emergent/crons.yml`: 15-minute publishing cadence; authenticated publishing handler | Archived schedule only; not enabled or triggered in this environment |
| Themes/catalogs | Theme definitions and 11 industry JSON packs | Seed/demo assets, not proof of distinct complete themes or business inventory |

`frontend/src/App.tsx` defines 12 storefront routes and 38 admin-route entries, plus the admin index, offer route and not-found route. Broad functionality includes catalog, inventory, orders, accounts, support, offers, affiliates, themes/pages, media, mailbox, providers, analytics, roles and settings. Presence of a route is not proof its entire flow works.

Principal data domains: users/sessions/roles; products/product_drafts/inventory/categories/brands/collections; orders/payment_transactions/shipments; documents/revisions/previews/themes; provider_configs/integrations; support conversations/messages/attachments; media/media_blobs; mailbox drafts/plans; AI tasks/usage/action requests; audit and analytics records. Shared infrastructure collections are also accessed outside the ordinary scoped proxy and require separate isolation tests.

## 3. Verified source issues and acceptance gaps

Paths below are relative to the extracted primary snapshot. Priorities are rebuild triage priorities, not a claim of an exploited production vulnerability.

### P0 — archived secrets must not be activated or redistributed

- Outer archive contains `backend/.env`, historical backend/frontend environment files, and the original nested archive also contains `.env` files.
- Sensitive identifiers include `APP_SECRET`, `OWNER_SETUP_KEY`, `WEBHOOK_CRON_SECRET`, and a historical LLM-key variable. Values were not printed in this report or loaded into the active application.
- Treat any real credentials distributed in these archives as exposed: rotate or revoke them with their providers before reuse. Do not infer that a breach has occurred.
- Preserve original artifacts privately for evidence; create sanitized rebuild/export artifacts without nested secret-bearing archives.

### P0 — current demo entry conflicts with the requested credentialed boundary

- `backend/core.py:16` defaults `RUNTIME_MODE` to `demo` if unset.
- `backend/isolation.py:47-69` permits anonymous creation of a synthetic owner workspace and an MFA-satisfied session.
- This is an isolated demo namespace, **not evidence that the real owner or business data are publicly reachable**. It nevertheless violates the requested dedicated credentialed demo account and prohibition on privileged demo operations.
- Replace public owner creation with credentialed, restricted demo access. Require explicit environment mode and an independent external-action kill switch. Simply changing mode to production is not an adequate repair and could enable outbound paths.
- Add namespace quotas and retention/cleanup after scheduling requirements are reviewed.

### P1 — payment verification does not bind SSLCommerz success to the expected transaction

- `backend/providers/payments/sslcommerz.py:79-92` returns `paid` for `VALID`/`VALIDATED` without comparing the validation payload to the expected transaction, amount and currency.
- Potential exploitation requires the provider to be configured and reachable; no live exploit or payment was attempted.
- Before enabling the provider, require exact transaction identity, currency and expected-amount matching using the provider contract, deduplicate events, and reconcile payment state server-side. Test mismatched IDs/amounts/currencies and reused validation references.

### P1 — Login/Footer acceptance flow is not implemented as requested

- `frontend/src/pages/admin/WebsiteBuilder.tsx:9-14` lists Login & signup and Footer settings, but all SitePanel previews use `src="/"` at line 56.
- Selecting Login therefore targets the homepage URL rather than a dedicated customer authentication preview state. This is a verified route-selection defect; exact visual behavior still requires a browser run.
- Footer is stored as part of shared site configuration, not as a fabricated page, which is worth preserving. However, selection does not scroll/highlight its rendered region or present affected-page review.
- `SitePanel` uses explicit manual save; no autosave or unsaved-navigation guard is present in that component. Switching tabs remounts it. Local unsaved changes can therefore be lost.
- The label at line 40 equates clean local state with “Draft in sync with live,” even after saving an unpublished draft. Replace this with separate local-save, draft and live-release states.
- Save/publish/history and undo/redo implementation can inform the rebuild, but cannot be treated as completion of the acceptance flow.

### P1 — store startup failure blocks the owner workspace too

- `frontend/src/lib/store.tsx:15` collapses every `/store` failure to one boolean error.
- `frontend/src/App.tsx:89-105` checks that global error before rendering either storefront or admin routes.
- This confirms shared failure coupling and poor error visibility. It does **not** establish why a particular historical “couldn’t reach the store” incident occurred.
- Reproduce failures in an isolated runtime; collect request status, correlation ID and sanitized backend/database evidence. Keep admin recovery/login independent of storefront configuration success.

### P1 — publication is per-document, not an atomic immutable site-release switch

- `backend/cms.py:67-76` updates a document's published copy using version comparison, then inserts a revision and audit entry separately.
- Optimistic conflict detection exists, but a failure between operations can leave live content updated without corresponding history. Multiple documents do not switch together as one release.
- Build validated immutable site releases and switch a single active-release pointer atomically. Restoration must affect presentation/configuration only, never completed business transactions.

### P1 — legacy AI streaming client is used after closure

- `backend/ai.py:56-60` exits `async with httpx.AsyncClient(...)` before calling `client.stream(...)`.
- The source has an invalid client-lifetime pattern that should fail if this path is invoked. It has not been exercised here and is not a verified root cause of storefront failure.
- Repair and test with an isolated adapter before enabling external AI. Also review the configurable base URL and credential-forwarding policy before accepting arbitrary provider hosts.

### P1/P2 — isolation and architecture gaps

- Preview client state avoids the live cart and skips loading a logged-in customer, and server middleware rejects recognized preview mutations. These are useful existing controls.
- Previews are nevertheless same-origin. `LivePageFrame.tsx:8` combines `allow-scripts` and `allow-same-origin`; `WebsiteBuilder.tsx:56` has no iframe sandbox attribute. Neither is a secure boundary for untrusted executable custom code. Keep custom scripts disabled pending separate-origin sandbox design.
- Object storage with media versioning/backup artifacts is not implemented: `backend/media.py` stores image binaries in MongoDB and explicitly rejects unconfigured external attachment storage.
- Backup and restoration in `docs/OPERATIONS.md` are instructions, explicitly not a successful restore drill.
- Multi-provider AI, complete email delivery, payment/courier sandbox verification, recovery delivery, resilient multi-document commerce writes and comprehensive accessibility/performance testing remain unfinished according to supplied documentation and inspected source.
- Additional static security hardening: require production Secure cookies independently of an accidentally non-HTTPS origin; bind OAuth state to the selected provider; check Facebook OAuth HTTP-client lifetime. These need focused implementation and tests.

## 4. What has and has not been verified here

**Performed:** download/hash comparison; safe outer extraction; inventory of nested archives without executing/extracting them; source/route/dependency/provider/asset inspection; Python AST parsing; source-level security assessment; comparison against the required acceptance flow.

**Not performed:** application import/startup, dependency installation/build, browser reproduction, database connection or migration, security exploit testing, external provider requests, payment processing, backup/restore, production infrastructure audit, accessibility/load testing, or re-execution of any supplied historical test.

The independent static assessment found the demo-default and SSLCommerz issues described above. Its scope does not justify a production safety certification or a claim that there are no other vulnerabilities.

## 5. Ordered next work

1. Retain the archive and original logo; prepare a sanitized working copy. Do not copy uploaded `.env` values, nested archives, public source downloads or caches into the active app.
2. Establish isolated runtime configuration using provisioned database/URL settings and fresh private secrets, with real payments and all outbound production actions disabled independently of auth mode.
3. Replace public demo-owner entry; verify credentialed owner access, expiry, MFA boundaries and direct protected URLs.
4. Reproduce store-startup failures with request IDs and isolated admin recovery; do not mask failures with fake success/fallback content.
5. Implement Login customer-state preview → draft save → shared Footer impact review → responsive preview → explicit release publication, preserving admin session and live cart state.
6. Add immutable site releases, concurrency tests and presentation-only rollback; test old-live-before-publish behavior.
7. Obtain a separately supplied authorized business-data backup or approved read-only infrastructure inventory. Restore it into isolated staging and measure recovery before any migration.
8. Reconnect providers one at a time after current integration guidance and sandbox tests. Preserve working behavior where demonstrated; do not assume any provider is mandatory.

No production activation is authorized by this inspection.