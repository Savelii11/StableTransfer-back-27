from typing import Any, Dict

from django.contrib.auth import authenticate, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser
from .serializers import CustomUserSerializer, GetCustomUserSerializer


def generate_tokens_for_user(user: CustomUser) -> Dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    }


class CustomUserSignUpAPIView(APIView):

    def post(self, request: HttpRequest) -> HttpResponse:
        serializer = CustomUserSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginAPIView(APIView):

    def post(self, request: HttpRequest) -> HttpResponse:
        email = request.data["email"]
        password = request.data["password"]

        user = CustomUser.objects.filter(email=email).first()

        if user is None:
            raise exceptions.AuthenticationFailed("Invalid credentials")
        elif not user.check_password(password):
            raise exceptions.AuthenticationFailed("Invalid credentials")

        try:
            CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            raise exceptions.AuthenticationFailed(
                "You must complete your profile to log in."
            )

        user = authenticate(request, email=email, password=password)
        tokens = generate_tokens_for_user(user)

        user.is_active = True
        user.save()

        response = Response(
            tokens,
            status=status.HTTP_200_OK,
        )

        return response


class VerifyRefreshTokenAPIView(APIView):

    def post(self, request: HttpRequest) -> HttpResponse:
        refresh_token = request.data.get("refresh_token")

        if not refresh_token:
            return Response(
                {"message": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.verify()

            return Response(
                {"message": "Refresh token is valid."}, status=status.HTTP_200_OK
            )

        except TokenError:
            # Delete all expired refresh tokens
            now = timezone.now()
            OutstandingToken.objects.filter(expires_at__lte=now).delete()

            return Response(
                {"message": "Refresh token is invalid and has been revoked."},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class UserAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: HttpRequest, user_id: int) -> HttpResponse:
        custom_user = get_object_or_404(CustomUser, pk=user_id)

        return Response(
            GetCustomUserSerializer(custom_user).data, status=status.HTTP_200_OK
        )


class ProfileAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: HttpRequest) -> HttpResponse:
        custom_user = get_object_or_404(CustomUser, pk=request.user.id)
        return Response(
            GetCustomUserSerializer(custom_user).data, status=status.HTTP_200_OK
        )
