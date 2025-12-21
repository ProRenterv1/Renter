from __future__ import annotations

from datetime import date
from typing import Iterable

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from payments.models import OwnerPayoutAccount

User = get_user_model()

REQUIREMENTS_CLEAR = {
    "currently_due": [],
    "eventually_due": [],
    "past_due": [],
    "disabled_reason": "",
}

FIRST_NAMES = [
    "Alex",
    "Taylor",
    "Jordan",
    "Morgan",
    "Casey",
    "Jamie",
    "Riley",
    "Cameron",
    "Drew",
    "Quinn",
    "Avery",
    "Charlie",
    "Dakota",
    "Harper",
    "Kai",
    "Logan",
    "Parker",
    "Reese",
    "Rowan",
    "Skyler",
]

LAST_NAMES = [
    "Nguyen",
    "Singh",
    "Patel",
    "Smith",
    "Brown",
    "Garcia",
    "Johnson",
    "Lee",
    "Martin",
    "Clark",
    "Wright",
    "Young",
    "Lewis",
    "Walker",
    "Hall",
    "King",
    "Scott",
    "Adams",
    "Baker",
    "Nelson",
]

ADDRESS_SEEDS = [
    {"street": "101 Jasper Ave", "city": "Edmonton", "province": "AB", "postal_code": "T5J 1N2"},
    {"street": "2458 River Rd", "city": "Calgary", "province": "AB", "postal_code": "T2P 1J9"},
    {"street": "88 Cedar St", "city": "Toronto", "province": "ON", "postal_code": "M5V 2T6"},
    {"street": "512 Maple Dr", "city": "Vancouver", "province": "BC", "postal_code": "V6B 1A1"},
    {"street": "9 Wellington St", "city": "Ottawa", "province": "ON", "postal_code": "K1P 1J1"},
    {"street": "333 104 Ave", "city": "Winnipeg", "province": "MB", "postal_code": "R3C 4T3"},
    {"street": "27 Whyte Ave", "city": "Halifax", "province": "NS", "postal_code": "B3H 1G1"},
    {"street": "1800 Grant St", "city": "Victoria", "province": "BC", "postal_code": "V8W 1N6"},
    {"street": "64 118 Ave", "city": "Regina", "province": "SK", "postal_code": "S4P 3Y2"},
    {"street": "7725 109 St", "city": "Saskatoon", "province": "SK", "postal_code": "S7K 1J5"},
]

BIRTH_DATES = [
    date(1984, 4, 12),
    date(1986, 9, 5),
    date(1988, 1, 27),
    date(1990, 6, 9),
    date(1992, 11, 18),
    date(1994, 3, 2),
    date(1996, 7, 14),
    date(1998, 12, 1),
    date(2000, 5, 21),
    date(2001, 8, 30),
]


def phone_generator(existing_numbers: set[str], start: int = 2025550000) -> Iterable[str]:
    current = start
    while True:
        phone = f"+1{current:010d}"
        current += 1
        if phone in existing_numbers:
            continue
        existing_numbers.add(phone)
        yield phone


class Command(BaseCommand):
    help = (
        "Populate users with profile details, verified email/phone, "
        "and mark 50% of users as ID verified."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=0,
            help="Number of new users to create before updating verification flags.",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="test-pass",
            help="Password for newly created users.",
        )
        parser.add_argument(
            "--preserve-existing-id-verified",
            action="store_true",
            help="Keep already verified users even if it exceeds 50%%.",
        )

    def handle(self, *args, **options) -> None:
        count = options["count"]
        password = options["password"]
        preserve_existing = options["preserve_existing_id_verified"]

        if count < 0:
            raise CommandError("--count must be >= 0.")

        with transaction.atomic():
            existing_phones = set(
                User.objects.exclude(phone__isnull=True)
                .exclude(phone="")
                .values_list("phone", flat=True)
            )
            phone_iter = phone_generator(existing_phones)

            created_count = self._create_users(count, password, phone_iter)
            users = list(User.objects.order_by("id"))
            if not users:
                self.stdout.write(self.style.WARNING("No users found. Nothing to update."))
                return

            updated_profiles = self._ensure_profile_details(users, phone_iter)
            verified_count, target_count, demoted_count = self._apply_id_verification(
                users,
                preserve_existing=preserve_existing,
            )

        self.stdout.write(self.style.SUCCESS("User population complete."))
        self.stdout.write(f"Created users: {created_count}")
        self.stdout.write(f"Profiles updated: {updated_profiles}")
        self.stdout.write(
            f"ID verification: {verified_count}/{len(users)} users " f"(target {target_count})."
        )
        if not preserve_existing:
            self.stdout.write(f"ID verification demoted: {demoted_count}")

    def _create_users(self, count: int, password: str, phone_iter: Iterable[str]) -> int:
        if count == 0:
            return 0

        base_username = "seeduser"
        existing_usernames = set(
            User.objects.filter(username__startswith=base_username).values_list(
                "username", flat=True
            )
        )

        index = 1
        while f"{base_username}{index}" in existing_usernames:
            index += 1

        for _ in range(count):
            username = f"{base_username}{index}"
            profile = self._profile_seed(index)
            index += 1
            email = f"{username}@example.com"
            phone = next(phone_iter)
            User.objects.create_user(
                username=username,
                email=email,
                phone=phone,
                password=password,
                email_verified=True,
                phone_verified=True,
                first_name=profile["first_name"],
                last_name=profile["last_name"],
                street_address=profile["street_address"],
                city=profile["city"],
                province=profile["province"],
                postal_code=profile["postal_code"],
                birth_date=profile["birth_date"],
            )
        return count

    def _ensure_profile_details(self, users: list[User], phone_iter: Iterable[str]) -> int:
        updated_users: list[User] = []
        for user in users:
            profile = self._profile_seed(user.id or 1)
            changed = False
            if not (user.email or "").strip():
                user.email = f"user{user.id}@example.com"
                changed = True
            if not (user.phone or "").strip():
                user.phone = next(phone_iter)
                changed = True
            if not user.email_verified:
                user.email_verified = True
                changed = True
            if not user.phone_verified:
                user.phone_verified = True
                changed = True
            if not (user.first_name or "").strip():
                user.first_name = profile["first_name"]
                changed = True
            if not (user.last_name or "").strip():
                user.last_name = profile["last_name"]
                changed = True
            if not (user.street_address or "").strip():
                user.street_address = profile["street_address"]
                changed = True
            if not (user.city or "").strip():
                user.city = profile["city"]
                changed = True
            if not (user.province or "").strip():
                user.province = profile["province"]
                changed = True
            if not (user.postal_code or "").strip():
                user.postal_code = profile["postal_code"]
                changed = True
            if not user.birth_date:
                user.birth_date = profile["birth_date"]
                changed = True
            if changed:
                updated_users.append(user)

        if updated_users:
            User.objects.bulk_update(
                updated_users,
                [
                    "email",
                    "phone",
                    "email_verified",
                    "phone_verified",
                    "first_name",
                    "last_name",
                    "street_address",
                    "city",
                    "province",
                    "postal_code",
                    "birth_date",
                ],
            )
        return len(updated_users)

    def _profile_seed(self, seed_index: int) -> dict[str, object]:
        safe_index = max(seed_index, 1)
        first_name = FIRST_NAMES[safe_index % len(FIRST_NAMES)]
        last_name = LAST_NAMES[safe_index % len(LAST_NAMES)]
        address = ADDRESS_SEEDS[safe_index % len(ADDRESS_SEEDS)]
        birth_date = BIRTH_DATES[safe_index % len(BIRTH_DATES)]
        return {
            "first_name": first_name,
            "last_name": last_name,
            "street_address": address["street"],
            "city": address["city"],
            "province": address["province"],
            "postal_code": address["postal_code"],
            "birth_date": birth_date,
        }

    def _apply_id_verification(
        self, users: list[User], preserve_existing: bool
    ) -> tuple[int, int, int]:
        users_sorted = [user for user in users if user.id is not None]
        users_sorted.sort(key=lambda user: user.id)
        total_users = len(users_sorted)
        target_count = total_users // 2

        selected_ids: set[int] = set()
        if preserve_existing:
            selected_ids.update(
                OwnerPayoutAccount.objects.filter(
                    user_id__in=[user.id for user in users_sorted],
                    is_fully_onboarded=True,
                ).values_list("user_id", flat=True)
            )
            if len(selected_ids) < target_count:
                for user in users_sorted:
                    if user.id not in selected_ids:
                        selected_ids.add(user.id)
                        if len(selected_ids) >= target_count:
                            break
        else:
            selected_ids.update(user.id for user in users_sorted[:target_count])

        now = timezone.now()
        existing_accounts = set(
            OwnerPayoutAccount.objects.filter(user_id__in=selected_ids).values_list(
                "user_id", flat=True
            )
        )

        to_create = [
            OwnerPayoutAccount(
                user=user,
                stripe_account_id=f"acct_seed_{user.id}",
                payouts_enabled=True,
                charges_enabled=True,
                is_fully_onboarded=True,
                requirements_due=REQUIREMENTS_CLEAR.copy(),
                last_synced_at=now,
            )
            for user in users_sorted
            if user.id in selected_ids and user.id not in existing_accounts
        ]
        if to_create:
            OwnerPayoutAccount.objects.bulk_create(to_create)

        if selected_ids:
            OwnerPayoutAccount.objects.filter(user_id__in=selected_ids).update(
                payouts_enabled=True,
                charges_enabled=True,
                is_fully_onboarded=True,
                requirements_due=REQUIREMENTS_CLEAR,
                last_synced_at=now,
            )

        demoted_count = 0
        if not preserve_existing:
            demoted_count = OwnerPayoutAccount.objects.exclude(user_id__in=selected_ids).update(
                payouts_enabled=False,
                charges_enabled=False,
                is_fully_onboarded=False,
            )

        return len(selected_ids), target_count, demoted_count
