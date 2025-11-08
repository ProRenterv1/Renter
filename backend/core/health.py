from django.http import JsonResponse
def healthz(_): return JsonResponse({"status":"ok"})