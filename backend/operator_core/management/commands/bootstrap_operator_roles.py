from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

OPERATOR_GROUPS = [
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
]


class Command(BaseCommand):
    help = "Create operator role groups and optionally assign operator_admin to a user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--assign-email",
            dest="assign_email",
            help="Email of the user to assign to operator_admin.",
        )
        parser.add_argument(
            "--assign-username",
            dest="assign_username",
            help="Username of the user to assign to operator_admin.",
        )

    def handle(self, *args, **options):
        created = []
        for group_name in OPERATOR_GROUPS:
            group, was_created = Group.objects.get_or_create(name=group_name)
            if was_created:
                created.append(group_name)

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created groups: {', '.join(created)}"))
        else:
            self.stdout.write("Operator groups already exist.")

        assign_email = options.get("assign_email")
        assign_username = options.get("assign_username")

        if assign_email and assign_username:
            raise CommandError("Provide only one of --assign-email or --assign-username.")

        if assign_email or assign_username:
            user = self._get_user(assign_email, assign_username)
            user.is_staff = True
            user.save(update_fields=["is_staff"])

            admin_group = Group.objects.get(name="operator_admin")
            user.groups.add(admin_group)
            self.stdout.write(
                self.style.SUCCESS(f"Assigned {user} to operator_admin and set is_staff=True.")
            )

    def _get_user(self, email, username):
        User = get_user_model()

        try:
            if email:
                return User.objects.get(email=email)
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError("User not found for the provided identifier.")
