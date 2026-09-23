"""Stage 1 hardening pass, item 4: timestamp trust boundary audit.

Claim under test: every protocol-controlled timestamp CLAUSE stores
(`WarrantyProgram.created_at`, `WarrantyConstitution.frozen_at`, `WarrantyPassport.
registered_at`, `Reservation.created_at`/`released_at`) is derived exclusively from
`gl.message_raw["datetime"]` via `_now()`, and there is no write-method parameter through
which a caller can directly set or override any of them. `coverage_start`/`coverage_end` are
the one deliberate exception - they are manufacturer-asserted warranty terms, not protocol
timestamps, and are never conflated with the protocol-derived fields (docs/DATA_MODEL.md,
docs/ARCHITECTURE.md's nine-timestamp taxonomy).

`direct_vm.warp(iso_string)` is the gltest-direct harness's way of *simulating* the GenVM
runtime's control over `gl.message_raw["datetime"]` for testing purposes. It is not analogous
to a caller/attacker parameter on any public method - no public method here takes a
timestamp-shaped argument at all (proven by test_no_write_method_accepts_a_protocol_
timestamp_parameter below), so there is no equivalent lever for a real caller to pull.
"""

import datetime

from helpers import CONTRACT_PATH, ONE_GEN, create_constitution, fund, issue


def _iso(unix_seconds: int) -> str:
    return datetime.datetime.fromtimestamp(unix_seconds, tz=datetime.timezone.utc).isoformat()


_PROTOCOL_TIMESTAMP_PARAM_NAMES = {
    "registered_at",
    "created_at",
    "frozen_at",
    "released_at",
    "now",
    "datetime",
    "timestamp",
}


def test_no_write_method_accepts_a_protocol_timestamp_parameter(direct_deploy, direct_vm, direct_accounts):
    """Schema-derived (not hand-maintained): confirms no public write method's parameter list
    contains anything shaped like a protocol timestamp. coverage_start/coverage_end are
    expected and excluded deliberately - they are asserted warranty terms, audited separately
    below, never treated as protocol-authoritative."""
    import json
    import subprocess

    result = subprocess.run(
        ["genvm-lint", "schema", CONTRACT_PATH, "--json"],
        capture_output=True, text=True, cwd=".",
    )
    payload = json.loads(result.stdout)
    assert payload.get("ok") is True, payload
    schema = payload["schema"]

    offending = []
    for name, meth in schema["methods"].items():
        if meth.get("readonly"):
            continue
        param_names = {p[0] for p in meth.get("params", [])} | set(meth.get("kwparams", {}).keys())
        hit = param_names & _PROTOCOL_TIMESTAMP_PARAM_NAMES
        if hit:
            offending.append((name, hit))
    assert offending == [], f"write method(s) accept a protocol-timestamp-shaped parameter: {offending}"


def test_registered_at_matches_protocol_time_exactly(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    direct_vm.warp(_iso(1_800_000_000))
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=1 * ONE_GEN, coverage_start=1_800_000_000, coverage_end=1_800_100_000,
    )
    passport = contract.get_passport(warranty_id)
    assert passport["registered_at"] == 1_800_000_000


def test_registered_at_is_independent_of_caller_supplied_coverage_dates(direct_deploy, direct_vm, direct_accounts):
    """A caller choosing wildly different coverage_start/coverage_end values must never move
    registered_at - the two are structurally unrelated fields, never derived from each
    other."""
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    direct_vm.warp(_iso(1_800_000_000))
    # coverage_start is 50 years in the future, coverage_end further still - registered_at
    # must still read as the actual protocol time of the call, not the asserted window.
    far_future = 1_800_000_000 + 50 * 365 * 24 * 3600
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=1 * ONE_GEN, coverage_start=far_future, coverage_end=far_future + 1000,
    )
    passport = contract.get_passport(warranty_id)
    assert passport["registered_at"] == 1_800_000_000
    assert passport["coverage_start"] == far_future  # asserted term, stored as given
    assert passport["registered_at"] != passport["coverage_start"]


def test_frozen_at_matches_protocol_time_at_the_freeze_moment(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    direct_vm.warp(_iso(1_900_000_000))
    issue(contract, direct_vm, program_id, constitution_id, manufacturer, holder, max_remedy=1 * ONE_GEN)
    assert contract.get_constitution(constitution_id)["frozen_at"] == 1_900_000_000


def test_program_created_at_matches_protocol_time(direct_deploy, direct_vm, direct_accounts):
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.warp(_iso(2_000_000_000))
    program_id = contract.create_program("Acme")
    assert contract.get_program(program_id)["created_at"] == 2_000_000_000


def test_reservation_created_and_released_at_match_protocol_time(direct_deploy, direct_vm, direct_accounts):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)

    direct_vm.warp(_iso(2_100_000_000))
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=1 * ONE_GEN, coverage_start=2_100_000_000, coverage_end=2_100_000_100,
    )
    reservation_id = contract.get_passport(warranty_id)["reservation_id"]
    assert contract.get_reservation(reservation_id)["created_at"] == 2_100_000_000

    direct_vm.warp(_iso(2_100_000_200))
    contract.release_expired_reservation(warranty_id)
    assert contract.get_reservation(reservation_id)["released_at"] == 2_100_000_200


def test_now_is_read_live_not_cached_across_calls(direct_deploy, direct_vm, direct_accounts):
    """Confirms _now() re-reads gl.message_raw["datetime"] on every call rather than caching
    a value from deploy time - two calls at two different warped times must disagree."""
    manufacturer = direct_accounts[0]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)

    direct_vm.warp(_iso(1_000_000_000))
    t1 = int(contract.now())
    direct_vm.warp(_iso(1_000_000_555))
    t2 = int(contract.now())

    assert t1 == 1_000_000_000
    assert t2 == 1_000_000_555
    assert t1 != t2
