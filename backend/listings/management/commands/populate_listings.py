from __future__ import annotations

from decimal import Decimal
from itertools import cycle

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from listings.models import Category, Listing, ListingPhoto

User = get_user_model()

CATEGORY_SEEDS = [
    {
        "name": "Power Tools",
        "icon": "Drill",
        "accent": "bg-amber-100",
        "icon_color": "text-amber-700",
    },
    {
        "name": "Outdoor",
        "icon": "TreePine",
        "accent": "bg-emerald-100",
        "icon_color": "text-emerald-700",
    },
    {
        "name": "Events",
        "icon": "PartyPopper",
        "accent": "bg-orange-100",
        "icon_color": "text-orange-700",
    },
    {
        "name": "Audio & Video",
        "icon": "Speaker",
        "accent": "bg-sky-100",
        "icon_color": "text-sky-700",
    },
    {
        "name": "Home Projects",
        "icon": "Hammer",
        "accent": "bg-stone-100",
        "icon_color": "text-stone-700",
    },
    {
        "name": "Sports & Travel",
        "icon": "Backpack",
        "accent": "bg-teal-100",
        "icon_color": "text-teal-700",
    },
]

LISTING_SEEDS = [
    {
        "title": "Cordless Drill Kit",
        "description": "18V drill with two batteries, charger, and bit set. Cleaned and tested.",
        "daily_price_cad": Decimal("18.00"),
        "replacement_value_cad": Decimal("220.00"),
        "damage_deposit_cad": Decimal("50.00"),
        "city": "Edmonton",
        "postal_code": "T5J 1N2",
    },
    {
        "title": "Pressure Washer 2000 PSI",
        "description": "Compact electric washer with 3 nozzles and hose. Great for patios.",
        "daily_price_cad": Decimal("35.00"),
        "replacement_value_cad": Decimal("450.00"),
        "damage_deposit_cad": Decimal("80.00"),
        "city": "Calgary",
        "postal_code": "T2P 1J9",
    },
    {
        "title": "Projector + Screen Bundle",
        "description": "1080p projector with 100in screen and HDMI cable. Easy setup.",
        "daily_price_cad": Decimal("45.00"),
        "replacement_value_cad": Decimal("650.00"),
        "damage_deposit_cad": Decimal("120.00"),
        "city": "Vancouver",
        "postal_code": "V6B 1A1",
    },
    {
        "title": "Party Speaker Pair",
        "description": "Two powered speakers with stands and Bluetooth. Includes cables.",
        "daily_price_cad": Decimal("28.00"),
        "replacement_value_cad": Decimal("380.00"),
        "damage_deposit_cad": Decimal("75.00"),
        "city": "Toronto",
        "postal_code": "M5V 2T6",
    },
    {
        "title": "DSLR Camera Starter Kit",
        "description": "Entry DSLR with 18-55mm lens, bag, and extra battery.",
        "daily_price_cad": Decimal("55.00"),
        "replacement_value_cad": Decimal("900.00"),
        "damage_deposit_cad": Decimal("180.00"),
        "city": "Ottawa",
        "postal_code": "K1P 1J1",
    },
    {
        "title": "GoPro Adventure Pack",
        "description": "Action camera with chest mount, helmet mount, and case.",
        "daily_price_cad": Decimal("22.00"),
        "replacement_value_cad": Decimal("420.00"),
        "damage_deposit_cad": Decimal("90.00"),
        "city": "Winnipeg",
        "postal_code": "R3C 4T3",
    },
    {
        "title": "Lawn Mower 21in",
        "description": "Gas mower with mulching blade. Freshly serviced.",
        "daily_price_cad": Decimal("30.00"),
        "replacement_value_cad": Decimal("320.00"),
        "damage_deposit_cad": Decimal("70.00"),
        "city": "Edmonton",
        "postal_code": "T6G 2R3",
    },
    {
        "title": "Snow Blower 24in",
        "description": "Two-stage blower with electric start and chute control.",
        "daily_price_cad": Decimal("40.00"),
        "replacement_value_cad": Decimal("700.00"),
        "damage_deposit_cad": Decimal("150.00"),
        "city": "Calgary",
        "postal_code": "T3A 0A1",
    },
    {
        "title": "Electric Bike Rack",
        "description": "Hitch-mounted rack for two bikes. Includes hitch pin.",
        "daily_price_cad": Decimal("25.00"),
        "replacement_value_cad": Decimal("300.00"),
        "damage_deposit_cad": Decimal("60.00"),
        "city": "Halifax",
        "postal_code": "B3H 1G1",
    },
    {
        "title": "Compact Air Compressor",
        "description": "Oil-free compressor with 25ft hose and tire inflator.",
        "daily_price_cad": Decimal("26.00"),
        "replacement_value_cad": Decimal("350.00"),
        "damage_deposit_cad": Decimal("80.00"),
        "city": "Victoria",
        "postal_code": "V8W 1N6",
    },
    {
        "title": "Laser Level Kit",
        "description": "Self-leveling cross-line laser with tripod and case.",
        "daily_price_cad": Decimal("19.00"),
        "replacement_value_cad": Decimal("260.00"),
        "damage_deposit_cad": Decimal("55.00"),
        "city": "Saskatoon",
        "postal_code": "S7K 1J5",
    },
    {
        "title": "Tile Cutter Wet Saw",
        "description": "7in wet saw with fence guide. Perfect for backsplash jobs.",
        "daily_price_cad": Decimal("38.00"),
        "replacement_value_cad": Decimal("520.00"),
        "damage_deposit_cad": Decimal("120.00"),
        "city": "Regina",
        "postal_code": "S4P 3Y2",
    },
    {
        "title": "Paint Sprayer Pro",
        "description": "Airless sprayer with tips and cleaning kit.",
        "daily_price_cad": Decimal("27.00"),
        "replacement_value_cad": Decimal("430.00"),
        "damage_deposit_cad": Decimal("90.00"),
        "city": "Kelowna",
        "postal_code": "V1Y 1N5",
    },
    {
        "title": "Kayak Single",
        "description": "Lightweight kayak with paddle and life jacket.",
        "daily_price_cad": Decimal("32.00"),
        "replacement_value_cad": Decimal("600.00"),
        "damage_deposit_cad": Decimal("130.00"),
        "city": "Vancouver",
        "postal_code": "V6C 2G8",
    },
    {
        "title": "Roof Ladder 20ft",
        "description": "Aluminum ladder with stabilizer bar. Rated for 300 lbs.",
        "daily_price_cad": Decimal("16.00"),
        "replacement_value_cad": Decimal("200.00"),
        "damage_deposit_cad": Decimal("40.00"),
        "city": "Edmonton",
        "postal_code": "T5K 0A1",
    },
    {
        "title": "Carpet Cleaner Upright",
        "description": "Deep clean carpet machine with upholstery tool.",
        "daily_price_cad": Decimal("24.00"),
        "replacement_value_cad": Decimal("280.00"),
        "damage_deposit_cad": Decimal("60.00"),
        "city": "Montreal",
        "postal_code": "H3B 2Y5",
    },
    {
        "title": "Chainsaw 18in",
        "description": "Gas chainsaw with fresh chain and safety chaps.",
        "daily_price_cad": Decimal("29.00"),
        "replacement_value_cad": Decimal("420.00"),
        "damage_deposit_cad": Decimal("95.00"),
        "city": "Calgary",
        "postal_code": "T2S 2G2",
    },
    {
        "title": "Concrete Mixer Portable",
        "description": "Portable mixer with 3.5 cu ft drum. Easy to tow.",
        "daily_price_cad": Decimal("60.00"),
        "replacement_value_cad": Decimal("950.00"),
        "damage_deposit_cad": Decimal("200.00"),
        "city": "Toronto",
        "postal_code": "M4W 1A8",
    },
    {
        "title": "3D Printer Starter",
        "description": "FDM printer with 0.4mm nozzle and starter filament.",
        "daily_price_cad": Decimal("48.00"),
        "replacement_value_cad": Decimal("800.00"),
        "damage_deposit_cad": Decimal("160.00"),
        "city": "Ottawa",
        "postal_code": "K2P 1L4",
    },
    {
        "title": "Event Tent 10x20",
        "description": "Pop-up tent with sidewalls and sandbags.",
        "daily_price_cad": Decimal("52.00"),
        "replacement_value_cad": Decimal("700.00"),
        "damage_deposit_cad": Decimal("140.00"),
        "city": "Edmonton",
        "postal_code": "T5P 2L8",
    },
]


class Command(BaseCommand):
    help = "Populate listings for existing users with complete listing details."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Number of listings to create.",
        )
        parser.add_argument(
            "--photos-per-listing",
            type=int,
            default=2,
            help="Number of photos to create per listing.",
        )

    def handle(self, *args, **options) -> None:
        count = options["count"]
        photos_per_listing = options["photos_per_listing"]

        if count <= 0:
            raise CommandError("--count must be greater than 0.")
        if photos_per_listing < 0:
            raise CommandError("--photos-per-listing must be 0 or higher.")

        owners = list(User.objects.filter(can_list=True).order_by("id"))
        if not owners:
            owners = list(User.objects.order_by("id"))
        if not owners:
            raise CommandError("No users found. Create users before adding listings.")

        categories = self._ensure_categories()

        with transaction.atomic():
            created = self._create_listings(
                count=count,
                owners=owners,
                categories=categories,
                photos_per_listing=photos_per_listing,
            )

        self.stdout.write(self.style.SUCCESS("Listing population complete."))
        self.stdout.write(f"Listings created: {created}")

    def _ensure_categories(self) -> list[Category]:
        categories: list[Category] = []
        for seed in CATEGORY_SEEDS:
            category, created = Category.objects.get_or_create(
                name=seed["name"],
                defaults={
                    "icon": seed["icon"],
                    "accent": seed["accent"],
                    "icon_color": seed["icon_color"],
                },
            )
            if not created:
                updates = {}
                if not category.icon and seed.get("icon"):
                    updates["icon"] = seed["icon"]
                if not category.accent and seed.get("accent"):
                    updates["accent"] = seed["accent"]
                if not category.icon_color and seed.get("icon_color"):
                    updates["icon_color"] = seed["icon_color"]
                if updates:
                    for field, value in updates.items():
                        setattr(category, field, value)
                    category.save(update_fields=list(updates.keys()))
            categories.append(category)
        return categories

    def _create_listings(
        self,
        *,
        count: int,
        owners: list[User],
        categories: list[Category],
        photos_per_listing: int,
    ) -> int:
        owners_cycle = cycle(owners)
        categories_cycle = cycle(categories)
        created = 0

        for index in range(count):
            seed = LISTING_SEEDS[index % len(LISTING_SEEDS)]
            owner = next(owners_cycle)
            category = next(categories_cycle)
            is_available = index % 5 != 0

            listing = Listing.objects.create(
                owner=owner,
                title=seed["title"],
                description=seed["description"],
                category=category,
                daily_price_cad=seed["daily_price_cad"],
                replacement_value_cad=seed["replacement_value_cad"],
                damage_deposit_cad=seed["damage_deposit_cad"],
                is_available=is_available,
                city=seed["city"],
                postal_code=seed["postal_code"],
                is_active=True,
                is_deleted=False,
            )

            if photos_per_listing:
                self._create_photos(listing, photos_per_listing)

            created += 1

        return created

    def _create_photos(self, listing: Listing, count: int) -> None:
        for index in range(1, count + 1):
            filename = f"photo-{index}.jpg"
            ListingPhoto.objects.create(
                listing=listing,
                owner=listing.owner,
                key=f"uploads/listings/{listing.id}/{filename}",
                url=f"https://example.com/media/listings/{listing.slug}/{filename}",
                filename=filename,
                content_type="image/jpeg",
                size=180000 + index * 12000,
                etag=f"seed-{listing.id}-{index}",
                status=ListingPhoto.Status.ACTIVE,
                av_status=ListingPhoto.AVStatus.CLEAN,
                width=1200,
                height=800,
            )
