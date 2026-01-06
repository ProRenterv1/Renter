from django.conf import settings
from django.http import HttpResponseNotFound


class OpsOnlyRouteGatingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Lowercase allowed hosts for quick comparison
        self.allowed_hosts = {host.lower() for host in getattr(settings, "OPS_ALLOWED_HOSTS", [])}

    def __call__(self, request):
        path = request.path or ""

        if path.startswith("/admin/"):
            if not getattr(settings, "ENABLE_DJANGO_ADMIN", False):
                return HttpResponseNotFound()
            if not self._is_ops_host(request):
                return HttpResponseNotFound()
        elif path.startswith("/api/operator/"):
            if not getattr(settings, "ENABLE_OPERATOR", False):
                return HttpResponseNotFound()
            if not self._is_ops_host(request):
                return HttpResponseNotFound()

        return self.get_response(request)

    def _is_ops_host(self, request):
        host = request.get_host() or ""
        hostname = host.split(":", 1)[0].lower()
        return hostname in self.allowed_hosts
