from typing import Iterable, Sequence

from rest_framework.permissions import BasePermission


class IsOperator(BasePermission):
    """
    Allows access only to authenticated staff users.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)


class HasOperatorRole(BasePermission):
    """
    Allows access to staff users in any of the required roles (groups).
    """

    required_roles: Sequence[str] = ()

    def __init__(self, roles: Iterable[str] | None = None):
        if roles is not None:
            self.required_roles = tuple(roles)

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and user.is_staff):
            return False

        if not self.required_roles:
            return False

        return user.groups.filter(name__in=self.required_roles).exists()

    @classmethod
    def with_roles(cls, roles: Iterable[str]):
        """
        Helper to build a permission class with baked-in required roles.
        """

        role_tuple = tuple(roles)

        class _HasOperatorRole(cls):
            required_roles = role_tuple

        _HasOperatorRole.__name__ = f"{cls.__name__}WithRoles"
        return _HasOperatorRole
