import os
import random
from typing import Any, Dict

import openai
from django.contrib.auth import authenticate, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from payments.models import Transfer
from payments.usdc_transfer import USDCTransfer
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Contract, CustomUser
from .serializers import ContractSerializer, GetContractSerializer, PutAttachmentProofSerializer, GetMediatorsContractSerializer, GetFullContractSerializer

usdc_transfer = USDCTransfer()


class ContractCreateView(APIView):
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request: HttpRequest) -> HttpResponse:

        if request.user.is_checker:
            raise exceptions.PermissionDenied(
                "Checkers are not allowed to create contracts."
            )

        data = request.data.copy()
        trans_hash = data.pop("transaction_hash", None)

        # Create the contract (without transaction_hash)
        tx_data = usdc_transfer.get_tx_data(trans_hash)

        if not tx_data:
            return Response(
                {"message": "Tx hash is invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transfer = usdc_transfer.get_transferred_usdc(tx_data)

        if (
            usdc_transfer.is_receiver(
                tx_data, usdc_transfer.STABLE_TRANSFER_ADDRESS_SEPOLIA
            )
            and usdc_transfer.is_sender(tx_data, request.user.wallet_address)
            and usdc_transfer.is_usdc_amount_correct(transfer, float(data["reward"]))
        ):
            serializer = ContractSerializer(data=data, context={"request": request})
            if serializer.is_valid():
                contract = serializer.save(
                    contractor=request.user
                )  # Assign contractor automatically

                Transfer.objects.create(
                    sender=request.user,
                    contract=contract,
                    tx_hash=trans_hash,
                    status="Created",
                )

                return Response(
                    ContractSerializer(contract).data, status=status.HTTP_201_CREATED
                )

            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        else:
            response = {
                "message": "Transaction is invalid",
            }
            return Response(response, status=status.HTTP_400_BAD_REQUEST)


class AcceptContractAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request: HttpRequest, contract_id: int) -> HttpResponse:
        user = request.user

        if user.is_checker == True:
            return Response(
                {"error": "Mediator isn't allowed to accept contract."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        # Get the associated transfer object (handle case where no transfer exists)
        transfer = getattr(contract, "contract", None)

        if transfer is None:
            return Response(
                {"error": "No Transfer associated with this contract."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Update the transfer receiver
        transfer.receiver = user
        transfer.save()

        response_data = {"message": "Contract successfully accepted."}
        return Response(response_data, status=status.HTTP_200_OK)


class ContractRaiseDispute(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request: HttpRequest, contract_id: int) -> Response:
        user = request.user

        # Retrieve the contract
        contract = get_object_or_404(Contract, id=contract_id)

        # Ensure the contract has a contractee
        if not contract.contractee:
            return Response(
                {"error": "The contract doesn't have a contractee."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Ensure that only the contractor can raise a dispute
        if contract.contractor != user:
            return Response(
                {"error": "Only the contractor can raise a dispute."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Retrieve the transfer associated with the contract
        transfer = getattr(contract, "contract", None)

        if transfer is None:
            return Response(
                {"error": "No Transfer associated with this contract."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get a list of available mediators (users with is_checker=True)
        potential_mediators = CustomUser.objects.filter(is_checker=True)

        if not potential_mediators.exists():
            return Response(
                {"error": "No available mediators."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Randomly select a mediator
        # mediator = random.choice(list(potential_mediators))
        mediator = self.get_best_mediator(contract.description, potential_mediators)

        # Assign the mediator to both the contract and transfer
        contract.mediator = mediator
        contract.save()

        transfer.mediator = mediator
        transfer.status = "Disputed"
        transfer.save()

        response_data: Dict[str, Any] = {
            "message": "Dispute raised successfully.",
            "transfer_status": transfer.status,
        }
        return Response(response_data, status=status.HTTP_200_OK)

    def get_best_mediator(self, contract_description, mediators):
        """
        Use OpenAI to match the contract description with the most relevant mediator.
        """
        openai.api_key = os.environ.get(
            "OPENAI_API_KEY"
        )  # Ensure this is set in Django settings

        # Prepare mediator descriptions for comparison
        mediator_profiles = [
            f"Mediator {mediator.id}: {mediator.description}"
            for mediator in mediators
            if hasattr(mediator, "description") and mediator.description
        ]

        if not mediator_profiles:
            return random.choice(
                mediators
            )  # If no descriptions are available, fallback to random selection


        mediator_profiles_str = "\n".join(mediator_profiles)  # Create a string first

        prompt = f"""
            Given the following contract description, select the best mediator from the list below.

            Contract Description: {contract_description}

            Mediator Profiles:
            {mediator_profiles_str}

            Choose the best mediator by returning ONLY their ID.
            """

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=10,
            )

            mediator_id = int(response["choices"][0]["message"]["content"].strip())
            return mediators.get(id=mediator_id)

        except Exception as e:
            print(f"OpenAI Error: {e}")
            return random.choice(mediators)


class ProcessContractDispute(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request: HttpRequest, transfer_id: int) -> HttpResponse:
        user = request.user
        is_dispute_approved = request.data.get("is_disputed_contract")
        transfer = get_object_or_404(Transfer, id=transfer_id)

        if transfer.mediator != user:
            return Response(
                {"error": "You are not the assigned mediator for this dispute."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if transfer.status != "Disputed":
            return Response(
                {"error": "Transfer is not in disputed status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if is_dispute_approved:
            # TODO
            # money goes back to sender from out address
            transfer.status = "Cancelled"

        else:
            # TODO
            # money goes to contra from out address
            transfer.status = "Completed"


class GetContractsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: HttpRequest) -> HttpResponse:
        contracts = Contract.objects.all()
        serializer = GetContractSerializer(contracts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GetSpecificContractAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: HttpRequest, contract_id: int) -> Response:
        user = request.user
        if user.is_checker==True:
            return Response({"error": f"Only the ordinary users can see Contract's details"},
                            status=status.HTTP_403_FORBIDDEN, )

        contract = get_object_or_404(Contract, id=contract_id)
        if user==contract.contractee or user==contract.contractor:
            serializer = GetFullContractSerializer(contract)
        else:
            serializer = GetContractSerializer(contract)
        return Response(serializer.data, status=status.HTTP_200_OK)

class AttachProofAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request: HttpRequest, contract_id: int) ->Response:
        contract = get_object_or_404(Contract, id=contract_id)
        user = request.user
        if contract.contractee!=user:
            return Response({"error": f"Only the contractee can attach proof.Current user: {user.fullname}"},
                status=status.HTTP_403_FORBIDDEN,)

        serializer = PutAttachmentProofSerializer(contract, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetMediatorContractsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: HttpRequest) -> Response:
        user = request.user
        if user.is_checker==False:
            return Response({"error":"Only the mediators can request this information"}, status=status.HTTP_403_FORBIDDEN,)

        all_contracts = Contract.objects.filter(mediator=user)
        serializer = GetMediatorsContractSerializer(all_contracts, many = True)

        return Response(serializer.data, status=status.HTTP_200_OK)






