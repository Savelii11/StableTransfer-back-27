from typing import Any

from user_auth.models import CustomUser
from django.http import HttpRequest
from rest_framework import permissions
from rest_framework.views import APIView

class IsContractorOrRead(permissions.BasePermission):
    def has_object_permission(
            self, request: HttpRequest, view: APIView, obj: Any
    ) -> bool:
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return True
        # Write permissions are only allowed to the owner of the profile.
        return obj.contractor == request.user