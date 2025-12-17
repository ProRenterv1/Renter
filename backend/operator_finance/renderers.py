from rest_framework.renderers import BaseRenderer


class CSVRenderer(BaseRenderer):
    """
    Minimal renderer to satisfy DRF content negotiation for CSV endpoints.

    The export views return a Django HttpResponse directly, but DRF still runs
    Accept header negotiation before executing the handler.
    """

    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b""
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        return str(data).encode(self.charset)
