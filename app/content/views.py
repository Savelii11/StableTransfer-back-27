import os
import random
from typing import Any, Dict

import openai
from django.contrib.auth import authenticate, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from payments.models import Transfer
from payments.usdc_transfer import USDCManager
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Contract, CustomUser
from .permissions import IsContractorOrRead
from .serializers import (
    CompleteContractSerializer,
    ContractSerializer,
    GetContractSerializer,
    GetFullContractSerializer,
    GetMediatorsContractSerializer,
    PutAttachmentProofSerializer,
)

usdc_manager = USDCManager()


class ContractCreateView(APIView):
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request: HttpRequest) -> HttpResponse:

        # Ensure checkers are not creating contracts
        if request.user.is_checker:
            raise exceptions.PermissionDenied(
                "Checkers are not allowed to create contracts."
            )

        # Extract transaction hash
        data = request.data.copy()
        trans_hash = data.pop("transaction_hash", None)

        if not trans_hash:
            return Response(
                {"message": "Transaction hash is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Retrieve transaction data from Etherscan/Alchemy
        tx_data = usdc_manager.get_tx_data(trans_hash)

        if not tx_data:
            return Response(
                {"message": "Invalid transaction hash or transaction not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Extract all USDC transfers from the transaction
        transfers = usdc_manager.get_transferred_usdc(tx_data)

        if not transfers:
            return Response(
                {"message": "No valid USDC transfers found in the transaction."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if the user is the sender and the contract address is the receiver
        is_valid_transfer = all(
            usdc_manager.is_receiver(
                transfer, usdc_manager.STABLE_TRANSFER_ADDRESS_SEPOLIA
            )
            and usdc_manager.is_sender(transfer, request.user.wallet_address)
            and usdc_manager.is_usdc_amount_correct(
                transfer, float(data.get("reward", 0))
            )
            for transfer in transfers
        )

        if not is_valid_transfer:
            return Response(
                {"message": "Transaction validation failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create contract if the transaction is valid
        serializer = ContractSerializer(data=data, context={"request": request})
        if serializer.is_valid():
            contract = serializer.save(contractor=request.user)

            # Create Transfer entry for the contract
            Transfer.objects.create(
                sender=request.user,
                contract=contract,
                tx_hash=trans_hash,
                status="Created",
            )

            return Response(
                ContractSerializer(contract).data, status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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


class ProcessContractDisputeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request: HttpRequest, transfer_id: int) -> HttpResponse:
        user = request.user
        is_dispute_approved = request.data.get("is_disputed_contract")
        transfer = get_object_or_404(Transfer, id=transfer_id)

        contract_curr = transfer.contract

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

        try:
            # Send 99% of the reward to either the sender (if dispute is approved)
            # or contractor (if dispute is rejected)
            recipient = (
                transfer.sender.wallet_address
                if is_dispute_approved
                else transfer.receiver.wallet_address
            )
            new_tx_hash = usdc_manager.send_usdc(recipient, transfer.id, 99.0)

            # Send 1% of the reward to the mediator
            mediator_tx_hash = usdc_manager.send_usdc(
                transfer.mediator.wallet_address, transfer.id, 1.0
            )

            print(f"Transaction sent! TX Hash: {new_tx_hash}")
            print(f"Mediator Paid! TX Hash: {mediator_tx_hash}")

            transfer.tx_hash = new_tx_hash
            transfer.status = "Cancelled" if is_dispute_approved else "Completed"
            transfer.save()
            if transfer.status == "Completed":
                contract_curr.completed = True
                contract_curr.save()

            return Response(
                {
                    "message": "Dispute processed successfully.",
                    "transaction_hash": new_tx_hash,
                    "mediator_transaction_hash": mediator_tx_hash,
                    "new_status": transfer.status,
                },
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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
        if user.is_checker == True:
            return Response(
                {"error": f"Only the ordinary users can see Contract's details"},
                status=status.HTTP_403_FORBIDDEN,
            )

        contract = get_object_or_404(Contract, id=contract_id)
        if user == contract.contractee or user == contract.contractor:
            serializer = GetFullContractSerializer(contract)
        else:
            serializer = GetContractSerializer(contract)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AttachProofAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request: HttpRequest, contract_id: int) -> Response:
        contract = get_object_or_404(Contract, id=contract_id)
        user = request.user
        if contract.contractee != user:
            return Response(
                {
                    "error": f"Only the contractee can attach proof.Current user: {user.fullname}"
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PutAttachmentProofSerializer(
            contract, data=request.data, partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetMediatorContractsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: HttpRequest) -> Response:
        user = request.user
        if user.is_checker == False:
            return Response(
                {"error": "Only the mediators can request this information"},
                status=status.HTTP_403_FORBIDDEN,
            )

        all_contracts = Contract.objects.filter(mediator=user)
        serializer = GetMediatorsContractSerializer(all_contracts, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)


class ContractCompleteAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsContractorOrRead]

    def put(self, request: HttpRequest, contract_id) -> Response:
        curr_contr = get_object_or_404(Contract, id=contract_id)
        self.check_object_permissions(request, curr_contr)

        if curr_contr.contractee is None:
            return Response(
                {
                    "error": "Can't complete the contract when the contractee is not assigned, need to cancel instead"
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CompleteContractSerializer(
            curr_contr, data={"completed": True}, partial=True
        )

        if serializer.is_valid():
            # Mark the contract as complete
            serializer.save()

            # Retrieve the Transfer associated with this Contract (OneToOne relation)
            transfer = curr_contr.contract

            # try:
            #     # Send 100% of the reward to the contractee
            #     tx_hash = usdc_manager.send_usdc(
            #         curr_contr.contractee.wallet_address, transfer.id, 100.0
            #     )
            # except Exception as e:
            #     return Response(
            #         {"error": f"Payment failed: {str(e)}"},
            #         status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            #     )

            # Update the Transfer with the transaction hash and new status
            # transfer.tx_hash = tx_hash
            transfer.status = "Completed"
            transfer.save()

            return Response(
                {
                    "message": "Contract completed and payment sent successfully.",
                    "contract": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ContractDeleteAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsContractorOrRead]

    def delete(self, request: HttpRequest, contract_id) -> Response:
        contract = get_object_or_404(Contract, id=contract_id)
        self.check_object_permissions(request, contract)

        if contract.contractee:
            return Response(
                {"error": "Can't cancel the contract when the contractee is assigned"},
                status=status.HTTP_403_FORBIDDEN,
            )

        contract.delete()

        res = {
            "status": status.HTTP_200_OK,
            "message": f"Your contract with ID {contract_id} has been deleted.",
        }
        return Response(res, status=status.HTTP_200_OK)
