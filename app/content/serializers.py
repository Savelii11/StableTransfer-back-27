from typing import Any, Dict

from rest_framework import serializers

from .models import Contract


class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = ["id", "title", "reward", "description", "contractor", "contractee", "mediator", "completed"]
        read_only_fields = ["contractor"]  # Prevent users from setting the contractor manually

    def create(self, validated_data):
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            validated_data["contractor"] = (
                request.user
            )  # Assign contractor automatically

        return super().create(validated_data)


class GetContractSerializer(serializers.ModelSerializer):
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
            "transaction_hash",
        ]
