import time

from web3 import Web3

# Sepolia Alchemy RPC URL
ALCHEMY_RPC_URL = (
    "https://eth-sepolia.g.alchemy.com/v2/c4rQ3N5uTkW1fAHlf3yHbAkBJwVN3N4S"
)
PRIVATE_KEY = "45fe119abab22f659bd642c1a8c29270faebcc46c7016d6e18c09ddc1e173581"  # Your private key
USDC_CONTRACT_ADDRESS = "0x1C7D4B196CB0C7B01D743FBC6116A902379C7238"
RECIPIENT_ADDRESS = "0x72a4C9507b956C94824E897C24dFf520DcdB4f44"  # Recipient wallet

web3 = Web3(Web3.HTTPProvider(ALCHEMY_RPC_URL))

if not web3.is_connected():
    raise Exception("❌ Failed to connect to Sepolia network")

print("✅ Connected to Sepolia Testnet")

# Get sender's address from private key
sender_account = web3.eth.account.from_key(PRIVATE_KEY)
SENDER_ADDRESS = sender_account.address
print(f"📩 Sender Address: {SENDER_ADDRESS}")

# Convert USDC contract address to checksum format
USDC_CONTRACT_ADDRESS = web3.to_checksum_address(USDC_CONTRACT_ADDRESS)

# ERC-20 ABI for transfer & balanceOf
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# Instantiate USDC contract
usdc_contract = web3.eth.contract(address=USDC_CONTRACT_ADDRESS, abi=ERC20_ABI)

# ✅ Step 1: Check USDC Balance
balance = usdc_contract.functions.balanceOf(SENDER_ADDRESS).call()
balance_in_usdc = balance / 10**6  # Convert to USDC decimals
print(f"💰 USDC Balance: {balance_in_usdc} USDC")

if balance_in_usdc < 1:
    raise Exception("❌ Not enough USDC to transfer 1 USDC")

# ✅ Step 2: Transfer 1 USDC
print("🚀 Sending 1 USDC to recipient...")

# Convert 1 USDC to smallest unit (since USDC has 6 decimals)
amount_in_smallest_unit = 1 * 10**6

# Get nonce for sender
nonce = web3.eth.get_transaction_count(SENDER_ADDRESS)

# Build the transaction
transaction = usdc_contract.functions.transfer(
    RECIPIENT_ADDRESS, amount_in_smallest_unit
).build_transaction(
    {
        "gas": 100000,
        "gasPrice": web3.to_wei("4.4", "gwei"),  # Adjusted gas price
        "nonce": nonce,
        "chainId": 11155111,  # Sepolia Chain ID
    }
)

# Sign the transaction
signed_tx = web3.eth.account.sign_transaction(transaction, PRIVATE_KEY)

# Send the transaction
tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
print(f"✅ USDC Transfer Sent! Tx Hash: {web3.to_hex(tx_hash)}")

# ⏳ Wait for transfer confirmation
print("⏳ Waiting for transfer confirmation...")
try:
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status == 1:
        print(f"✅ USDC Transfer Confirmed in block {receipt.blockNumber}")
    else:
        raise Exception("❌ USDC Transfer failed!")
except Exception as e:
    raise Exception(f"❌ Error waiting for transfer confirmation: {e}")
