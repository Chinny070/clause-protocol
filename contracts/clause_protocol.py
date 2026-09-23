# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
from dataclasses import dataclass
import datetime
import hashlib
import json

# CLAUSE Stage 1 - Deterministic Foundation.
#
# Scope: WarrantyProgram, WarrantyConstitution, Clause, WarrantyPassport, WarrantyPool,
# Reservation. No Claim/EvidenceRecord/Adjudication/Challenge/ResolutionReceipt yet (Stages
# 2-4). No gl.nondet.*, no LLM calls, no evidence retrieval, no settlement lifecycle.
#
# See docs/ARCHITECTURE.md, docs/DATA_MODEL.md, docs/STATE_MACHINES.md,
# docs/WARRANTY_CONSTITUTION.md and docs/ECONOMIC_INVARIANTS.md for the frozen Stage 0
# design this file implements. Deviations from those docs are called out inline and
# summarized in STAGE_1_VERIFICATION.md.

PROGRAM_ACTIVE = "ACTIVE"
PROGRAM_PAUSED = "PAUSED"
PROGRAM_RETIRED = "RETIRED"

PASSPORT_ACTIVE = "ACTIVE"
PASSPORT_EXPIRED = "EXPIRED"
PASSPORT_CANCELLED = "CANCELLED"

RESERVATION_ACTIVE = "ACTIVE"
RESERVATION_RELEASED = "RELEASED"
RESERVATION_CONSUMED = "CONSUMED"

CLAUSE_COVERED = "COVERED"
CLAUSE_EXCLUDED = "EXCLUDED"

REMEDY_FULL_REFUND = "FULL_REFUND"
REMEDY_REPAIR_CREDIT = "REPAIR_CREDIT"
REMEDY_PARTIAL_BPS = "PARTIAL_BPS"
REMEDY_NONE = "NONE"
_REMEDY_KINDS = (REMEDY_FULL_REFUND, REMEDY_REPAIR_CREDIT, REMEDY_PARTIAL_BPS, REMEDY_NONE)

# Frozen minimum outcome vocabulary from docs/ADJUDICATION_SCHEMA.md. Stage 1 never produces
# an outcome itself (no adjudicator exists yet) but the remedy table is keyed by these
# literals now so Stage 3/4 can settle against it without a schema migration.
_OUTCOMES = (
    "COVERED",
    "NOT_COVERED",
    "INSUFFICIENT_EVIDENCE",
    "EVIDENCE_UNAVAILABLE",
    "INVALID_CLAIM",
    "ACCEPTED_NO_CONTEST",
)

# Constitution-level frozen policy enums (docs/WARRANTY_CONSTITUTION.md).
_EVIDENCE_GAP_BEHAVIORS = ("RULE_FOR_HOLDER", "RULE_FOR_MANUFACTURER", "BLOCK")

# V1 lock: remand/challenge recursion depth (docs/STATE_MACHINES.md, docs/APPEALS_AND_FINALITY.md).
_MAX_CHALLENGE_DEPTH = 1

# Oversized-input guards for the collections validated by _validate_clause_list /
# _validate_remedy_table (Stage 1 hardening pass, STAGE_1_VERIFICATION.md item 2). Chosen as
# generous-but-finite ceilings, not a business/product judgment about real warranty programs -
# only to prevent unbounded storage growth from a single write.
_MAX_CLAUSES_PER_KIND = 50
_MAX_REMEDY_ROWS = 50
_MAX_EVIDENCE_CATEGORIES = 20
_MAX_SHORT_LEN = 200
_MAX_TEXT_LEN = 4000
_REMEDY_ROW_KEYS = frozenset({"outcome", "clause_id", "remedy_kind", "remedy_value"})
_CLAUSE_ROW_KEYS = frozenset({"clause_id", "text"})

# Sanity ceiling only - not an actuarial/solvency judgment, just an overflow guard for u256
# arithmetic and for a single-warranty remedy relative to a pool. Ten million GEN.
_MAX_REMEDY_ATOMS = u256(10_000_000 * 10**18)


def _coerce_address(val) -> Address:
    """Accept Address, hex/base64 str, raw bytes, or a plain int (observed live on
    StudioNet for address-typed arguments - see docs/NETWORK_AND_SDK_VERIFICATION.md and
    this workspace's own prior incident on a sibling GenLayer project)."""
    if isinstance(val, Address):
        return val
    if isinstance(val, int):
        return Address(val.to_bytes(Address.SIZE, "big"))
    if isinstance(val, (bytes, bytearray)):
        return Address(bytes(val))
    return Address(val)


def _parse_iso_datetime(raw: str) -> u64:
    """gl.message_raw['datetime'] is documented as an ISO datetime string, not a unix
    integer (confirmed against the installed py-genlayer SDK source at
    genlayer/_internal/msg.py - see docs/NETWORK_AND_SDK_VERIFICATION.md). Convert once,
    here, to the u64 unix-second epoch every other Stage 1 timestamp field is stored as."""
    normalized = raw.replace("Z", "+00:00")
    parsed = datetime.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return u64(int(parsed.timestamp()))


def _now() -> u64:
    return _parse_iso_datetime(gl.message_raw["datetime"])


def _sender() -> Address:
    return gl.message.sender_address


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise gl.vm.UserError(message)


def _canonical_json(obj) -> str:
    """CLAUSE's definition of "canonical JSON" (Stage 1 hardening pass,
    STAGE_1_VERIFICATION.md item 2): a serialization is canonical here if and only if two
    semantically-equivalent inputs always produce byte-identical output. That requires more
    than `sort_keys=True` + compact separators (which only fixes *object key* order and
    whitespace) - it also requires the caller to have already normalized any *array* whose
    element order carries no meaning (an unordered ID set or a table keyed by a unique tuple)
    before this function ever sees it. This function performs the object-key/whitespace half
    of canonicalization; `_validate_clause_list` and `_validate_remedy_table` perform the
    array-ordering half (sorting `covered_clause_ids`/`excluded_clause_ids`/evidence
    categories lexicographically, and `remedy_table` rows by `(outcome, clause_id,
    remedy_kind, remedy_value)`) before their results are ever passed here. Free-text fields
    with meaningful order (e.g. `product_scope`, clause `text`) are never reordered - only
    fields that are logically sets/keyed-tables are. As long as every caller of this function
    passes already-order-normalized data for such fields, later code (Stage 2+) can compare
    two `fingerprint` values, or two `json.loads(...)` results, for exact/`==` equality to
    decide semantic equality - it will never need to re-parse and compare raw JSON text or
    tolerate reordering itself.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _fingerprint(obj) -> bytes:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).digest()


def _validate_hex_commitment(raw: str) -> bytes:
    """Product commitment must be a privacy-preserving hash (hash(serial + salt)), never a
    raw serial (docs/DATA_MODEL.md, docs/ARCHITECTURE.md anti-rewrite/privacy sections).
    Stage 1 enforces the *shape* of a commitment (32-byte hex digest); it cannot verify the
    holder actually knows a real serial+salt pair - that is a claim-time check in a later
    stage, not a registration-time one."""
    text = raw[2:] if raw.startswith("0x") or raw.startswith("0X") else raw
    _require(len(text) == 64, "malformed product commitment: expected 32-byte hex digest")
    try:
        return bytes.fromhex(text)
    except ValueError:
        raise gl.vm.UserError("malformed product commitment: not valid hex")


def _validate_clause_list(rows: list, kind: str, min_count: int) -> list:
    """Validates a covered/excluded clause list and returns the clause_ids in canonical
    (lexicographically sorted, deduplicated-by-construction) order - see `_canonical_json`'s
    docstring for why this matters for fingerprint stability. `min_count` lets covered clauses
    be required (a warranty must cover something) while excluded clauses stay optional (a
    program may legitimately have zero exclusions)."""
    _require(isinstance(rows, list), "clause list must be a list")
    _require(len(rows) >= min_count, f"at least {min_count} {kind.lower()} clause(s) required")
    _require(len(rows) <= _MAX_CLAUSES_PER_KIND, f"too many {kind.lower()} clauses (max {_MAX_CLAUSES_PER_KIND})")
    expected_prefix = "C-" if kind == CLAUSE_COVERED else "X-"
    ids = []
    for row in rows:
        _require(isinstance(row, dict), "malformed clause row: expected an object")
        _require(set(row.keys()) == _CLAUSE_ROW_KEYS, "clause row must have exactly the keys clause_id, text")
        clause_id = row["clause_id"]
        text = row["text"]
        _require(isinstance(clause_id, str) and 0 < len(clause_id) <= _MAX_SHORT_LEN, "clause_id must be a non-empty string within length limits")
        _require(clause_id.startswith(expected_prefix), f"clause_id must start with '{expected_prefix}'")
        _require(isinstance(text, str) and 0 < len(text) <= _MAX_TEXT_LEN, "clause text must be a non-empty string within length limits")
        _require(clause_id not in ids, "duplicate clause_id")
        ids.append(clause_id)
    return sorted(ids)


def _validate_remedy_table(rows: list, known_clause_ids: set) -> list:
    """Validates the remedy table and returns rows sorted by (outcome, clause_id,
    remedy_kind, remedy_value) - canonical order, so two semantically-equivalent tables
    submitted in different row order fingerprint identically (see `_canonical_json`)."""
    _require(isinstance(rows, list), "remedy_table must be a list")
    _require(len(rows) >= 1, "remedy_table must not be empty")
    _require(len(rows) <= _MAX_REMEDY_ROWS, f"too many remedy rows (max {_MAX_REMEDY_ROWS})")
    validated = []
    seen_pairs = set()
    for row in rows:
        _require(isinstance(row, dict), "malformed remedy row: expected an object")
        _require(set(row.keys()) == _REMEDY_ROW_KEYS, "remedy row must have exactly the keys outcome, clause_id, remedy_kind, remedy_value")
        outcome = row["outcome"]
        clause_id = row["clause_id"]
        remedy_kind = row["remedy_kind"]
        remedy_value = row["remedy_value"]
        _require(isinstance(outcome, str) and outcome in _OUTCOMES, "remedy row outcome must be one of " + str(_OUTCOMES))
        _require(isinstance(clause_id, str), "remedy row clause_id must be a string")
        _require(clause_id == "" or clause_id in known_clause_ids, "remedy row clause_id must reference a clause on this constitution")
        _require(isinstance(remedy_kind, str) and remedy_kind in _REMEDY_KINDS, "remedy row remedy_kind must be one of " + str(_REMEDY_KINDS))
        _require(isinstance(remedy_value, int) and not isinstance(remedy_value, bool) and remedy_value >= 0, "remedy_value must be a non-negative integer")
        if remedy_kind == REMEDY_PARTIAL_BPS:
            _require(remedy_value <= 10_000, "remedy_value for PARTIAL_BPS must be <= 10000")
        if remedy_kind == REMEDY_NONE:
            _require(remedy_value == 0, "remedy_value for NONE must be 0")

        # Wrong-clause-kind guard: a row may only cite a clause whose kind matches its own
        # outcome direction (COVERED -> C-*, NOT_COVERED -> X-*). Every other outcome
        # (INSUFFICIENT_EVIDENCE / EVIDENCE_UNAVAILABLE / INVALID_CLAIM / ACCEPTED_NO_CONTEST)
        # is procedural, not clause-specific, and must be outcome-level (clause_id == "").
        if clause_id != "":
            if outcome == "COVERED":
                _require(clause_id.startswith("C-"), "a COVERED remedy row's clause_id must reference a covered (C-*) clause")
            elif outcome == "NOT_COVERED":
                _require(clause_id.startswith("X-"), "a NOT_COVERED remedy row's clause_id must reference an excluded (X-*) clause")
            else:
                raise gl.vm.UserError(f"remedy rows for outcome {outcome} must be outcome-level (clause_id == '')")

        pair = (outcome, clause_id)
        _require(pair not in seen_pairs, "duplicate remedy row for the same (outcome, clause_id) pair")
        seen_pairs.add(pair)

        validated.append(
            {
                "outcome": outcome,
                "clause_id": clause_id,
                "remedy_kind": remedy_kind,
                "remedy_value": int(remedy_value),
            }
        )
    validated.sort(key=lambda r: (r["outcome"], r["clause_id"], r["remedy_kind"], r["remedy_value"]))
    return validated


@allow_storage
@dataclass
class WarrantyProgram:
    program_id: u32
    manufacturer: Address
    name: str
    status: str
    created_at: u64


@allow_storage
@dataclass
class WarrantyConstitution:
    constitution_id: u32
    program_id: u32
    version: str
    fingerprint: bytes
    product_scope: str
    coverage_calc: str
    # Frozen policy fields stored as canonical JSON strings rather than nested
    # DynArray[struct]/TreeMap[struct] collections. This departs from the literal typed
    # shapes sketched in docs/DATA_MODEL.md; reasoning and impact are recorded in
    # STAGE_1_VERIFICATION.md (deviation #1). Every JSON payload here is validated for
    # shape at write time (create_constitution) - a stored value is never untrusted.
    covered_clause_ids_json: str
    excluded_clause_ids_json: str
    acceptable_evidence_categories_json: str
    source_eligibility_policy: str
    claim_deadline_s: u64
    manufacturer_response_period_s: u64
    challenge_window_s: u64
    challenge_depth: u32
    insufficient_evidence_behavior: str
    unavailable_evidence_behavior: str
    expiry_cancellation_rules: str
    remedy_table_json: str
    frozen_at: u64
    is_frozen: bool


@allow_storage
@dataclass
class ClauseRecord:
    clause_id: str
    constitution_id: u32
    kind: str
    text: str


@allow_storage
@dataclass
class WarrantyPassport:
    warranty_id: u32
    program_id: u32
    manufacturer: Address
    holder: Address
    product_model_id: str
    product_commitment: bytes
    registered_at: u64
    coverage_start: u64
    coverage_end: u64
    constitution_id: u32
    constitution_version: str
    constitution_fingerprint: bytes
    source_policy_snapshot: str
    max_deterministic_remedy: u256
    reservation_id: u32
    status: str


@allow_storage
@dataclass
class WarrantyPool:
    pool_id: u32
    program_id: u32
    manufacturer: Address
    total_balance: u256
    reserved_liability: u256


@allow_storage
@dataclass
class Reservation:
    reservation_id: u32
    pool_id: u32
    warranty_id: u32
    amount: u256
    status: str
    created_at: u64
    released_at: u64


class ClauseProtocol(gl.Contract):
    programs: TreeMap[u32, WarrantyProgram]
    constitutions: TreeMap[u32, WarrantyConstitution]
    clauses: TreeMap[str, ClauseRecord]  # key: f"{constitution_id}:{clause_id}"
    clause_ids_by_constitution_json: TreeMap[u32, str]  # constitution_id -> json list[str]
    passports: TreeMap[u32, WarrantyPassport]
    pools: TreeMap[u32, WarrantyPool]  # keyed by program_id (one pool per program in V1)
    reservations: TreeMap[u32, Reservation]

    program_ids_json: str
    passport_ids_by_program_json: TreeMap[u32, str]

    next_program_id: u32
    next_constitution_id: u32
    next_passport_id: u32
    next_reservation_id: u32

    def __init__(self):
        self.program_ids_json = "[]"
        self.next_program_id = u32(1)
        self.next_constitution_id = u32(1)
        self.next_passport_id = u32(1)
        self.next_reservation_id = u32(1)

    # ------------------------------------------------------------------
    # WarrantyProgram
    # ------------------------------------------------------------------

    @gl.public.write
    def create_program(self, name: str) -> u32:
        _require(len(name) > 0, "program name must not be empty")
        program_id = self.next_program_id
        self.next_program_id = u32(program_id + 1)

        self.programs[program_id] = WarrantyProgram(
            program_id=program_id,
            manufacturer=_sender(),
            name=name,
            status=PROGRAM_ACTIVE,
            created_at=_now(),
        )
        self.pools[program_id] = WarrantyPool(
            pool_id=program_id,
            program_id=program_id,
            manufacturer=_sender(),
            total_balance=u256(0),
            reserved_liability=u256(0),
        )
        ids = json.loads(self.program_ids_json)
        ids.append(int(program_id))
        self.program_ids_json = _canonical_json(ids)
        self.passport_ids_by_program_json[program_id] = "[]"
        return program_id

    def _require_program(self, program_id: u32) -> WarrantyProgram:
        program = self.programs.get(program_id)
        _require(program is not None, "unknown program")
        return program

    def _require_manufacturer(self, program: WarrantyProgram) -> None:
        _require(
            _sender().as_bytes == program.manufacturer.as_bytes,
            "caller is not this program's manufacturer",
        )

    @gl.public.write
    def pause_program(self, program_id: u32) -> None:
        program = self._require_program(program_id)
        self._require_manufacturer(program)
        _require(program.status == PROGRAM_ACTIVE, "program is not ACTIVE")
        program.status = PROGRAM_PAUSED

    @gl.public.write
    def resume_program(self, program_id: u32) -> None:
        program = self._require_program(program_id)
        self._require_manufacturer(program)
        _require(program.status == PROGRAM_PAUSED, "program is not PAUSED")
        program.status = PROGRAM_ACTIVE

    @gl.public.write
    def retire_program(self, program_id: u32) -> None:
        program = self._require_program(program_id)
        self._require_manufacturer(program)
        _require(program.status != PROGRAM_RETIRED, "program is already RETIRED")
        program.status = PROGRAM_RETIRED

    @gl.public.view
    def get_program(self, program_id: u32) -> dict:
        program = self.programs.get(program_id)
        if program is None:
            return {}
        return {
            "program_id": int(program.program_id),
            "manufacturer": program.manufacturer.as_hex,
            "name": program.name,
            "status": program.status,
            "created_at": int(program.created_at),
        }

    @gl.public.view
    def list_program_ids(self) -> list:
        return json.loads(self.program_ids_json)

    # ------------------------------------------------------------------
    # WarrantyConstitution / Clause
    # ------------------------------------------------------------------

    @gl.public.write
    def create_constitution(
        self,
        program_id: u32,
        version: str,
        product_scope: str,
        coverage_calc: str,
        covered_clauses: list,   # [{"clause_id": "C-001", "text": "..."}, ...]
        excluded_clauses: list,  # [{"clause_id": "X-001", "text": "..."}, ...]
        acceptable_evidence_categories: list,  # [str, ...]
        source_eligibility_policy: str,
        claim_deadline_s: u64,
        manufacturer_response_period_s: u64,
        challenge_window_s: u64,
        challenge_depth: u32,
        insufficient_evidence_behavior: str,
        unavailable_evidence_behavior: str,
        expiry_cancellation_rules: str,
        remedy_table: list,  # [{"outcome": "...", "clause_id": "", "remedy_kind": "...", "remedy_value": int}, ...]
    ) -> u32:
        program = self._require_program(program_id)
        self._require_manufacturer(program)
        _require(program.status != PROGRAM_RETIRED, "program is RETIRED")
        _require(len(version) > 0, "version must not be empty")
        _require(int(challenge_depth) <= _MAX_CHALLENGE_DEPTH, "challenge_depth exceeds V1 maximum of 1")
        _require(
            insufficient_evidence_behavior in _EVIDENCE_GAP_BEHAVIORS,
            "insufficient_evidence_behavior must be one of " + str(_EVIDENCE_GAP_BEHAVIORS),
        )
        _require(
            unavailable_evidence_behavior in _EVIDENCE_GAP_BEHAVIORS,
            "unavailable_evidence_behavior must be one of " + str(_EVIDENCE_GAP_BEHAVIORS),
        )

        covered_ids = _validate_clause_list(covered_clauses, CLAUSE_COVERED, min_count=1)
        excluded_ids = _validate_clause_list(excluded_clauses, CLAUSE_EXCLUDED, min_count=0)
        all_ids = set(covered_ids) | set(excluded_ids)
        _require(len(all_ids) == len(covered_ids) + len(excluded_ids), "duplicate clause_id across covered/excluded")

        # Evidence categories are a set: validated, deduplicated, and returned in canonical
        # (sorted) order for the same fingerprint-stability reason as clause IDs above.
        _require(isinstance(acceptable_evidence_categories, list), "acceptable_evidence_categories must be a list")
        _require(len(acceptable_evidence_categories) >= 1, "at least one acceptable evidence category is required")
        _require(len(acceptable_evidence_categories) <= _MAX_EVIDENCE_CATEGORIES, f"too many evidence categories (max {_MAX_EVIDENCE_CATEGORIES})")
        seen_categories = set()
        for category in acceptable_evidence_categories:
            _require(isinstance(category, str) and 0 < len(category) <= _MAX_SHORT_LEN, "evidence category must be a non-empty string within length limits")
            _require(category not in seen_categories, "duplicate evidence category")
            seen_categories.add(category)
        canonical_categories = sorted(seen_categories)

        remedy_rows = _validate_remedy_table(remedy_table, all_ids)

        # No two constitutions under one program may share a (program_id, version) pair
        # (docs/WARRANTY_CONSTITUTION.md, "Versioning is explicit, not inferred").
        for existing in self.constitutions.values():
            if existing.program_id == program_id and existing.version == version:
                raise gl.vm.UserError("a constitution with this version already exists for this program")

        constitution_id = self.next_constitution_id
        self.next_constitution_id = u32(constitution_id + 1)

        frozen_fields = {
            "program_id": int(program_id),
            "version": version,
            "product_scope": product_scope,
            "coverage_calc": coverage_calc,
            "covered_clause_ids": covered_ids,
            "excluded_clause_ids": excluded_ids,
            "acceptable_evidence_categories": canonical_categories,
            "source_eligibility_policy": source_eligibility_policy,
            "claim_deadline_s": int(claim_deadline_s),
            "manufacturer_response_period_s": int(manufacturer_response_period_s),
            "challenge_window_s": int(challenge_window_s),
            "challenge_depth": int(challenge_depth),
            "insufficient_evidence_behavior": insufficient_evidence_behavior,
            "unavailable_evidence_behavior": unavailable_evidence_behavior,
            "expiry_cancellation_rules": expiry_cancellation_rules,
            "remedy_table": remedy_rows,
        }
        fingerprint = _fingerprint(frozen_fields)

        self.constitutions[constitution_id] = WarrantyConstitution(
            constitution_id=constitution_id,
            program_id=program_id,
            version=version,
            fingerprint=fingerprint,
            product_scope=product_scope,
            coverage_calc=coverage_calc,
            covered_clause_ids_json=_canonical_json(covered_ids),
            excluded_clause_ids_json=_canonical_json(excluded_ids),
            acceptable_evidence_categories_json=_canonical_json(canonical_categories),
            source_eligibility_policy=source_eligibility_policy,
            claim_deadline_s=claim_deadline_s,
            manufacturer_response_period_s=manufacturer_response_period_s,
            challenge_window_s=challenge_window_s,
            challenge_depth=challenge_depth,
            insufficient_evidence_behavior=insufficient_evidence_behavior,
            unavailable_evidence_behavior=unavailable_evidence_behavior,
            expiry_cancellation_rules=expiry_cancellation_rules,
            remedy_table_json=_canonical_json(remedy_rows),
            frozen_at=u64(0),
            is_frozen=False,
        )

        for row in covered_clauses:
            key = f"{int(constitution_id)}:{row['clause_id']}"
            self.clauses[key] = ClauseRecord(
                clause_id=row["clause_id"], constitution_id=constitution_id, kind=CLAUSE_COVERED, text=row["text"]
            )
        for row in excluded_clauses:
            key = f"{int(constitution_id)}:{row['clause_id']}"
            self.clauses[key] = ClauseRecord(
                clause_id=row["clause_id"], constitution_id=constitution_id, kind=CLAUSE_EXCLUDED, text=row["text"]
            )
        self.clause_ids_by_constitution_json[constitution_id] = _canonical_json(sorted(all_ids))

        return constitution_id

    @gl.public.view
    def get_constitution(self, constitution_id: u32) -> dict:
        c = self.constitutions.get(constitution_id)
        if c is None:
            return {}
        return {
            "constitution_id": int(c.constitution_id),
            "program_id": int(c.program_id),
            "version": c.version,
            "fingerprint": c.fingerprint.hex(),
            "product_scope": c.product_scope,
            "coverage_calc": c.coverage_calc,
            "covered_clause_ids": json.loads(c.covered_clause_ids_json),
            "excluded_clause_ids": json.loads(c.excluded_clause_ids_json),
            "acceptable_evidence_categories": json.loads(c.acceptable_evidence_categories_json),
            "source_eligibility_policy": c.source_eligibility_policy,
            "claim_deadline_s": int(c.claim_deadline_s),
            "manufacturer_response_period_s": int(c.manufacturer_response_period_s),
            "challenge_window_s": int(c.challenge_window_s),
            "challenge_depth": int(c.challenge_depth),
            "insufficient_evidence_behavior": c.insufficient_evidence_behavior,
            "unavailable_evidence_behavior": c.unavailable_evidence_behavior,
            "expiry_cancellation_rules": c.expiry_cancellation_rules,
            "remedy_table": json.loads(c.remedy_table_json),
            "frozen_at": int(c.frozen_at),
            "is_frozen": c.is_frozen,
        }

    @gl.public.view
    def get_clauses(self, constitution_id: u32) -> list:
        ids_json = self.clause_ids_by_constitution_json.get(constitution_id)
        if ids_json is None:
            return []
        out = []
        for clause_id in json.loads(ids_json):
            record = self.clauses.get(f"{int(constitution_id)}:{clause_id}")
            if record is not None:
                out.append(
                    {
                        "clause_id": record.clause_id,
                        "kind": record.kind,
                        "text": record.text,
                    }
                )
        return out

    # ------------------------------------------------------------------
    # WarrantyPool
    # ------------------------------------------------------------------

    def _require_pool(self, program_id: u32) -> WarrantyPool:
        pool = self.pools.get(program_id)
        _require(pool is not None, "unknown pool")
        return pool

    @gl.public.write.payable
    def fund_pool(self, program_id: u32) -> None:
        self._require_program(program_id)
        pool = self._require_pool(program_id)
        value = gl.message.value
        _require(value > 0, "send some GEN to fund the pool")
        pool.total_balance = u256(pool.total_balance + value)

    def _available_balance(self, pool: WarrantyPool) -> u256:
        return u256(pool.total_balance - pool.reserved_liability)

    @gl.public.write
    def withdraw_pool(self, program_id: u32, amount: u256) -> None:
        program = self._require_program(program_id)
        self._require_manufacturer(program)
        pool = self._require_pool(program_id)
        _require(amount > 0, "amount must be greater than 0")
        available = self._available_balance(pool)
        _require(amount <= available, "amount exceeds available (unreserved) balance")
        pool.total_balance = u256(pool.total_balance - amount)
        _require(pool.total_balance >= pool.reserved_liability, "accounting invariant violated")

        recipient = program.manufacturer
        _EOA(recipient).emit_transfer(value=u256(amount))

    @gl.public.view
    def get_pool(self, program_id: u32) -> dict:
        pool = self.pools.get(program_id)
        if pool is None:
            return {}
        return {
            "pool_id": int(pool.pool_id),
            "program_id": int(pool.program_id),
            "manufacturer": pool.manufacturer.as_hex,
            "total_balance": int(pool.total_balance),
            "reserved_liability": int(pool.reserved_liability),
            "available_balance": int(self._available_balance(pool)),
        }

    # ------------------------------------------------------------------
    # WarrantyPassport / Reservation
    # ------------------------------------------------------------------

    @gl.public.write
    def issue_warranty(
        self,
        program_id: u32,
        constitution_id: u32,
        holder,
        product_model_id: str,
        product_commitment_hex: str,
        coverage_start: u64,
        coverage_end: u64,
        max_deterministic_remedy: u256,
    ) -> u32:
        program = self._require_program(program_id)
        self._require_manufacturer(program)
        _require(program.status == PROGRAM_ACTIVE, "program is not ACTIVE")

        constitution = self.constitutions.get(constitution_id)
        _require(constitution is not None, "unknown constitution")
        _require(constitution.program_id == program_id, "constitution does not belong to this program")

        _require(len(product_model_id) > 0, "product_model_id must not be empty")
        commitment_bytes = _validate_hex_commitment(product_commitment_hex)

        _require(int(coverage_start) < int(coverage_end), "coverage_start must be before coverage_end")
        _require(int(coverage_end) - int(coverage_start) <= 100 * 365 * 24 * 3600, "coverage duration implausibly large (overflow guard)")

        _require(int(max_deterministic_remedy) > 0, "max_deterministic_remedy must be greater than 0")
        _require(max_deterministic_remedy <= _MAX_REMEDY_ATOMS, "max_deterministic_remedy exceeds sanity ceiling")

        pool = self._require_pool(program_id)
        available = self._available_balance(pool)
        _require(max_deterministic_remedy <= available, "insufficient pool capacity for this warranty")

        holder_address = _coerce_address(holder)

        warranty_id = self.next_passport_id
        self.next_passport_id = u32(warranty_id + 1)
        reservation_id = self.next_reservation_id
        self.next_reservation_id = u32(reservation_id + 1)

        now = _now()

        # Freeze the constitution the instant its first warranty issues - never a separate,
        # skippable step (docs/WARRANTY_CONSTITUTION.md).
        if not constitution.is_frozen:
            constitution.is_frozen = True
            constitution.frozen_at = now

        pool.reserved_liability = u256(pool.reserved_liability + max_deterministic_remedy)

        self.reservations[reservation_id] = Reservation(
            reservation_id=reservation_id,
            pool_id=program_id,
            warranty_id=warranty_id,
            amount=max_deterministic_remedy,
            status=RESERVATION_ACTIVE,
            created_at=now,
            released_at=u64(0),
        )

        self.passports[warranty_id] = WarrantyPassport(
            warranty_id=warranty_id,
            program_id=program_id,
            manufacturer=program.manufacturer,
            holder=holder_address,
            product_model_id=product_model_id,
            product_commitment=commitment_bytes,
            registered_at=now,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            constitution_id=constitution_id,
            constitution_version=constitution.version,
            constitution_fingerprint=constitution.fingerprint,
            source_policy_snapshot=constitution.source_eligibility_policy,
            max_deterministic_remedy=max_deterministic_remedy,
            reservation_id=reservation_id,
            status=PASSPORT_ACTIVE,
        )

        ids_json = self.passport_ids_by_program_json.get(program_id, "[]")
        ids = json.loads(ids_json)
        ids.append(int(warranty_id))
        self.passport_ids_by_program_json[program_id] = _canonical_json(ids)

        return warranty_id

    def _effective_status(self, passport: WarrantyPassport) -> str:
        """EXPIRED is derived at read time from coverage_end, never a separate mutation a
        manufacturer could forget to trigger (docs/STATE_MACHINES.md)."""
        if passport.status == PASSPORT_ACTIVE and _now() >= passport.coverage_end:
            return PASSPORT_EXPIRED
        return passport.status

    @gl.public.write
    def cancel_warranty(self, warranty_id: u32) -> None:
        passport = self.passports.get(warranty_id)
        _require(passport is not None, "unknown warranty")
        caller = _sender()
        _require(
            caller.as_bytes == passport.holder.as_bytes or caller.as_bytes == passport.manufacturer.as_bytes,
            "caller is neither the holder nor the manufacturer of this warranty",
        )
        _require(self._effective_status(passport) == PASSPORT_ACTIVE, "warranty is not ACTIVE")

        passport.status = PASSPORT_CANCELLED
        self._release_reservation(passport.reservation_id)

    @gl.public.write
    def release_expired_reservation(self, warranty_id: u32) -> None:
        """Permissionless cleanup - anyone may release capacity for an already
        expired/cancelled warranty (docs/ECONOMIC_INVARIANTS.md)."""
        passport = self.passports.get(warranty_id)
        _require(passport is not None, "unknown warranty")
        effective = self._effective_status(passport)
        _require(effective in (PASSPORT_EXPIRED, PASSPORT_CANCELLED), "warranty is not expired or cancelled")
        if passport.status == PASSPORT_ACTIVE and effective == PASSPORT_EXPIRED:
            passport.status = PASSPORT_EXPIRED
        self._release_reservation(passport.reservation_id)

    def _release_reservation(self, reservation_id: u32) -> None:
        reservation = self.reservations.get(reservation_id)
        _require(reservation is not None, "unknown reservation")
        _require(reservation.status == RESERVATION_ACTIVE, "reservation is not ACTIVE (already released or consumed)")

        pool = self.pools.get(reservation.pool_id)
        _require(pool is not None, "unknown pool for reservation")
        _require(pool.reserved_liability >= reservation.amount, "accounting invariant violated")

        pool.reserved_liability = u256(pool.reserved_liability - reservation.amount)
        reservation.status = RESERVATION_RELEASED
        reservation.released_at = _now()

    @gl.public.view
    def get_passport(self, warranty_id: u32) -> dict:
        passport = self.passports.get(warranty_id)
        if passport is None:
            return {}
        return {
            "warranty_id": int(passport.warranty_id),
            "program_id": int(passport.program_id),
            "manufacturer": passport.manufacturer.as_hex,
            "holder": passport.holder.as_hex,
            "product_model_id": passport.product_model_id,
            "product_commitment": passport.product_commitment.hex(),
            "registered_at": int(passport.registered_at),
            "coverage_start": int(passport.coverage_start),
            "coverage_end": int(passport.coverage_end),
            "constitution_id": int(passport.constitution_id),
            "constitution_version": passport.constitution_version,
            "constitution_fingerprint": passport.constitution_fingerprint.hex(),
            "max_deterministic_remedy": int(passport.max_deterministic_remedy),
            "reservation_id": int(passport.reservation_id),
            "status": self._effective_status(passport),
        }

    @gl.public.view
    def get_reservation(self, reservation_id: u32) -> dict:
        reservation = self.reservations.get(reservation_id)
        if reservation is None:
            return {}
        return {
            "reservation_id": int(reservation.reservation_id),
            "pool_id": int(reservation.pool_id),
            "warranty_id": int(reservation.warranty_id),
            "amount": int(reservation.amount),
            "status": reservation.status,
            "created_at": int(reservation.created_at),
            "released_at": int(reservation.released_at),
        }

    @gl.public.view
    def list_passport_ids(self, program_id: u32) -> list:
        ids_json = self.passport_ids_by_program_json.get(program_id)
        if ids_json is None:
            return []
        return json.loads(ids_json)

    @gl.public.view
    def now(self) -> u64:
        """Exposed for the frontend to display server-observed protocol time next to
        deadlines without needing its own clock skew handling."""
        return _now()


@gl.evm.contract_interface
class _EOA:
    class View:
        pass

    class Write:
        pass
