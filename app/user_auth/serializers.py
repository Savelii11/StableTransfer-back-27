from rest_framework import serializers
from .models import CustomUser
from typing import Any, Dict

def validate_password(value: str) -> str:
    if len(value) < 8:
        raise serializers.ValidationError(
            "The password must be at least 8 characters long"
        )
    return value



class CustomUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def create(self, validated_data: Dict[str, Any]) -> CustomUser:
        password = validated_data.pop("password", None)
        instance = self.Meta.model(**validated_data)
        if password is not None:
            instance.set_password(password)
        instance.save()
        return instance

    class Meta:
        model = CustomUser
        fields = ["id", "fullname", "email", "wallet_address", "password", "is_checker", "description"]
        extra_kwargs = {"password": {"write_only": True}}

class LoginSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ["email", "password"]

class GetCustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["fullname","wallet_address", "email", "description"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # If user is a checker, remove email and phone_number
        if instance.is_checker:
            representation.pop("email", None)
            representation.pop("fullname", None)


        return representation