"""Stage 2.5: empirically record what the real runtime's gl.nondet.web.get / render return.
Run against a FRESH simulator process (see scripts/run_real_web.sh) - glsim 0.29.2 only
survives one contract load per process."""
import json
from pathlib import Path

from gltest import get_accounts
from genlayer_py.types import TransactionStatus  # noqa: F401
from rt import client, wait, leader_result, votes, read

PROBE = Path(__file__).parent / "probe_contracts" / "response_probe.py"
OUT = Path(__file__).parent / "_response_probe_result.json"


def test_response_probe():
    acct = get_accounts()[0]
    h = client().deploy_contract(code=PROBE.read_text(encoding="utf-8").encode(), account=acct, args=[])
    r = wait(h)
    addr = r["data"]["contract_address"]
    assert leader_result(r)["execution_result"] == "SUCCESS", leader_result(r)
    result = {"deploy_tx": h, "address": addr}

    h1 = client().write_contract(address=addr, function_name="probe_get", account=acct, args=["https://example.org/"])
    r1 = wait(h1)
    result["get_tx"] = h1
    result["get_status"] = r1.get("status_name")
    result["get_votes"] = votes(r1)
    result["get_leader"] = leader_result(r1)["execution_result"]
    result["get_observed"] = json.loads(read(addr, "read_get"))

    h2 = client().write_contract(address=addr, function_name="probe_render", account=acct, args=["https://example.org/"])
    r2 = wait(h2)
    result["render_tx"] = h2
    result["render_status"] = r2.get("status_name")
    result["render_votes"] = votes(r2)
    result["render_leader"] = leader_result(r2)
    result["render_observed"] = read(addr, "read_render")
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print("RESPONSE_PROBE", json.dumps(result, indent=2, default=str))
