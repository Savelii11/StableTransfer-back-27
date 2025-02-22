import os
from typing import Dict, List

import requests


class USDCTransfer:
    # ERC‑20 Transfer event signature hash (first topic) starts with this prefix
    TRANSFER_TOPIC_PREFIX = os.environ.get("TRANSFER_TOPIC_PREFIX")

    STABLE_TRANSFER_ADDRESS_SEPOLIA = os.environ.get("STABLE_TRANSFER_ADDRESS_SEPOLIA")
    USDC_CONTRACT_ADDRESS_SEPOLIA = os.environ.get("USDC_CONTRACT_ADDRESS_SEPOLIA")
    SEPOLIA_ETHERSCAN_API_KEY = os.environ.get("SEPOLIA_ETHERSCAN_API_KEY")
    API_URL = os.environ.get("API_URL")

    def get_tx_data(self, tx_hash: str, api_url: str) -> Dict:

        # Get the transaction receipt, which includes logs
        params = {
            "module": "proxy",
            "action": "eth_getTransactionReceipt",
            "txhash": tx_hash,
            "apikey": self.SEPOLIA_ETHERSCAN_API_KEY,
        }

        response = requests.get(api_url, params=params)
        tx_data = response.json().get("result")
        return tx_data

    def get_transferred_usdc(self, tx_data: Dict) -> List[Dict]:
        transfer = {}

        for log in tx_data.get("logs", []):
            # Check if the log's address matches the USDC contract address (case-insensitive)
            if (
                log.get("address", "").lower()
                == self.USDC_CONTRACT_ADDRESS_SEPOLIA.lower()
            ):
                topics = log.get("topics", [])
                if topics and topics[0].startswith(self.TRANSFER_TOPIC_PREFIX):
                    # Extract the "from" and "to" addresses from topics[1] and topics[2]
                    from_address = "0x" + topics[1][-40:]
                    to_address = "0x" + topics[2][-40:]
                    # Convert the transferred value from hex to integer
                    value = int(log.get("data", "0x0"), 16)
                    transfer["contract"] = log.get("address")
                    transfer["from"] = from_address
                    transfer["to"] = to_address
                    transfer["value"] = value / 1e6

        return transfer

    def is_receiver(self, tx_data: Dict, address_destination: str) -> bool:
        # Check the transaction's "to" field for the receiver address.
        receiver = tx_data.get("to", "").lower()
        return receiver == address_destination.lower()

    def is_usdc_amount_correct(
        self, transfer: List[Dict], contract_price: float
    ) -> bool:
        usdc_sent = transfer["value"]
        print(usdc_sent, contract_price)
        return usdc_sent >= contract_price - 20


usdc_transfer = USDCTransfer()

# Use the correct transaction hash and API endpoint
tx_hash = "0xe414909f4fb5ce964697112a49873b7d75d448bbbc2f5455ccc2b47fceed4201"

tx_data = usdc_transfer.get_tx_data(tx_hash, usdc_transfer.API_URL)

if not tx_data:
    print("Could not retrieve transaction receipt")
    exit()

print(tx_data)

transfer = usdc_transfer.get_transferred_usdc(tx_data)

print(f"USDC Token Transfers in the transaction: {transfer}")


print(usdc_transfer.is_receiver(tx_data, usdc_transfer.STABLE_TRANSFER_ADDRESS_SEPOLIA))

print(usdc_transfer.is_usdc_amount_correct(transfer, float(10020)))
