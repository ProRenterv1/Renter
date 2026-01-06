from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from itertools import cycle
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from bookings.models import Booking, BookingPhoto
from core.settings_resolver import get_int
from listings.models import Listing
from listings.services import compute_booking_totals
from payments.models import OwnerPayoutAccount

User = get_user_model()


@dataclass(frozen=True)
class Scenario:
    key: str
    status: str
    paid: bool = False
    deposit_authorized: bool = False
    pickup_confirmed: bool = False
    before_photos: bool = False
    after_photos: bool = False
    renter_returned: bool = False
    owner_return_confirmed: bool = False
    canceled_by: str | None = None
    canceled_reason: str = ""


SCENARIOS = [
    Scenario(key="requested", status=Booking.Status.REQUESTED),
    Scenario(key="confirmed", status=Booking.Status.CONFIRMED),
    Scenario(
        key="canceled_renter",
        status=Booking.Status.CANCELED,
        canceled_by=Booking.CanceledBy.RENTER,
        canceled_reason="Renter canceled the request.",
    ),
    Scenario(key="paid_future", status=Booking.Status.PAID, paid=True),
    Scenario(
        key="paid_start_day",
        status=Booking.Status.PAID,
        paid=True,
        deposit_authorized=True,
    ),
    Scenario(
        key="in_progress",
        status=Booking.Status.PAID,
        paid=True,
        deposit_authorized=True,
        pickup_confirmed=True,
        before_photos=True,
    ),
    Scenario(
        key="completed",
        status=Booking.Status.COMPLETED,
        paid=True,
        deposit_authorized=True,
        pickup_confirmed=True,
        before_photos=True,
        after_photos=True,
        renter_returned=True,
        owner_return_confirmed=True,
    ),
    Scenario(
        key="completed_recent",
        status=Booking.Status.COMPLETED,
        paid=True,
        deposit_authorized=True,
        pickup_confirmed=True,
        before_photos=True,
        after_photos=True,
        renter_returned=True,
        owner_return_confirmed=True,
    ),
]


class Command(BaseCommand):
    help = "Populate bookings with existing listings and users across lifecycle stages."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Number of bookings to create.",
        )
        parser.add_argument(
            "--photos-per-booking",
            type=int,
            default=2,
            help="Number of photos to create for each before/after role when required.",
        )

    def handle(self, *args, **options) -> None:
        count = options["count"]
        photos_per_booking = options["photos_per_booking"]

        if count <= 0:
            raise CommandError("--count must be greater than 0.")
        if photos_per_booking <= 0:
            raise CommandError("--photos-per-booking must be greater than 0.")

        listings = list(
            Listing.objects.select_related("owner")
            .filter(is_active=True, is_available=True, is_deleted=False)
            .order_by("id")
        )
        if not listings:
            raise CommandError("No active listings found. Seed listings before bookings.")

        renters = list(User.objects.filter(can_rent=True).order_by("id"))
        if not renters:
            raise CommandError("No rentable users found. Seed users before bookings.")

        verified_user_ids = set(
            OwnerPayoutAccount.objects.filter(is_fully_onboarded=True).values_list(
                "user_id", flat=True
            )
        )
        if not verified_user_ids:
            self.stdout.write(
                self.style.WARNING("No verified users found; verified-only rules may be skipped.")
            )

        max_days_unverified = get_int("MAX_BOOKING_DAYS", settings.UNVERIFIED_MAX_BOOKING_DAYS)
        max_repl = settings.UNVERIFIED_MAX_REPLACEMENT_CAD
        max_dep = settings.UNVERIFIED_MAX_DEPOSIT_CAD

        listings_cycle = cycle(listings)
        renters_cycle = cycle(renters)
        now = timezone.now()
        today = timezone.localdate()
        created = 0

        with transaction.atomic():
            for index in range(count):
                scenario = SCENARIOS[index % len(SCENARIOS)]
                batch = index // len(SCENARIOS)
                timeline = self._build_timeline(scenario, batch, now, today)

                start_date = timeline["start_date"]
                end_date = timeline["end_date"]

                listing = self._select_listing(
                    listings,
                    listings_cycle,
                    start_date,
                    end_date,
                    needs_deposit=scenario.deposit_authorized,
                    active_state=scenario.status in {Booking.Status.CONFIRMED, Booking.Status.PAID},
                )

                requires_verified = self._requires_verified(
                    listing=listing,
                    start_date=start_date,
                    end_date=end_date,
                    max_days_unverified=max_days_unverified,
                    max_repl=max_repl,
                    max_dep=max_dep,
                )
                renter = self._select_renter(
                    renters,
                    renters_cycle,
                    listing.owner_id,
                    requires_verified=requires_verified,
                    verified_user_ids=verified_user_ids,
                )
                self._ensure_contact_verified(renter)

                totals = compute_booking_totals(
                    listing=listing,
                    start_date=start_date,
                    end_date=end_date,
                )

                payment_id = f"pi_charge_seed_{index + 1}" if scenario.paid else ""
                deposit_hold_id = ""
                deposit_amount = listing.damage_deposit_cad or 0
                if scenario.deposit_authorized and deposit_amount > 0:
                    deposit_hold_id = f"pi_deposit_seed_{index + 1}"

                booking = Booking.objects.create(
                    listing=listing,
                    owner=listing.owner,
                    renter=renter,
                    start_date=start_date,
                    end_date=end_date,
                    status=scenario.status,
                    totals=totals,
                    charge_payment_intent_id=payment_id,
                    deposit_hold_id=deposit_hold_id,
                    renter_stripe_customer_id=(f"cus_seed_{renter.id}" if scenario.paid else ""),
                    renter_stripe_payment_method_id=(
                        f"pm_seed_{renter.id}" if scenario.paid else ""
                    ),
                    deposit_attempt_count=1 if scenario.deposit_authorized else 0,
                    deposit_authorized_at=timeline.get("deposit_authorized_at"),
                    pickup_confirmed_at=timeline.get("pickup_confirmed_at"),
                    before_photos_uploaded_at=timeline.get("before_photos_uploaded_at"),
                    returned_by_renter_at=timeline.get("returned_by_renter_at"),
                    return_confirmed_at=timeline.get("return_confirmed_at"),
                    after_photos_uploaded_at=timeline.get("after_photos_uploaded_at"),
                    deposit_release_scheduled_at=timeline.get("deposit_release_scheduled_at"),
                    deposit_released_at=timeline.get("deposit_released_at"),
                    dispute_window_expires_at=timeline.get("dispute_window_expires_at"),
                    canceled_by=scenario.canceled_by,
                    canceled_reason=scenario.canceled_reason or None,
                    auto_canceled=False,
                    before_photos_required=True,
                    deposit_locked=False,
                    is_disputed=False,
                )

                if scenario.before_photos:
                    self._create_booking_photos(
                        booking=booking,
                        uploaded_by=renter,
                        role=BookingPhoto.Role.BEFORE,
                        count=photos_per_booking,
                    )
                if scenario.after_photos:
                    self._create_booking_photos(
                        booking=booking,
                        uploaded_by=renter,
                        role=BookingPhoto.Role.AFTER,
                        count=photos_per_booking,
                    )

                created += 1

        self.stdout.write(self.style.SUCCESS("Booking population complete."))
        self.stdout.write(f"Bookings created: {created}")

    def _build_timeline(self, scenario: Scenario, batch: int, now, today) -> dict[str, object]:
        timeline: dict[str, object] = {}
        if scenario.key == "requested":
            start_date = today + timedelta(days=7 + batch * 2)
            end_date = start_date + timedelta(days=2)
        elif scenario.key == "confirmed":
            start_date = today + timedelta(days=5 + batch * 2)
            end_date = start_date + timedelta(days=3)
        elif scenario.key == "canceled_renter":
            start_date = today + timedelta(days=6 + batch * 2)
            end_date = start_date + timedelta(days=2)
        elif scenario.key == "paid_future":
            start_date = today + timedelta(days=3 + batch * 2)
            end_date = start_date + timedelta(days=2)
        elif scenario.key == "paid_start_day":
            start_date = today
            end_date = start_date + timedelta(days=2)
            timeline["deposit_authorized_at"] = now - timedelta(hours=1)
        elif scenario.key == "in_progress":
            start_date = today - timedelta(days=1 + batch)
            end_date = start_date + timedelta(days=3)
            timeline["deposit_authorized_at"] = now - timedelta(days=1, hours=1)
            timeline["before_photos_uploaded_at"] = now - timedelta(days=1, hours=3)
            timeline["pickup_confirmed_at"] = now - timedelta(hours=6)
        elif scenario.key == "completed":
            start_date = today - timedelta(days=8 + batch)
            end_date = start_date + timedelta(days=2)
            timeline["deposit_authorized_at"] = now - timedelta(days=7 + batch, hours=2)
            timeline["before_photos_uploaded_at"] = now - timedelta(days=7 + batch, hours=1)
            timeline["pickup_confirmed_at"] = now - timedelta(days=7 + batch)
            timeline["returned_by_renter_at"] = now - timedelta(days=5 + batch, hours=2)
            timeline["return_confirmed_at"] = timeline["returned_by_renter_at"] + timedelta(hours=2)
            timeline["after_photos_uploaded_at"] = timeline["return_confirmed_at"] + timedelta(
                hours=1
            )
            timeline["deposit_release_scheduled_at"] = self._deposit_release_at(end_date)
            timeline["deposit_released_at"] = timeline["deposit_release_scheduled_at"] + timedelta(
                hours=3
            )
            timeline["dispute_window_expires_at"] = timeline[
                "after_photos_uploaded_at"
            ] + timedelta(hours=24)
        elif scenario.key == "completed_recent":
            start_date = today - timedelta(days=2 + batch)
            end_date = today
            timeline["deposit_authorized_at"] = now - timedelta(days=1, hours=5)
            timeline["before_photos_uploaded_at"] = now - timedelta(days=2, hours=2)
            timeline["pickup_confirmed_at"] = now - timedelta(days=1, hours=2)
            timeline["returned_by_renter_at"] = now - timedelta(hours=3)
            timeline["return_confirmed_at"] = now - timedelta(hours=2)
            timeline["after_photos_uploaded_at"] = now - timedelta(hours=1)
            timeline["deposit_release_scheduled_at"] = self._deposit_release_at(end_date)
            timeline["dispute_window_expires_at"] = timeline[
                "after_photos_uploaded_at"
            ] + timedelta(hours=24)
        else:
            raise CommandError(f"Unknown scenario {scenario.key}")

        timeline["start_date"] = start_date
        timeline["end_date"] = end_date
        return timeline

    def _deposit_release_at(self, end_date):
        release_date = end_date + timedelta(days=1)
        return timezone.make_aware(
            datetime.combine(release_date, time.min),
            timezone.get_current_timezone(),
        )

    def _requires_verified(
        self,
        *,
        listing: Listing,
        start_date,
        end_date,
        max_days_unverified: int,
        max_repl,
        max_dep,
    ) -> bool:
        booking_days = (end_date - start_date).days
        replacement = listing.replacement_value_cad or 0
        deposit = listing.damage_deposit_cad or 0
        return booking_days > max_days_unverified or replacement > max_repl or deposit > max_dep

    def _select_listing(
        self,
        listings: list[Listing],
        listings_cycle: Iterable[Listing],
        start_date,
        end_date,
        *,
        needs_deposit: bool,
        active_state: bool,
    ) -> Listing:
        for _ in range(len(listings)):
            listing = next(listings_cycle)
            if needs_deposit and (listing.damage_deposit_cad or 0) <= 0:
                continue
            if active_state:
                conflict = Booking.objects.filter(
                    listing=listing,
                    status__in=[Booking.Status.CONFIRMED, Booking.Status.PAID],
                    start_date__lt=end_date,
                    end_date__gt=start_date,
                ).exists()
                if conflict:
                    continue
            return listing
        return listings[0]

    def _select_renter(
        self,
        renters: list[User],
        renters_cycle: Iterable[User],
        owner_id: int,
        *,
        requires_verified: bool,
        verified_user_ids: set[int],
    ) -> User:
        for _ in range(len(renters)):
            renter = next(renters_cycle)
            if renter.id == owner_id:
                continue
            if requires_verified and renter.id not in verified_user_ids:
                continue
            return renter
        for renter in renters:
            if renter.id != owner_id:
                return renter
        raise CommandError("No eligible renter found.")

    def _ensure_contact_verified(self, renter: User) -> None:
        updated_fields = []
        if not renter.email_verified:
            renter.email_verified = True
            updated_fields.append("email_verified")
        if not renter.phone_verified:
            renter.phone_verified = True
            updated_fields.append("phone_verified")
        if updated_fields:
            renter.save(update_fields=updated_fields)

    def _create_booking_photos(
        self,
        *,
        booking: Booking,
        uploaded_by: User,
        role: str,
        count: int,
    ) -> None:
        for index in range(1, count + 1):
            filename = f"{role}-{index}.jpg"
            BookingPhoto.objects.create(
                booking=booking,
                uploaded_by=uploaded_by,
                role=role,
                s3_key=f"uploads/bookings/{booking.id}/{filename}",
                url=f"https://example.com/media/bookings/{booking.id}/{filename}",
                filename=filename,
                content_type="image/jpeg",
                size=150000 + index * 12000,
                etag=f"seed-{booking.id}-{role}-{index}",
                status=BookingPhoto.Status.ACTIVE,
                av_status=BookingPhoto.AVStatus.CLEAN,
                width=1280,
                height=960,
            )
