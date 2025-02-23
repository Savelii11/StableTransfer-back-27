import json
import os
import time
from decimal import Decimal
from typing import Dict, List

import requests
from django.core.exceptions import ObjectDoesNotExist
from payments.models import Transfer
from web3 import Web3
from web3.contract import Contract


class USDCManager:
    # ERC‑20 Transfer event signature hash (first topic) starts with this prefix
    TRANSFER_TOPIC_PREFIX = os.environ.get("TRANSFER_TOPIC_PREFIX")
    ALCHEMY_RPC_URL = os.environ.get("ALCHEMY_RPC_URL")

    PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
    USDC_CONTRACT_ADDRESS_SEPOLIA = os.environ.get("USDC_CONTRACT_ADDRESS_SEPOLIA")
    STABLE_TRANSFER_ADDRESS_SEPOLIA = os.environ.get("STABLE_TRANSFER_ADDRESS_SEPOLIA")
    SEPOLIA_ETHERSCAN_API_KEY = os.environ.get("SEPOLIA_ETHERSCAN_API_KEY")
    API_URL = os.environ.get("API_URL")
    web3 = Web3(Web3.HTTPProvider(ALCHEMY_RPC_URL))

    # ERC-20 ABI (Minimal for Transfers)
    ERC20_ABI = json.loads(
        """
    [
        {
            "constant": false,
            "inputs": [
                {"name": "_to", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": false,
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]
    """
    )

    def get_usdc_contract(self) -> Contract:
        return self.web3.eth.contract(
            address=Web3.to_checksum_address(self.USDC_CONTRACT_ADDRESS_SEPOLIA),
            abi=self.ERC20_ABI,
        )

    def check_web3_connection(self) -> bool:
        if not self.web3.is_connected():
            return False

        else:
            return True

    def send_usdc(
        self, receiver_address: str, transfer_id: int, percentage: float = 100.0
    ) -> str:
        """
        Automatically sends USDC and retries if needed.
        """
        try:
            transfer = Transfer.objects.get(id=transfer_id)
        except ObjectDoesNotExist:
            raise ValueError("Transfer not found.")

        sender = Web3.to_checksum_address(self.STABLE_TRANSFER_ADDRESS_SEPOLIA)
        receiver = Web3.to_checksum_address(receiver_address)

        amount_wei = int(
            (
                Decimal(str(transfer.contract.reward))
                * Decimal(str(percentage))
                / Decimal("100")
            )
            * Decimal("1e6")
        )

        usdc_contract = self.get_usdc_contract()

        latest_block = self.web3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas", self.web3.to_wei(10, "gwei"))
        priority_fee = self.web3.to_wei(2, "gwei")

        nonce = self.web3.eth.get_transaction_count(
            sender, "pending"
        )  # Get latest nonce

        max_retries = 3  # Maximum retry attempts
        retry_delay = 10  # Seconds between retries

        for attempt in range(max_retries):
            try:
                priority_fee = self.web3.to_wei(
                    2 + attempt * 2, "gwei"
                )  # Increase priority fee each retry
                max_fee = (
                    base_fee + priority_fee + self.web3.to_wei(1, "gwei")
                )  # Add buffer

                tx = usdc_contract.functions.transfer(
                    receiver, amount_wei
                ).build_transaction(
                    {
                        "from": sender,
                        "nonce": nonce,
                        "gas": 150000,  # Slightly higher gas limit
                        "maxPriorityFeePerGas": priority_fee,
                        "maxFeePerGas": max_fee,
                    }
                )

                private_key_bytes = Web3.to_bytes(hexstr=self.PRIVATE_KEY)
                signed_tx = self.web3.eth.account.sign_transaction(
                    tx, private_key_bytes
                )

                tx_hash = self.web3.eth.send_raw_transaction(signed_tx.raw_transaction)
                return self.web3.to_hex(tx_hash)  # ✅ Successful transaction sent

            except Exception as e:
                print(f"⚠️ Attempt {attempt + 1} failed: {e}")

                if "replacement transaction underpriced" in str(e):
                    print("🔄 Retrying with a higher gas fee...")
                    time.sleep(retry_delay)  # Wait before retrying

                else:
                    raise e  # ❌ If error is not related to gas fees, stop retrying

        raise ValueError("❌ Failed to send USDC after multiple attempts.")

    def get_tx_data(self, tx_hash: str) -> Dict:

        # Get the transaction receipt, which includes logs
        params = {
            "module": "proxy",
            "action": "eth_getTransactionReceipt",
            "txhash": tx_hash,
            "apikey": self.SEPOLIA_ETHERSCAN_API_KEY,
        }

        response = requests.get(self.API_URL, params=params)
        tx_data = response.json().get("result")
        return tx_data

    def get_transferred_usdc(self, tx_data: Dict) -> List[Dict]:
        print("🔍 Raw Logs from Transaction:")
        print(json.dumps(tx_data.get("logs", []), indent=4))  # Pretty print logs

        transfers = []

        # 🔹 Use the **full** ERC-20 Transfer event signature hash
        TRANSFER_TOPIC_HASH = (
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        )

        for log in tx_data.get("logs", []):
            print(f"🔄 Processing log: {log}")

            topics = log.get("topics", [])

            # ✅ Ensure this is an **ERC-20 Transfer event**
            if not topics or topics[0].lower() != TRANSFER_TOPIC_HASH:
                print("⚠️ Skipping log due to missing or incorrect transfer topic.")
                continue

            # ✅ Extract sender and receiver addresses correctly
            from_address = Web3.to_checksum_address("0x" + topics[1][-40:])
            to_address = Web3.to_checksum_address("0x" + topics[2][-40:])

            # ✅ Convert USDC amount from hex (6 decimals)
            value = int(log.get("data", "0x0"), 16) / 1e6

            print(
                f"✅ USDC Transfer Found: {from_address} -> {to_address}, Amount: {value}"
            )

            transfers.append(
                {
                    "contract": Web3.to_checksum_address(log.get("address")),
                    "from": from_address,
                    "to": to_address,
                    "value": value,
                }
            )

        if not transfers:
            print("❌ No valid USDC transfers found.")

        return transfers

    def is_receiver(self, tx_data: Dict, address_destination: str) -> bool:
        receiver = tx_data.get("to", "").lower()
        return receiver == address_destination.lower()

    def is_sender(self, tx_data: Dict, address_sender: str) -> bool:
        sender = tx_data.get("from", "").lower()
        return sender == address_sender.lower()

    def is_usdc_amount_correct(
        self, transfer: List[Dict], contract_price: float
    ) -> bool:
        usdc_sent = transfer["value"]
        print(usdc_sent, contract_price)
        return usdc_sent >= contract_price - 20
