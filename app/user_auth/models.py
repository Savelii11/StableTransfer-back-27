from django.db import models
from decimal import Decimal

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import CustomUserManager

# Create your models here.
class CustomUser(AbstractBaseUser, PermissionsMixin):
    fullname = models.CharField(max_length=30, blank=False, null=False, unique=True)
    email = models.EmailField(_("email address"), unique=True)
    wallet_address = models.CharField(unique=True, blank=False)
    is_checker = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)


    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["id","fullname", "wallet_address","is_checker"]

    objects = CustomUserManager()

    def str(self) -> str:
        return self.email

