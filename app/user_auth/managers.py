from typing import Any, Dict, Optional

from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    def create_user(
        self,
        email: str,
        fullname: str,
        wallet_address: str,
        is_checker: bool,
        password: Optional[str] = None,
        **extra_fields: Any
    ):
        if not email:
            raise ValueError(_("The Email must be set"))

        email = self.normalize_email(email)
        user = self.model(email=email, fullname=fullname, is_checker=is_checker,wallet_address=wallet_address, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    '''def create_superuser(
        self, email: str, password: Optional[str], **extra_fields: Any
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "Admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password=password, **extra_fields)'''
