import datetime

import pytest

from helpers import CONTRACT_PATH, ONE_GEN, create_constitution, fund, issue


def _iso(unix_seconds: int) -> str:
    return datetime.datetime.fromtimestamp(unix_seconds, tz=datetime.timezone.utc).isoformat()


def _setup(direct_deploy, direct_vm, direct_accounts, remedy=6 * ONE_GEN):
    manufacturer, holder = direct_accounts[0], direct_accounts[1]
    direct_vm.sender = manufacturer
    contract = direct_deploy(CONTRACT_PATH)
    program_id = contract.create_program("Acme")
    constitution_id = create_constitution(contract, program_id)
    fund(contract, direct_vm, program_id, manufacturer, 10 * ONE_GEN)
    return contract, program_id, constitution_id, manufacturer, holder


def test_now_reflects_message_datetime(direct_deploy, direct_vm, direct_accounts):
    contract, *_ = _setup(direct_deploy, direct_vm, direct_accounts)
    direct_vm.warp(_iso(1_700_000_000))
    assert int(contract.now()) == 1_700_000_000


def test_before_coverage_status_is_active(direct_deploy, direct_vm, direct_accounts):
    """A passport whose coverage_start is in the future is still modeled as ACTIVE in Stage
    1 - CLAUSE has no separate PENDING/NOT_YET_STARTED state (docs/STATE_MACHINES.md only
    defines ACTIVE/EXPIRED/CANCELLED). This is recorded as a Stage 1 scope note, not a bug:
    Stage 2's claim-filing logic is what will actually need a before-coverage distinction."""
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now + 1000, coverage_end=now + 2000,
    )
    assert contract.get_passport(warranty_id)["status"] == "ACTIVE"


def test_exact_coverage_start_boundary(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 1000,
    )
    assert contract.get_passport(warranty_id)["status"] == "ACTIVE"


def test_active_coverage_mid_window(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 1000,
    )
    direct_vm.warp(_iso(now + 500))
    assert contract.get_passport(warranty_id)["status"] == "ACTIVE"


def test_exact_expiry_boundary_is_expired(direct_deploy, direct_vm, direct_accounts):
    """docs/STATE_MACHINES.md: expiry is derived at read time; coverage_end itself is the
    first instant a passport reads as EXPIRED (>= comparison), never still ACTIVE."""
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 1000,
    )
    direct_vm.warp(_iso(now + 1000))
    assert contract.get_passport(warranty_id)["status"] == "EXPIRED"


def test_one_second_before_expiry_still_active(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 1000,
    )
    direct_vm.warp(_iso(now + 999))
    assert contract.get_passport(warranty_id)["status"] == "ACTIVE"


def test_after_expiry_status_is_expired(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 1000,
    )
    direct_vm.warp(_iso(now + 5000))
    assert contract.get_passport(warranty_id)["status"] == "EXPIRED"


def test_invalid_range_start_after_end_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    with pytest.raises(Exception):
        issue(
            contract, direct_vm, program_id, constitution_id, manufacturer, holder,
            max_remedy=6 * ONE_GEN, coverage_start=now + 1000, coverage_end=now,
        )


def test_invalid_range_start_equals_end_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    with pytest.raises(Exception):
        issue(
            contract, direct_vm, program_id, constitution_id, manufacturer, holder,
            max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now,
        )


def test_overflow_guard_on_implausible_duration_rejected(direct_deploy, direct_vm, direct_accounts):
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    with pytest.raises(Exception):
        issue(
            contract, direct_vm, program_id, constitution_id, manufacturer, holder,
            max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 200 * 365 * 24 * 3600,
        )


def test_cancelled_status_survives_past_expiry(direct_deploy, direct_vm, direct_accounts):
    """A CANCELLED warranty must never flip back to EXPIRED just because coverage_end has
    since passed - status derivation only upgrades ACTIVE -> EXPIRED, never touches a
    terminal CANCELLED (docs/STATE_MACHINES.md)."""
    contract, program_id, constitution_id, manufacturer, holder = _setup(direct_deploy, direct_vm, direct_accounts)
    now = int(contract.now())
    warranty_id = issue(
        contract, direct_vm, program_id, constitution_id, manufacturer, holder,
        max_remedy=6 * ONE_GEN, coverage_start=now, coverage_end=now + 1000,
    )
    direct_vm.sender = holder
    contract.cancel_warranty(warranty_id)
    direct_vm.warp(_iso(now + 5000))
    assert contract.get_passport(warranty_id)["status"] == "CANCELLED"
