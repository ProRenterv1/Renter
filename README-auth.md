# Authentication API Reference

This document summarizes the auth/account endpoints exposed under `/api/users/`.

## Endpoints

| Path | Method | Description | Request Body | Response |
|------|--------|-------------|--------------|----------|
| `/api/users/signup/` | POST | Create an account with email or phone | `username?`, `email?`, `phone?`, `password`, `first_name?`, `last_name?`, `can_rent`, `can_list` | `201` JSON of created user |
| `/api/users/token/` | POST | Obtain JWT pair using `identifier` (email/phone/username) + `password` | `{ "identifier": "", "password": "" }` | `200` `{ "access": "...", "refresh": "..." }` |
| `/api/users/token/refresh/` | POST | Refresh JWT | `{ "refresh": "" }` | `200` `{ "access": "...", "refresh": "...optional..." }` |
| `/api/users/me/` | GET/PATCH | Retrieve or update the current profile | n/a / partial profile fields | `200` profile JSON |
| `/api/users/password-reset/request/` | POST | Send a 6‑digit code to email or phone | `{ "contact": "email or phone" }` | Always `200` `{ "ok": true, "challenge_id?": 123 }` |
| `/api/users/password-reset/verify/` | POST | Verify a code (challenge id or contact) | `{ "challenge_id?": 123, "contact?": "", "code": "" }` | On success `200` `{ "verified": true, "challenge_id": 123 }` |
| `/api/users/password-reset/complete/` | POST | Finish reset and set a new password | `{ "challenge_id?": 123, "contact?": "", "code": "", "new_password": "" }` | `200` `{ "ok": true }` |

## Required Environment Keys

Set these in `backend/.env` (dev defaults exist but production requires real values):

```
DEFAULT_FROM_EMAIL=notifications@example.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend  # or Anymail backend
SENDGRID_API_KEY=...   # only if using SendGrid/Anymail
TWILIO_ACCOUNT_SID=AC....
TWILIO_AUTH_TOKEN=....
TWILIO_FROM_NUMBER=+15551230000
FRONTEND_ORIGIN=https://app.example.com
```

## cURL Examples

```bash
# Signup with email
curl -X POST http://localhost:8000/api/users/signup/ \
  -H "Content-Type: application/json" \
  -d '{"email":"new@example.com","password":"StrongPass123!","can_rent":true,"can_list":false}'

# Login
curl -X POST http://localhost:8000/api/users/token/ \
  -H "Content-Type: application/json" \
  -d '{"identifier":"new@example.com","password":"StrongPass123!"}'

# Password reset request
curl -X POST http://localhost:8000/api/users/password-reset/request/ \
  -H "Content-Type: application/json" \
  -d '{"contact":"new@example.com"}'

# Password reset verify
curl -X POST http://localhost:8000/api/users/password-reset/verify/ \
  -H "Content-Type: application/json" \
  -d '{"challenge_id":123,"code":"123456"}'

# Password reset complete
curl -X POST http://localhost:8000/api/users/password-reset/complete/ \
  -H "Content-Type: application/json" \
  -d '{"challenge_id":123,"code":"123456","new_password":"NewSecret123!"}'
```
