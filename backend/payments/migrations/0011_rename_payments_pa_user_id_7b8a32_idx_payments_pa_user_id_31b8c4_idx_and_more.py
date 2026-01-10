from django.db import migrations


class Migration(migrations.Migration):
    """
    No-op migration to satisfy index rename detection.

    The original auto-generated migration attempted to rename indexes that do not
    exist in some environments (e.g., after clean database creation). This placeholder
    allows the migration to apply safely without errors.
    """

    dependencies = [
        ("payments", "0010_ownerpayoutaccount_business_type"),
    ]

    operations: list[migrations.operations.base.Operation] = []
