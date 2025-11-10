from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):

    can_rent = models.BooleanField(default=True)
    can_list = models.BooleanField(default=True)

    def is_owner(self) -> bool:
        return bool(self.can_list)

    def is_renter(self) -> bool:
        return bool(self.can_rent)
