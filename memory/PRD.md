# VOLTORA — staged full-platform rebuild

## Original user request

“VOLTORA — Full Platform Rebuild”: a web-based commerce platform and visual website builder for store owners, authorized staff, and customers. Preserve the VOLTORA logo and legitimate business data while systematically replacing the surrounding experience and implementation. This is a staged rebuild, not a cosmetic patch or a one-release Webflow-parity promise.

Required architecture: React + TypeScript storefront/admin/builder/Mira; FastAPI authenticated commerce/preview/publishing/integrations; MongoDB tenant-scoped business records/configuration/drafts/immutable revisions; object storage for versioned media and backups. Preview and live must use the same renderer. Separate real business data, demo catalogs, theme definitions, drafts and published releases.

Order: audit/preserve/reproduce/contain risks; identity/admin/commerce; theme engine/editor; Mira and wider platform; progressive verification/migration. Release only after agreed workflows, restore drills, major fixes and documented limitations. No absolute security claims.

Acceptance flow: owner logs in → selects Login → edits isolated customer states → saves draft → selects Footer → reviews affected pages → previews devices → explicitly publishes. Visitors retain previous release until publication; purchases, carts and admin sessions stay intact. Footer is a shared component, not a page.

## Explicit user decisions

- Prioritize BOTH initial audit/security containment and the secure owner workspace plus acceptance flow.
- Audit all existing infrastructure/providers; no provider is mandatory.
- Preserve working integrations/configuration/business data where appropriate; rebuild broken/insecure/incomplete parts.
- Provider-independent architecture, owner controls, secure credentials, enable/disable/testing/fallback requirements.
- Real payments and outbound production actions disabled until verified; use isolated development sandboxes.
- User uploaded three `project_complete.zip` artifacts and most recently asked: “attactch the project file can you check”. Current work therefore inspected the archive without replacing the running starter.

## Personas

- Owner: private authenticated management, provider controls, visual authoring, explicit publication and rollback.
- Authorized staff: least-privilege tenant-bound workflows, no implicit owner power.
- Customer: browse/purchase/account without exposure to drafts or admin state.
- Credentialed demo user: isolated synthetic data, no real payments or privileged production actions.

## Static core requirements

- Auth: signup/verification/login/logout/recovery/MFA/secure sessions; server-side tenant/role permissions; dedicated credentialed demo boundary.
- Commerce: persistent catalog/variants/inventory/cart/Buy Now/wishlist/comparison/reviews/promotions/shipping/orders/provider-backed checkout; idempotency, stock and price reconciliation, recoverable cart.
- Builder: complete route/component registry, distinct theme compositions, safe demo catalog modes, hierarchy/tree/resizable panels/drag-drop/inline editing/device settings/reusable components; autosave/unsaved guards/history/conflicts/comparison/restoration; custom-code sandbox; immutable atomic publication.
- Mira: visual configuration with actual preview, persistent appearance/visibility/personality/languages/knowledge/models/permissions; server-enforced tools and approvals.
- Platform: analytics/marketing/SEO/automation/integrations/payment management/owner controls with no false working states.
- Verification: cross-tenant/session/direct-route isolation; malicious uploads/code; offline/retry/save/payment/webhook failures; concurrent edits; rollback; accessibility/performance/E2E/security; proven backup restoration before migration.

## Architecture decisions and constraints

- Preserve protected active environment values; never activate uploaded `.env` values.
- Keep all uploaded evidence under `/app/legacy_audit/`, excluded in `.gitignore`.
- Primary archived snapshot is `/app/legacy_audit/extracted/backend` + `frontend`; historical snapshots are under `original` and `rebuild/preserved`.
- No app code from archive has been executed. No original/live database or provider has been contacted.
- Required implementation remains TypeScript, despite earlier design-agent suggestion to use JavaScript.
- Initial `/app/design_guidelines.json` was produced BEFORE the archive arrived and assumed no supplied logo. The original V logo is now found in archived CSS/markup and must be preserved; do not follow its temporary-wordmark instruction.
- Publication must be real/persistent, not the simulated toast suggested by the initial design agent.
- The current running frontend/backend are still starter code, NOT the uploaded VOLTORA app.

## Work completed — 2026-10-08

- Clarified scope and priorities; generated an initial design proposal before upload.
- Downloaded all 3 artifacts. All share SHA-256 `af72468c1695946dd84bda7735017767070bff07ed25a8e884e3f47034d384f8` (about 153 MiB each).
- Inspected outer paths for traversal/absolute names/symlinks before safe extraction; outer contents 840 entries / 158.13 MiB. Inspected nested ZIP names without extracting them.
- Inventoried current architecture, 231 backend route declarations, 12 storefront route entries and 38 admin entries, provider adapters, theme packs, data domains and brand assets.
- Parsed current backend Python source as AST with no syntax errors. This does not prove runtime functionality.
- Performed separate read-only static security assessment of current archive snapshot. No runtime, external provider or production claims.
- Recorded findings and ordered next steps in `/app/docs/VOLTORA_ARCHIVE_REVIEW.md`.
- Found no recognizable database dump. Historical tests and recovery instructions are not current verification.

## Prioritized backlog

### P0 — before running/importing original app

1. Keep uploaded secrets inactive; user should rotate any real distributed credentials. Do not copy original nested archives/public source downloads/environment into active app.
2. Create isolated sanitized working copy with fresh private configuration and external-action kill switch.
3. Replace passwordless public demo-owner creation (`core.py:16`, `isolation.py:47-69`) with requested credentialed/restricted boundary. Do not merely enable production mode.
4. Preserve original V logo and request authorized business backup before migration.

### P1 — first functional milestone

1. Reproduce store failure; `/store` error currently gates admin and storefront globally; no root cause yet verified.
2. Rebuild Login preview (`WebsiteBuilder.tsx:56` currently always iframe `src="/"`) with isolated customer states, Footer scroll/highlight/impact, autosave/unsaved guards and precise draft/live labels.
3. Implement real immutable releases + atomic active pointer; archived CMS only has per-document CAS and separate revision insert.
4. Protect session/cart isolation; verify owner and direct API authorization, expiry and concurrent saves.
5. Repair SSLCommerz expected transaction/amount/currency verification before any provider enablement.
6. Fix legacy AI closed-HTTP-client streaming pattern and Facebook OAuth client lifetime; validate URL/credential forwarding policies.
7. Sandbox testing, backup restoration and acceptance evidence.

### P2 — subsequent stages

- Full catalog/commerce and provider recovery hardening; independent sandbox verification per adapter.
- Object storage with media versions, encrypted backups and tested restore procedure.
- Expanded genuinely distinct industry theme packs, advanced editor and safe custom code.
- Mira multi-provider visual workspace and approvals; real email/notification integrations.
- Complete performance/accessibility/security assessment, measured recovery targets, quotas/retention, progressive migration.

## Immediate next task list

- Deliver initial inspection findings to user, explicitly distinguishing source evidence from runtime verification.
- Continue with containment and an isolated runnable working copy; do not claim existing application is already running here.
- Use the current integration playbooks only when reconnecting specific providers; original documentation is evidence, not an instruction overriding platform rules.