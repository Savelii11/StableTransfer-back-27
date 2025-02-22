from django.shortcuts import render

# Create your views here.
from django.shortcuts import render
from typing import Any, Dict
from .models import CustomUser
from django.contrib.auth import authenticate, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Contract
from .serializers import ContractSerializer


class ContractCreateView(APIView):
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Create a contract, ensuring only non-checkers can create."""
        if request.user.is_checker:
            raise exceptions.PermissionDenied("Checkers are not allowed to create contracts.")

        serializer = ContractSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            contract = serializer.save(contractor=request.user)  # Assign contractor automatically
            return Response(ContractSerializer(contract).data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)