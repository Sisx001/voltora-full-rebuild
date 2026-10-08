# VOLTORA current rebuild status and handoff

## Authority and baseline

This is the current checklist. Both supplied continuation prompts remain the full scope, including real operations, isolated Design Preview and owner-controlled Go Live. `memory/PRD.md` archive notes and `docs/VOLTORA_ARCHIVE_REVIEW.md` are historical evidence, not current completion claims.

- Checkout baseline/current Git HEAD: `01921b03ca990bb08206d7ad61561d22e9f41407`.
- Public repository metadata reported the same `main` HEAD at inspection. No fetch performed; remote freshness beyond that lookup is not guaranteed.
- Changes are preserved in the working tree. No commits, pushes, deployment or production migration performed. Use Emergent **Save to GitHub** to preserve a reviewable commit; this workspace prohibits agent Git writes.
- Actual local test date: 2026-10-08. Fresh unique development DB configured privately; Mongo originally contained only system databases. No legitimate business data was imported, erased or migrated.
- Runtime: sandbox, external actions disabled. Provider configuration collection count: 0. Synthetic seeded design products and QA test records exist only in this new development namespace. Existing mock adapters remain a known blocker, not an acceptable real-operation implementation.

## Milestone 1: startup and recovery — implemented and verified locally

### Observed failure chain and repairs

1. Missing frontend/backend `.env` files caused backend `KeyError: MONGO_URL` and frontend `undefined/api`. Added explicit aggregated names-only validation, fresh private setup command, sanitized examples, and invalid API URL rejection before network requests.
2. Bootstrap used supervisor's UUID preview origin. The platform subsequently rewrote the protected frontend URL to the named preview alias. Browser POSTs then failed exact-Origin checks even though no-Origin backend tests passed. Preserved both existing protected URL values; created a new private `.env.local` containing only the exact approved supplemental preview origin. Added `scripts/check_environment.py`, Origin-aware tests and documentation. No CORS wildcard/reflection or MFA/CSRF weakening.
3. Recovery previously showed an uninformative page, hid the underlying reference, had no bounded in-flight UI, and linked directly to `/admin`. Implemented structured sanitized error references, a single-flight 12-second configuration GET, retry state, offline detection, response-shape checking, and admin-path-aware entry.
4. Storage writes previously ran on mount and could erase malformed local state or throw if storage was denied. Recovery now leaves persisted values untouched on mount, preserves in-memory state if writes fail, and does not clear cart/draft keys.
5. Replaced the last screenshot's sparse recovery UI with the original VOLTORA logo, responsive ivory/forest layout, bounded decorative animation, reduced-motion rules, keyboard focus and useful connection details.
6. Added test-only process synchronization for shared MFA credentials under mandatory parallel pytest. Application replay protection remains unchanged. Added matching Jest typings and made setupTests a module after new tests exposed build/type failures.

### Evidence (not a claim of full platform/provider verification)

| Check | Final observed result | Evidence |
|---|---|---|
| Backend regression suite, default parallel settings | 77 passed | `artifacts/backend-final-pytest.log`, `backend/tests/` |
| Origin-aware password/MFA, rejected untrusted origins, CSRF, cookie attributes | Passed in backend suite and actual browser | `test_origin_aware_auth.py`, final browser screenshots |
| Frontend unit suite | 47 passed | `frontend/src/lib/apiConfig.test.ts`, `artifacts/run47_evidence_gap_resolution.md` |
| Browser core workflow | 19 assertions passed | `tests/test_voltora_recovery_comprehensive.py`, `artifacts/TEST_RESULTS_SUMMARY.md` |
| Focused recovery/real draft key/preview checks | 16 assertions passed | `tests/test_voltora_recovery_focused.py`, `artifacts/run47_evidence_gap_resolution.md` |
| TypeScript and production bundle | Exit 0 for each | `yarn tsc --noEmit`, `yarn build`; matching logs noted in handoff |
| Cart and actual `voltora-draft-recovery:{user.id}` preservation | Exact bytes retained across failed + successful retry | Focused browser report (182-byte cart / 18890-byte draft fixtures) |
| Reconnect without reload + duplicate request prevention | Passed | Browser window sentinel retained; one in-flight GET |
| Store failure while owner APIs remain available | Real login, MFA and builder work | `artifacts/final-01-owner-authenticated.jpg`, `final-02-builder-interface.jpg` |
| Malformed response, aborted request, timeout, offline/online, malformed saved data, storage denial | Covered by focused/core browser checks | Reports above |
| Desktop and 390/320 mobile, keyboard reachability, reduced motion | Passed targeted checks | `final-03-mobile-390.jpg`, `final-04-mobile-320.jpg`, `final-05-reduced-motion.jpg` |
| Login selection, shared Footer highlight/global-impact label and device switches | Targeted checks passed | Focused browser report; correctness of every affected-route count not yet audited |

**Evidence limitations:** browser clipboard-copy completion remains unverified (automation reported an unstable element, not an application permission-fallback assertion). Full custom-admin-path browser journeys remain unverified. The full edit→autosave→explicit publish→visitor release switch→rollback browser acceptance is not complete; backend release/conflict/rollback regressions passed. First browser report's MFA/builder claims were rejected after screenshot review; only later actual MFA HTTP200/session assertions count. Test artifacts include historical failed screenshots for provenance.

Build succeeds with existing React hook dependency warnings. Standalone App.tsx lint reports existing route-array JSX key findings. No zero-bug, perfect-security, accessibility-certification, provider-verification or production-readiness claim. Fresh configuration is reproducible; a clean installation of every Python pin on a new container was not executed (provided dependencies were already installed). Tests use **MOCKED failure injection/test doubles only**; successful real provider operation is not simulated or claimed.

## Feature → UI → API → database inventory

This is a source-traced starting inventory, not proof that every control works. Backend routes below include `/api`; all collection names are scoped through `core.db` unless explicitly stated otherwise. Scope-prefixing does not prove authenticated tenant isolation.

| Domain | UI entry/source | API implementation | Persistence | Current state / next verification |
|---|---|---|---|---|
| Startup/store recovery | `App.tsx`, `StoreRecovery.tsx`, `store.tsx` | `server.py /health`, `catalog.py /store` | settings, site_workspace/site_releases; browser cart/recovery keys | Verified milestone scope |
| Owner/staff identity | OwnerEntry, AdminShell, Account MFA | `auth.py /auth/*`, permissions.py | users, sessions, login_attempts/history, roles, audit_logs | Owner+MFA and core guards tested; comprehensive expiry/revocation/recovery backlog |
| Customer identity | CustomerAuth, Account, CaptchaWidget | auth.py, auth_ext.py, accounts.py | users, sessions, otps, notifications | Registration/recovery delivery and CAPTCHA consistency partial/unverified |
| Builder / shared Header & Footer | admin/builder, ThemeGallery, store Header/Footer | `release_engine.py /admin/builder*` | site_workspace draft/version/active pointer, immutable site_releases | Existing implementation preserved; core release/conflict tests pass; full acceptance pending |
| Legacy CMS / SEO / scheduled publication | DesignStudio, legacy WebsiteBuilder, Settings | cms.py, publishing_jobs.py, server.py sitemap/robots | documents, revisions/previews, site_workspace/site_releases, scheduled jobs | Stale read/write paths remain to reconcile; sitemap reads legacy documents |
| Catalog / variants / inventory | StorePages, admin Catalog/Operations | catalog.py, admin.py | products, product_drafts, categories, brands, collections, inventory | Basic read/commerce regression passed; Buy Now and full concurrency audit pending |
| Cart / checkout / orders | Checkout, StoreProvider, admin Operations | commerce.py, payments.py | browser cart, orders, inventory reservations, payment_transactions | Basic idempotency tested; comprehensive pricing/stock/guest/payment reconciliation pending |
| Wishlist / comparison / reviews | StorePages, Account, Operations | accounts.py/catalog.py/admin.py | wishlist/customer data, reviews; browser compare | Present; full persistence/authorization/preview audit pending |
| Offers / coupons / affiliates | OfferPage, admin Offers/Affiliates | offers.py, affiliates.py, commerce.py | offer_pages/events, coupons, affiliates/ledger | Present, end-to-end unverified |
| Shipping / courier | Checkout LocationPicker, Locations/Couriers/Settings | locations.py, couriers.py | locations, shipments, orders, provider_configs | Source adapters exist; no real provider verification |
| Integrations / credentials | Connections, Providers, OAuth, Settings | providers_admin.py, auth_ext.py; providers/*; vault.py | provider_configs, OAuth config, sealed credentials | Fragmented; save/test external-action lock and evidence/version model incomplete |
| Notifications / mailbox | Header, Mailbox, Ops email templates | notifications.py, mailbox.py, email_admin.py | email_queue, notifications, mail_settings/aliases/messages/templates | Mailbox sending/receiving disconnected; queue worker not wired into lifespan |
| Mira / assistant | MiraWorkspace, MiraChat, Assistant, Workspace AI | mira_workspace.py, ai.py, ai_tools.py, ai_monitor.py | Mira config/settings, conversations/messages, ai_tasks/memories/logs | Config persistence/conflict tested; storefront/runtime propagation and real routing incomplete |
| Support / returns / account requests | Support, Account, SupportInbox | support.py, support_ext.py, accounts.py | conversations/messages, attachments, return_requests | Present; complete boundary/delivery verification pending |
| Media / storage | MediaLibrary, builder image controls | media.py | media metadata and current storage | Upload limits/chunking/versioned object storage/restore drills pending |
| Analytics / marketing / markets | Analytics, Monitor, MarketSettings, Ops | analytics_ext.py, monitor.py, market.py, risk.py, alerts.py | events, visitor_sessions, settings and operational logs | Present, labels and end-to-end behavior unverified |
| Credentialed Design Preview | No completed dedicated role entry | isolation.py currently rejects public demo start | Existing demo namespace machinery | Public anonymous demo correctly disabled; requested credentialed synthetic role/adoption missing |
| One-click Go Live / pause | No completed canonical readiness review | Future version-bound activation orchestration | Future activation config/version pointer/evidence | Missing; ordinary theme publish must stay separate |
| Tenant membership | Existing roles/workspace helpers | core.py + isolation.py + all domain APIs | prefixes and workspace context | Multi-tenant support not established; server-enforced membership audit required |

## Integration inventory and classification

No sandbox or production provider workflow has been verified in this milestone. Real credentials were not imported; no production action was enabled. Implementation, credentials, environment, enablement and health must be stored independently in the future canonical center.

| Capability/provider | Implementation classification | Credential state / environment / enablement | Operational evidence and exact remaining setup |
|---|---|---|---|
| SSLCommerz, bKash, Stripe, PayPal | Implemented but unconfigured | No provider records; sandbox runtime; external actions disabled | SSLCommerz identity/amount/currency unit checks pass, NOT provider verification. Need selected provider sandbox merchant/account keys, registered callback, controlled end-to-end payment/refund/duplicate/out-of-order/timeout tests |
| Mock payments / courier / SMS / email | Mock-only; still auto-registered | No active configs; must never be production fallback | Remove from live discovery/selection/execution; reject legacy saved mock configurations; keep doubles only in isolated tests/previews |
| SMS OTP | Missing real adapter | No SMS account; disabled/unverified | Select real SMS provider, obtain fresh API credentials/sender approval, authorize controlled recipient; test delivered/expiry/attempts/single-use |
| SMTP transactional email | Implemented but unconfigured | No account/config; external delivery disabled | Fresh SMTP host/account credentials and verified sending domain; send controlled recovery/notification and observe failures/retries |
| Mailbox sending/receiving | Missing operational connection | Draft workspace only; delivery/receiving report not_connected | Select mail provider and domain; verified DNS, authorized outbound credentials + inbound webhook/IMAP, delivery/receiving tests |
| Queue worker | Implemented but disabled/disconnected from startup | Paused; suppressed demo queue must not replay | Adopt platform recurring-task mechanism for execution, retry/observability and accepted vs delivered; never replay suppressed test jobs |
| Turnstile, reCAPTCHA, hCaptcha | Implemented but unconfigured | No site/secret keys; challenge tests unverified | Authorized domain + selected provider keys; valid/invalid/expired challenges, fail-closed required protection and controlled owner recovery |
| Google/Facebook/Apple OAuth | Adapters present; unverified | No authorized client setup in this milestone | Fresh developer client IDs/secrets, exact redirects, consent/test accounts; verified identity/account linking and staff boundaries |
| Pathao, Steadfast, RedX | Implemented but unconfigured | No courier credentials; disabled | Selected provider account and documented sandbox if one exists; explicitly approved controlled verification otherwise; booking/tracking/cancel/callback tests |
| Mira AI providers/models/tools | Partial implementation and disconnected config paths | No provider account enabled here; external actions locked | Decide provider/model using current integration playbook; fresh authorized credentials; test selected routing, knowledge, storefront propagation, permissions and tool approvals |
| Telegram notifications | Adapter present; unconfigured | No bot/chat setup; disabled | Fresh bot credentials/authorized chat and controlled delivery test |
| Cloudflare/domain/infrastructure | Adapter present; unconfigured | No infrastructure action authorized | Domain ownership, scoped token, exact DNS/HTTPS plan; verify without implying deployment authority |
| Storage/backups | Versioned object storage + tested restore missing | No storage account provisioned; no migration | Select provider, private bucket/versioning, scoped keys, backup encryption/retention, isolated restore drill and measured evidence |
| Analytics / scheduled publishing | Local modules present; operational audit pending | Local only; external health unknown | Consent/scoping validation and scheduled-task registration/execution evidence; don't infer from saved schedule or button |

Rechecked source gaps: providers auto-discovery imports mock adapters (`providers/__init__.py`); mock messaging logs content (`providers/messaging/mock.py`); real SMS adapter absent; mailbox send deliberately errors; `start_queue_worker` imported but not started by `server.py`; external-action middleware blocks provider configuration/sandbox tests; CAPTCHA credential validation must not be treated as successful challenge evidence. These are retained P0/P1 backlog items, not repaired by startup recovery.

## Complete remaining backlog, ordered milestones

### M2 — safe integration foundations (next)
- Separate configuration saving, mock/design preview, authorized provider sandbox, production operation and paused-state behavior.
- Exclude/reject mock providers from production discovery/selection/execution and legacy DB activation; remove sensitive messaging-body logging.
- Canonical owner Integration Center: supported capabilities, environment-specific sealed/write-only credentials, rotation, enablement, callbacks, setup steps, sanitized errors, verification timestamps/config hashes, rate limits/quotas/retries and operational evidence.
- Configuration changes invalidate verification. Connection checks are not workflow checks. No fake sandbox for providers without one. No payment fallback before reconciliation.
- Restore worker lifecycle using platform recurring-task skill; suppressed demo/OTP jobs never replay. Preserve callback/reconciliation processing when new operations paused.
- Local tests first; then request exact selected-provider credentials/controlled destinations. No real transactions without specific authorization.

### M3 — missing connections and credentialed design isolation
- Buy Now: owner visibility/text controls; variant/quantity/stock/server-price/checkout rules; preserve existing cart with explicit behavior.
- Customer registration/verification/login/logout/password recovery: consistent CAPTCHA, expiry/invalid/rate-limit/single-use/MFA/revocation tests and real delivery.
- Dedicated credentialed Design Preview role: own isolated draft + synthetic fixtures only; backend prohibits private data/secrets/live integrations/stock/orders/payments/staff/external actions/publication. Return to live site exits preview only. Owner adoption copies eligible presentation, never identities/inventory/credentials.
- Mira configuration actually drives appearance/greeting/visibility/language/personality/knowledge/provider/model/permissions; preserve server tool authorization.
- Reconcile legacy CMS restore/discard/history/theme preview/jobs/sitemap/public reads with release engine; no successful writes to unused stores.
- Complete admin-path helper adoption across remaining hardcoded routes; replace static environment/health labels with verified runtime evidence.

### M4 — builder and visual system completion
- One authoritative registry: home/shop/product/customer auth states/account/cart/checkout/order confirmation/tracking/wishlist/comparison/support/assistant/offers/custom pages.
- Shared Header/Footer and accurate affected-route impact; safe fixtures/editable templates for every dynamic page.
- Every persistent schema/design control must affect draft preview and published rendering; hierarchy, sections/components, inline editing, responsive overrides, reusable components, navigation/content/media/spacing/type/color/motion/visibility.
- Distinct industry compositions; separate real/demo/mixed preview catalogs. No synthetic live inventory promotion.
- Preview cannot mutate real sessions/carts/orders/messages/payments. Executable custom code stays disabled pending tested isolated design.
- Slow/overlapping autosaves, edits during save, errors/navigation/expiry/offline/conflicts tested without stale overwrite.
- Complete mandatory browser acceptance: MFA→Login states without replacing owner→edit/save→Footer highlight + accurate impact→desktop/tablet/mobile→review→explicit publish. Assert previous release until atomic switch and presentation-only rollback preserving commerce data.

### M5 — commerce and real-provider workflows
- Trace catalog/variants/inventory/cart/wishlist/compare/reviews/offers/coupons/shipping/checkout/orders/notifications/owner controls end to end.
- Server-authoritative price/stock/discount/shipping/totals; concurrent inventory and recoverable carts; idempotency and partial failures.
- Signed/validated callbacks with expected identity/amount/currency and duplicate/out-of-order handling; reconcile timeouts before retry/fallback. Guest/customer order boundaries.
- Real SMS/email OTP and recovery session revocation; delivery vs accepted statuses, observable failure/retry, mailbox inbound/outbound.
- Independently verify each enabled payment/courier/OAuth/CAPTCHA/email/AI/storage provider against current official docs and permitted controlled sandbox workflows. Mark exact credentials/approval blockers, not simulated success.
- Versioned object storage and proven backup/restore BEFORE any legitimate data migration.

### M6 — platform, activation and release candidate
- Mira real abstraction, tools, approvals and monitoring; audit analytics/marketing/SEO/localization/automation/support/settings and duplicated destinations.
- Decide tenancy based on evidence; enforce authenticated membership and server scoping across APIs/media/releases/jobs/secrets if required.
- Audit uploads, preview/custom content, sessions/permissions, secret handling, provider URLs and action controls; keyboard/focus/contrast/responsive/reduced motion/performance across all surfaces.
- Owner-only readiness review lists exact release/config versions, feature dependencies/optional disabled services, integration evidence, domain/HTTPS/auth/webhook/worker state, backup/restore and rollback.
- Final Go Live requires recent MFA and server-side checks bound to reviewed versions; controlled active pointer. Prepare external providers first; never claim cross-provider atomicity. Failure leaves previous state untouched; no mock fallback.
- Separate leaving preview, presentation publish, first operational activation, pausing new consequential actions, presentation/config rollback. Rollback never undoes charges/shipments/orders/customers or replays demo jobs.
- Prepare concrete release candidate, rollback procedure and tested restore evidence before production deployment/migration. No automatic production activation on passing development build.

## Exact next task and handoff

Next implementation: inventory/refactor `providers/__init__.py`, `providers/base.py`, `providers_admin.py`, `isolation.py` so saving disabled provider configuration works without production activation, and mock adapters cannot enter production discovery or execution. Add direct API regression tests first, with no external calls. Then introduce evidence/config-version state in the canonical Integration Center. Use current integration playbooks and ask for genuinely required provider credentials when real verification begins.

Startup/dependency commands and required variable names: `docs/STARTUP.md`. Private test credentials: ignored `memory/test_credentials.md` (fresh owner + TOTP, mode0600). No secret values belong in this document. Current QA releases may contain test headings/custom pages from backend acceptance runs; this is isolated synthetic presentation, not business content. Future test fixtures should restore only their own presentation changes using the release API; never reset legitimate records or reuse this catalog for live inventory.

Changed implementation: `backend/core.py`, `backend/runtime_config.py`, `backend/server.py`; setup/check scripts and sanitized env examples; frontend App/AdminShell/Header/adminPath/api/apiConfig/store/persistentState; new StoreRecovery + CSS; matching Jest types in package/lock. Tests/evidence: new runtime/setup/environment/origin regressions, MFA lock helper, enhanced e2e helpers, frontend unit and browser scripts. Documentation: this checklist, STARTUP, PRD current addendum, test_result and evidence summaries. No original logo replacement.
