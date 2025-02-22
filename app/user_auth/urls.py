from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("register/", views.CustomUserSignUpAPIView.as_view(), name="register"),
    path("login/", views.LoginAPIView.as_view(), name="login"),
    path("v1/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path(
        "v1/token/verify/",
        views.VerifyRefreshTokenAPIView.as_view(),
        name="token-verify",
    ),
    path("get_user/<int:user_id>/", views.UserAPIView.as_view(), name="get-user"),
]
