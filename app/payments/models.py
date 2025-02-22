from content.models import Contract
from django.db import models
from user_auth.models import CustomUser


class Transfer(models.Model):
    TRANSFER_STATUSES = [
        ("Created", "Created"),
        ("Completed", "Completed"),
        ("Disputed", "Disputed"),
        ("Cancelled", "Cancelled"),
    ]
    sender = models.ForeignKey(
        CustomUser, null=False, blank=False, on_delete=models.CASCADE
    )
    receiver = models.ForeignKey(
        CustomUser, null=False, blank=False, on_delete=models.CASCADE
    )

    contract = models.OneToOneField(
        Contract, null=False, blank=False, on_delete=models.CASCADE
    )
    tx_hash = models.CharField(max_length=256, null=False, unique=True)
    status = models.CharField(
        choices=TRANSFER_STATUSES, max_length=256, blank=False, null=False
    )
    mediator = models.ForeignKey(
        CustomUser, null=True, blank=True, on_delete=models.CASCADE
    )
