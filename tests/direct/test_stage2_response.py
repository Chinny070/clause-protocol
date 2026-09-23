import datetime

import pytest

from helpers import CONTRACT_PATH, ONE_GEN, create_constitution_stage2, file_claim, fund, issue, respond


def _iso(unix_seconds: int) -> str:
    return datetime.datetime.fromtimestamp(unix_seconds, tz=datetime.timezone.utc).isoformat()


def _setup_claim(direct_deploy, direct_vm, direct_accounts, response_period_s=14 * 24 * 3600):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution_stage2(contract, program_id, manufacturer_response_period_s=response_period_s)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)
    claim_id = file_claim(contract, direct_vm, warranty_id, holder)
    return contract, manufacturer, holder, claim_id


def test_valid_accept(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts)
    respond(contract, direct_vm, claim_id, manufacturer, "ACCEPT")
    claim = contract.get_claim(claim_id)
    assert claim["status"] == "ACCEPTED"
    assert claim["manufacturer_response"] == "ACCEPT"
    assert claim["responded_at"] > 0


def test_valid_dispute(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts)
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")
    assert contract.get_claim(claim_id)["status"] == "DISPUTED"


def test_invalid_decision_literal_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        respond(contract, direct_vm, claim_id, manufacturer, "MAYBE")


def test_unauthorized_response_stranger_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts)
    stranger = direct_accounts[2]
    with pytest.raises(Exception):
        respond(contract, direct_vm, claim_id, stranger, "ACCEPT")


def test_holder_cannot_respond_as_manufacturer(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts)
    with pytest.raises(Exception):
        respond(contract, direct_vm, claim_id, holder, "ACCEPT")


def test_unrelated_manufacturer_cannot_respond(direct_deploy, direct_vm, direct_accounts):
    """A manufacturer of a DIFFERENT program must not be able to respond to this claim."""
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts)
    other_manufacturer = direct_accounts[3]
    direct_vm.sender = other_manufacturer
    contract.create_program("Other Co")
    with pytest.raises(Exception):
        respond(contract, direct_vm, claim_id, other_manufacturer, "ACCEPT")


def test_duplicate_response_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts)
    respond(contract, direct_vm, claim_id, manufacturer, "ACCEPT")
    with pytest.raises(Exception):
        respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")


def test_response_immutable_once_committed(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts)
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")
    before = contract.get_claim(claim_id)
    with pytest.raises(Exception):
        respond(contract, direct_vm, claim_id, manufacturer, "ACCEPT")
    assert contract.get_claim(claim_id) == before


def test_response_at_exact_deadline_succeeds(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts, response_period_s=1000)
    deadline = contract.get_claim(claim_id)["response_deadline"]
    direct_vm.warp(_iso(deadline))
    respond(contract, direct_vm, claim_id, manufacturer, "ACCEPT")
    assert contract.get_claim(claim_id)["status"] == "ACCEPTED"


def test_response_one_second_late_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts, response_period_s=1000)
    deadline = contract.get_claim(claim_id)["response_deadline"]
    direct_vm.warp(_iso(deadline + 1))
    with pytest.raises(Exception):
        respond(contract, direct_vm, claim_id, manufacturer, "ACCEPT")


def test_silence_past_deadline_defaults_to_disputed(direct_deploy, direct_vm, direct_accounts):
    """No response at all, once the deadline passes: the claim reads as DISPUTED (silence
    does not grant a no-contest), letting it proceed toward evidence."""
    contract, manufacturer, holder, claim_id = _setup_claim(direct_deploy, direct_vm, direct_accounts, response_period_s=1000)
    deadline = contract.get_claim(claim_id)["response_deadline"]
    direct_vm.warp(_iso(deadline + 1))
    assert contract.get_claim(claim_id)["status"] == "DISPUTED"
