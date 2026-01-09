from django.http import JsonResponse

from core.feature_flags import get_maintenance_banner


def maintenance_status(_request):
    """
    Public endpoint to surface maintenance banner details to the frontend.
    Always returns a banner payload, defaulting to disabled if none is set.
    """

    banner = get_maintenance_banner()
    return JsonResponse(banner)
