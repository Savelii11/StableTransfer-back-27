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
from payments.models import Transfer
from payments.usdc_transfer import USDCTransfer


class ContractCreateView(APIView):
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):

        if request.user.is_checker:
            raise exceptions.PermissionDenied("Checkers are not allowed to create contracts.")
        data = request.data.copy()
        try:
            trans_hash = data.pop("transaction_hash", None)

            usdc_transfer = USDCTransfer()
            # Create the contract (without transaction_hash)
            tx_data = usdc_transfer.get_tx_data(trans_hash)
            transfer = usdc_transfer.get_transferred_usdc(tx_data)

            if usdc_transfer.is_receiver(tx_data, usdc_transfer.STABLE_TRANSFER_ADDRESS_SEPOLIA) and usdc_transfer.is_usdc_amount_correct(transfer, float(data["reward"])):
                serializer = ContractSerializer(data=data, context={"request": request})
            if serializer.is_valid():
                contract = serializer.save(contractor=request.user)  # Assign contractor automatically

                if trans_hash:
                    Transfer.objects.create(sender=request.user, contract=contract, tx_hash=trans_hash, status="Created")

                return Response(ContractSerializer(contract).data, status=status.HTTP_201_CREATED)
        except:
            response = {
                "message": "Hash is incorrect",
            }
            return Response(response, status=status.HTTP_400_BAD_REQUEST)


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


