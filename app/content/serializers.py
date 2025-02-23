from typing import Any, Dict

from rest_framework import serializers
from user_auth.serializers import CustomUserSerializer

from .models import Contract


class ContractSerializer(serializers.ModelSerializer):
    contractor = CustomUserSerializer(read_only=True)
    contractee = CustomUserSerializer(read_only=True)
    mediator = CustomUserSerializer(read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id",
            "title",
            "reward",
            "description",
            "contractor",
            "contractee",
            "mediator",
            "completed",
        ]
        read_only_fields = ["contractor"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            validated_data["contractor"] = (
                request.user
            )  # Assign contractor automatically

        return super().create(validated_data)


class GetContractSerializer(serializers.ModelSerializer):
    contractor = CustomUserSerializer(read_only=True)
    contractee = CustomUserSerializer(read_only=True)
    mediator = CustomUserSerializer(read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id",
            "title",
            "reward",
            "description",
            "contractor",
            "contractee",
            "mediator",
            "completed",
        ]
