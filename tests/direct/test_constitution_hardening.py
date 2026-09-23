"""Stage 1 hardening pass, item 1: constitution immutability, proven against the contract's
own authoritative write-method inventory rather than a hand-maintained forbidden-name list.

`_write_method_names` reads `ClauseProtocol.__get_schema__()` - the same JSON schema GenVM
itself uses for ABI introspection - and extracts every method whose `readonly` flag is False.
If a future stage adds, renames, or removes a write method, `test_write_method_inventory_
matches_expected_set` fails immediately, forcing this file's audit to be extended before
anyone can trust its coverage claim again.
"""

import json
import subprocess

import pytest

from helpers import (
    CONTRACT_PATH, ONE_GEN, create_constitution, create_constitution_stage2, file_claim,
    freeze_evidence, fund, issue, respond, submit_evidence,
)


def _load_schema() -> dict:
    """Extracts the contract's ABI schema straight from source via `genvm-lint schema
    --json`, the same tool GenVM itself uses for ABI introspection - not from the
    direct-mode-wrapped runtime class, whose `__init__` the gltest-direct loader strips in a
    way that breaks `genlayer.py.get_schema.get_schema()` (confirmed while writing this
    test: it raises `TypeError: __init__ is absent`)."""
    result = subprocess.run(
        ["genvm-lint", "schema", CONTRACT_PATH, "--json"],
        capture_output=True, text=True, cwd=".",
    )
    payload = json.loads(result.stdout)
    assert payload.get("ok") is True, payload
    return payload["schema"]


def _write_method_names(schema: dict) -> list:
    return sorted(name for name, meth in schema["methods"].items() if meth.get("readonly") is False)


EXPECTED_WRITE_METHODS = {
    "create_program",
    "pause_program",
    "resume_program",
    "retire_program",
    "create_constitution",
    "fund_pool",
    "withdraw_pool",
    "issue_warranty",
    "cancel_warranty",
    "release_expired_reservation",
    # Stage 2 additions (docs/STATE_MACHINES.md Claim/Evidence lifecycle) - none of these
    # take a constitution_id and mutate that record; each is exercised below for the same
    # frozen-constitution-untouched guarantee as every Stage 1 write method.
    "file_claim",
    "respond_to_claim",
    "submit_evidence",
    "freeze_evidence",
}


def test_write_method_inventory_matches_expected_set(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    names = _write_method_names(_load_schema())
    assert set(names) == EXPECTED_WRITE_METHODS, (
        "The write-method surface changed since this hardening pass was written. Every test "
        "below assumes exactly this set of write methods exists - extend the audit in this "
        "file for any newly added method before trusting constitution-immutability coverage."
    )


def test_every_non_constitution_write_method_leaves_frozen_constitution_untouched(
    direct_deploy, direct_vm, direct_accounts
):
    """Exercises every write method in EXPECTED_WRITE_METHODS except create_constitution
    itself, in realistic sequence, snapshotting the frozen constitution's full public view
    after each call. Full-dict equality (`==`) on the get_constitution() result proves
    field-level semantic equality of every frozen value (fingerprint compared as its exact
    hex string, i.e. byte-for-byte), not just a spot-checked subset."""
    manufacturer, holder, other_holder = direct_accounts[0], direct_accounts[1], direct_accounts[2]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)

    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 20 * ONE_GEN)

    # issue_warranty freezes the constitution as a side effect - this first call is the
    # freeze event itself, not part of the "leaves it untouched" claim.
    warranty_id = issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN, commitment_seed=1)
    frozen_snapshot = contract.get_constitution(constitution_id)
    assert frozen_snapshot["is_frozen"] is True

    def assert_unchanged(label: str):
        current = contract.get_constitution(constitution_id)
        assert current == frozen_snapshot, f"constitution mutated by: {label}"

    # create_program: unrelated program, must not touch this constitution.
    direct_vm.sender = manufacturer
    contract.create_program("Unrelated Program")
    assert_unchanged("create_program (unrelated)")

    # pause_program / resume_program: mutate WarrantyProgram.status only.
    contract.pause_program(program_id)
    assert_unchanged("pause_program")
    contract.resume_program(program_id)
    assert_unchanged("resume_program")

    # fund_pool / withdraw_pool: mutate WarrantyPool balances only.
    fund(contract, direct_vm, program_id, manufacturer, 1 * ONE_GEN)
    assert_unchanged("fund_pool")
    direct_vm.sender = manufacturer
    contract.withdraw_pool(program_id, 1 * ONE_GEN)
    assert_unchanged("withdraw_pool")

    # issue_warranty again: a SECOND issuance against an already-frozen constitution must be
    # a complete no-op on the constitution (the is_frozen/frozen_at assignment is guarded by
    # `if not constitution.is_frozen`) - this is the idempotent-freeze claim, tested directly.
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, other_holder, max_remedy=5 * ONE_GEN, commitment_seed=2)
    assert_unchanged("issue_warranty (second issuance against already-frozen constitution)")

    # cancel_warranty: mutates WarrantyPassport/Reservation/WarrantyPool only.
    direct_vm.sender = holder
    contract.cancel_warranty(warranty_id)
    assert_unchanged("cancel_warranty")

    # release_expired_reservation: exercised via a short-lived third warranty so a genuinely
    # expired reservation exists to release, without disturbing the frozen snapshot's source
    # constitution_id (still the same one).
    direct_vm.sender = manufacturer
    now = int(contract.now())
    short_warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=1 * ONE_GEN, coverage_start=now, coverage_end=now + 10, commitment_seed=3,
    )
    assert_unchanged("issue_warranty (third issuance, before warp)")
    direct_vm.warp(_iso(now + 20))
    contract.release_expired_reservation(short_warranty_id)
    assert_unchanged("release_expired_reservation")

    # file_claim / respond_to_claim / submit_evidence / freeze_evidence (Stage 2): none of
    # these take a constitution_id, but each is exercised here for the same guarantee. Needs
    # a fresh, still-ACTIVE warranty since `warranty_id` was cancelled above.
    direct_vm.sender = manufacturer
    claim_warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, other_holder,
        max_remedy=1 * ONE_GEN, commitment_seed=4,
    )
    assert_unchanged("issue_warranty (fourth issuance, for the claim exercises below)")
    claim_id = file_claim(contract, direct_vm, claim_warranty_id, other_holder)
    assert_unchanged("file_claim")
    respond(contract, direct_vm, claim_id, manufacturer, "DISPUTE")
    assert_unchanged("respond_to_claim")
    direct_vm.mock_web(r"https://docs\.genlayer\.com/hardening-evidence", {"status": 200, "body": "Evidence text."})
    evidence_id = submit_evidence(contract, direct_vm, claim_id, other_holder, "https://docs.genlayer.com/hardening-evidence", "RECEIPT")
    assert_unchanged("submit_evidence")
    freeze_evidence(contract, direct_vm, claim_id, other_holder)
    assert_unchanged("freeze_evidence")

    # retire_program is terminal - exercised last.
    direct_vm.sender = manufacturer
    contract.retire_program(program_id)
    assert_unchanged("retire_program")


def test_retire_program_does_not_touch_constitution(direct_deploy, direct_vm, direct_accounts):
    """Isolated, minimal repro of the retire_program case from the sequential test above -
    kept separate so a future regression here fails with an unambiguous, single-cause test."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 5 * ONE_GEN)
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=5 * ONE_GEN)

    before = contract.get_constitution(constitution_id)
    contract.retire_program(program_id)
    after = contract.get_constitution(constitution_id)
    assert before == after
    assert contract.get_program(program_id)["status"] == "RETIRED"


def test_frozen_at_and_fingerprint_survive_repeated_issuance_byte_for_byte(direct_deploy, direct_vm, direct_accounts):
    """Direct, explicit test of the idempotent-freeze claim on the two fields most at risk of
    a subtle re-write bug: frozen_at (a timestamp, easy to accidentally refresh) and
    fingerprint (bytes, easy to accidentally recompute)."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    now = int(contract.now())
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=3 * ONE_GEN, commitment_seed=1)
    c1 = contract.get_constitution(constitution_id)
    assert c1["frozen_at"] == now

    direct_vm.warp(_iso(now + 999))
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=3 * ONE_GEN, commitment_seed=2)
    c2 = contract.get_constitution(constitution_id)

    assert c2["frozen_at"] == c1["frozen_at"] == now  # NOT now + 999
    assert c2["fingerprint"] == c1["fingerprint"]
    assert c1 == c2


def _iso(unix_seconds: int) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(unix_seconds, tz=datetime.timezone.utc).isoformat()
