from decimal import Decimal

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from user_auth.models import CustomUser

# Create your models here.


class Contract(models.Model):
    title = models.CharField(max_length=30, blank=False, null=False)
    reward = models.FloatField(blank=False, null=False)
    description = models.TextField(blank=False, null=False)
    contractor = models.ForeignKey(
        CustomUser,
        related_name="contractor",
        blank=False,
        on_delete=models.SET_NULL,
        null=True,
    )
    contractee = models.ForeignKey(
        CustomUser,
        related_name="contractee",
        blank=True,
        on_delete=models.SET_NULL,
        null=True,
    )
    mediator = models.ForeignKey(
        CustomUser,
        related_name="mediator",
        blank=True,
        on_delete=models.SET_NULL,
        null=True,
    )
    completed = models.BooleanField(default=False)
