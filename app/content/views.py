from typing import Any, Dict

from django.contrib.auth import authenticate, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from payments.models import Transfer
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Contract, CustomUser
from .serializers import ContractSerializer


class ContractCreateView(APIView):
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Create a contract, ensuring only non-checkers can create."""
        if request.user.is_checker:
            raise exceptions.PermissionDenied(
                "Checkers are not allowed to create contracts."
            )

        serializer = ContractSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            contract = serializer.save(
                contractor=request.user
            )  # Assign contractor automatically
            return Response(
                ContractSerializer(contract).data, status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AcceptContractAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request: HttpRequest, contract_id: int) -> HttpResponse:
        user = request.user

        # Get the contract
        contract = get_object_or_404(Contract, id=contract_id)

        # Ensure that the contractee is not already set
        if contract.contractee is not None:
            return Response(
                {"error": "This contract has already been accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if contract.contractor == user:
            return Response(
                {"error": "This user is contractor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Assign the authenticated user as the contractee
        contract.contractee = user
        contract.save()

        try:
            transfer = contract.transfer
            transfer.receiver = user
            transfer.save()
        except Transfer.DoesNotExist:
            return Response(
                {"error": "No Transfer associated with this contract."},
                status=status.HTTP_404_NOT_FOUND,
            )

        response_data = {"message": "Contract successfully accepted."}
        return Response(response_data, status=status.HTTP_200_OK)
