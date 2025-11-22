# Security Policy – Renter Platform

This document describes the current security posture of the Renter codebase
(Django + DRF backend, React frontend, Stripe, S3, Redis, Celery) and the
expected practices for contributors.

---

## 1. Supported Environments

We distinguish between three main environments:

- **Local / Dev**
  - `DJANGO_DEBUG=True`
  - May use `localhost` DB/Redis, test Stripe keys, local file storage.
- **Staging**
  - `DJANGO_DEBUG=False`
  - Uses production-like services with test keys and staged data.
- **Production**
  - `DJANGO_DEBUG=False`
  - Real Stripe keys, S3, AV scanning, Twilio, Anymail, etc.

**Production requirements:**

- `DEBUG=False`
- `ALLOWED_HOSTS` **whitelist** of real domains only.
- `CORS_ALLOW_ALL_ORIGINS=False` and explicit `CORS_ALLOWED_ORIGINS`.
- All secrets provided via environment variables or secret store.

---

## 2. Secrets Management

All sensitive values **must** come from environment variables (or secret manager):

- `DJANGO_SECRET_KEY`
- Database credentials and URLs (`DATABASE_URL`)
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- `STRIPE_CONNECT_WEBHOOK_SECRET` (if separate)
- `ANYMAIL_SENDGRID_API_KEY`
- `TWILIO_*` credentials
- `REDIS_URL`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`
- `GOOGLE_MAPS_API_KEY` (or any other third-party API keys)

**Rules:**

1. **Never** commit secrets to git (including test keys).
2. Rotate any secret that was ever:
   - committed,
   - pasted into a ticket,
   - shared in plaintext.
3. Use different keys per environment (dev/stage/prod).

---

## 3. Authentication & Authorization

### 3.1 Authentication

- Custom `User` model with:
  - unique email,
  - `email_verified` / `phone_verified`,
  - flags for 2FA and login alerts.
- Login is via token endpoint (JWT) with optional **two-factor verification**.
- Password reset and contact verification codes are stored hashed.

**Invariants:**

- All auth endpoints are rate-limited (see section 7).
- 2FA-required accounts **must** go through the 2FA challenge flow.
- Login alerts never contain sensitive data (no passwords, no tokens).

### 3.2 Account Verification & Permissions

There are explicit gates for using the marketplace:

- To **rent**:
  - `email_verified == True`
  - `phone_verified == True`
  - `can_rent == True`
- To **list**:
  - `email_verified == True`
  - `phone_verified == True`
  - `can_list == True`

These conditions are enforced in:

- Booking create serializers
- Listing create/update serializers

### 3.3 Object-Level Access Control

- Listings:
  - Publicly readable.
  - Only the owner can create/update/delete.
- Bookings:
  - Only **participants** (renter or listing owner) can read or act on a booking.
- Admin / staff endpoints:
  - Restricted to `is_staff` or explicit admin permission classes.

Any new viewsets or endpoints **must**:

- Use DRF permission classes (`IsAuthenticated`, `IsOwnerOrReadOnly`, etc.).
- Enforce object-level permissions where applicable.

---

## 4. Payments & Financial Security

Payments are handled via **Stripe** only; the backend:

- Never stores card numbers or raw payment data.
- Uses:
  - PaymentIntents for booking rental charges.
  - Manual-capture PaymentIntents for damage deposits.
- Uses webhook verification with Stripe’s signing secret.

### 4.1 Booking Payment Structure

For each booking, the backend:

- Computes totals server-side (rental subtotal, service fee, deposit).
- Creates two PaymentIntents:
  - Charge (rental + service fee) – captured immediately.
  - Deposit hold – manual capture.
- Saves Stripe IDs on the booking.
- Logs all financial activity via a **Transaction ledger**.

**Client must never send the “amount to charge”**; amounts are derived on the server.

### 4.2 Transaction Ledger

Each money-related event is logged as a `Transaction` with:

- `kind` (e.g. `BOOKING_CHARGE`, `OWNER_EARNING`, `PLATFORM_FEE`,
  `DAMAGE_DEPOSIT_CAPTURE`, `DAMAGE_DEPOSIT_RELEASE`, `REFUND`, etc.).
- `user`, `booking`, `amount`, `currency`, `stripe_id`.

All owner balances, payouts, and earnings APIs **must** derive their data from this ledger.

### 4.3 Stripe Connect

- Owners are onboarded via Stripe Express (Connect accounts).
- Requirements and disabled reasons are synced via webhooks.
- Payout summary and history endpoints read from the ledger + Stripe Connect state.

**Do not** build any direct payout logic outside of Stripe Connect + ledger.

---

## 5. File Uploads & Antivirus

The platform supports uploads for listings, bookings, and receipts.

### 5.1 Storage

- Local filesystem in dev.
- S3 in staging/production (bucket with private or read-only public access).
- uploads use either:
  - direct presigned PUT URLs, or
  - server-side upload with explicit validation.

### 5.2 AV Scanning

- ClamAV is integrated via Celery tasks.
- Uploaded files go through an AV pipeline:
  - initial status = `PENDING`,
  - scanned in background,
  - only `CLEAN` files are considered visible/active.

New upload flows **must**:

- Use existing AV pipeline (same status flags / enums).
- Ensure the API and UI never expose non-clean files.

---

## 6. Identity Verification & Booking Limits

High-risk bookings are gated by ID verification (Stripe Identity):

- `IdentityVerification` records link users to Stripe verification sessions.
- Webhook from Stripe marks users as verified on successful checks.
- Until verified, users are limited by configuration:
  - max replacement value,
  - max damage deposit,
  - max rental duration.

Booking creation logic **must**:

- Enforce these limits for **unverified** users.
- Remove these limits for **verified** users.

Listings may also be restricted (e.g., certain high-value tools only rentable from verified owners).

---

## 7. Rate Limiting & Abuse Protection

To mitigate brute force and abuse:

- DRF throttling is configured for:
  - Login / token endpoints.
  - Password reset / verification endpoints.
- Custom view throttles can be added for:
  - Chat/message posting.
  - Expensive search/list endpoints.

Any new public-facing or auth-related endpoint **should** consider:

- Applying an existing throttle class, or
- Introducing a specific throttle scope for that endpoint.

---

## 8. Logging, Monitoring & Incident Response

### 8.1 Logging

The backend logs:

- Errors and exceptions.
- Key state transitions:
  - Booking lifecycle changes (requested → confirmed → paid → completed/canceled).
  - Payment events (charges, refunds, deposit captures).
  - Identity verification results.
- Important admin or account-level changes.

Logs **must not** contain:

- Full card numbers or PANs.
- Raw passwords or password reset tokens.
- Full Stripe webhook payloads containing sensitive card details.

### 8.2 Monitoring

Recommended (and expected for production):

- Application error tracking (e.g. Sentry) for backend + frontend.
- Metrics / dashboards for:
  - HTTP 5xx rate,
  - Stripe API errors,
  - AV scanner failures,
  - Celery queue health.

### 8.3 Incident Response (High-Level)

In case of suspected security incident:

1. **Triage**
   - Identify scope (which users, which component, which timeframe).
   - Capture logs and evidence.
2. **Contain**
   - Rotate potentially compromised secrets.
   - Disable relevant features or endpoints if needed.
3. **Eradicate & Recover**
   - Patch the root cause, redeploy.
   - Validate via tests and staging.
4. **Notify**
   - Communicate with affected users if their data may be impacted.
   - Document the incident and fixes (internal post-mortem).

---

## 9. Dependencies & Static Analysis

We use multiple tools to keep the codebase secure:

- **Bandit** for Python static security analysis.
  - Run on backend with test directories excluded or using `# nosec` where needed.
- **pip-audit** for Python dependencies vulnerabilities.
- `npm audit` / `pnpm audit` / `yarn audit` for frontend dependencies.
- `pytest --ds renter.settings.test` (incl. unit and integration tests) for behavior and regression testing.

### 9.1 Recommended Commands

```bash
# Python security tools
pip-audit
bandit -r backend -x "*/tests/*"

# Frontend dependencies
npm audit   # or pnpm/yarn equivalent

# Test suite
pytest --ds renter.settings.test
