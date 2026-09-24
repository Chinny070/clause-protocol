"""Thin real-runtime helpers (Stage 2.5): talk to a live GenLayer simulator through
genlayer-py, no mocks. Every write waits for the transaction to reach FINALIZED and returns
the full receipt so callers can inspect consensus data, not just a hash."""
from pathlib import Path

from genlayer_py.types import TransactionStatus
from gltest import get_accounts, get_gl_client

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "clause_protocol.py"


def client():
    return get_gl_client()


def wait(tx_hash, status=TransactionStatus.FINALIZED):
    return client().wait_for_transaction_receipt(
        transaction_hash=tx_hash, status=status, interval=1000, retries=90, full_transaction=True,
    )


def leader_result(receipt) -> dict:
    lr = receipt["consensus_data"]["leader_receipt"][0]
    return {"execution_result": lr.get("execution_result"), "result": lr.get("result"),
            "stderr": (lr.get("genvm_result") or {}).get("stderr")}


def votes(receipt) -> dict:
    return receipt["consensus_data"]["votes"]


def deploy(account):
    h = client().deploy_contract(code=CONTRACT.read_text(encoding="utf-8").encode(), account=account, args=[])
    r = wait(h)
    return r["data"]["contract_address"], r


def write(addr, fn, args, account, value=0):
    h = client().write_contract(address=addr, function_name=fn, account=account, args=args, value=value)
    return h, wait(h)


def read(addr, fn, args=None):
    return client().read_contract(address=addr, function_name=fn, args=args or [])
