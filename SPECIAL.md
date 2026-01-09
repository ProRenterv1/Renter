# Seed Management Commands

Management commands for loading demo data into the Django backend. Run them in this order: users → listings → bookings.

## Running commands
- From Docker Compose: `cd infra && docker compose exec api python manage.py <command> [flags]`
- From host virtualenv: `cd backend && python manage.py <command> [flags]`

## Commands (details & flags)
- `populate_users`
  - What it does: Creates `count` new users (if `count > 0`) with emails `seeduser<N>@example.com`, unique phones, verified email/phone, and profile fields filled. Ensures existing users also have verified contact info and profile fields. Marks 50% of users ID-verified via `OwnerPayoutAccount` (using Stripe-like ids) unless you opt to preserve current verified users.
  - Flags:
    - `--count <n>` (int, default `0`): number of new seed users to create. `0` only updates existing users.
    - `--password <pwd>` (str, default `test-pass`): password for newly created users.
    - `--preserve-existing-id-verified` (switch): if set, keeps already fully-onboarded users verified even if that means more than 50% stay verified; otherwise the command demotes users above the 50% target.
- `populate_listings`
  - What it does: Ensures the default categories exist/are populated, then creates `count` listings round-robin across users (prefers `can_list=True`, falls back to all users). Every 5th listing is marked unavailable; the rest are available/active/not deleted. Optionally attaches listing photos.
  - Flags:
    - `--count <n>` (int, default `20`): number of listings to create.
    - `--photos-per-listing <n>` (int, default `2`): number of photos per listing; set `0` to skip photo creation.
  - Prereq: users exist (ideally with `can_list=True`).
- `populate_bookings`
  - What it does: Generates bookings across a set of lifecycle scenarios (requested, confirmed, renter-canceled, paid future, paid start-day, in-progress with before photos, completed, and recently completed) using existing listings and renters. Creates payment/deposit ids when scenarios require, adds before/after photos per scenario, sets timeline fields, and enforces verified renters when required by listing limits.
  - Flags:
    - `--count <n>` (int, default `20`): total bookings to create across the scenario cycle.
    - `--photos-per-booking <n>` (int, default `2`): number of photos for each before/after set when the scenario includes photos; must be > 0.
  - Prereqs: active & available listings and renters (`can_rent=True`); run `populate_users` then `populate_listings` first. Verified payout accounts (from `populate_users`) let the command pick verified renters when required.

## Suggested flow
```bash
cd infra
docker compose exec api python manage.py migrate
docker compose exec api python manage.py populate_users --count 25 --password example-pass
docker compose exec api python manage.py populate_listings --count 20 --photos-per-listing 2
docker compose exec api python manage.py populate_bookings --count 20 --photos-per-booking 2
```
Adjust counts or photo settings as needed for your dataset size.
