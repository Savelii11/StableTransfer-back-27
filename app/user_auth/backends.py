from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest

UserModel = get_user_model()


class CustomAuthBackend(ModelBackend):
    def authenticate(
        self,
        request: Optional[HttpRequest],
        email: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: Any
    ):
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(email=email)
        except UserModel.DoesNotExist:
            return None

        if user.check_password(password):
            return user

        return None

    def get_user(self, user_id: Any) -> Optional[UserModel]:
        try:
            return get_user_model().objects.get(pk=user_id)

        except ObjectDoesNotExist:
            return None
