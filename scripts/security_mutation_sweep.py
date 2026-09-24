"""Stage 6A independent effectiveness check of the security tests.

For each security-critical guard in the release candidate: temporarily disable it in the contract source, run the
tests that are supposed to protect it, and require that AT LEAST ONE FAILS (a surviving mutation means the guard is
untested). The audited file is restored (byte-for-byte, SHA-256 verified) after every mutation and at exit.
Usage: python scripts/security_mutation_sweep.py   (takes ~10 minutes; do not run other tests concurrently)"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "clause_protocol.py"
AUDITED = "2cae6e200ee82b747ebe89bf3e423768fca545ada840348a8f104d9053c07851"

MUTATIONS = [
    ("authorization: only the holder may file a claim", 'passport.holder.as_bytes, "caller is not this warranty\'s holder")', 'passport.holder.as_bytes or True, "x")', ["tests/direct/test_stage2_claims.py"]),
    ("authorization: only the manufacturer may respond", 'claim.manufacturer.as_bytes, "caller is not this claim\'s manufacturer")', 'claim.manufacturer.as_bytes or True, "x")', ["tests/direct/test_stage2_response.py"]),
    ("evidence immutability: no submission after freeze", '        _require(claim.evidence_frozen_at == 0, "evidence for this claim is already frozen")\n\n        constitution = self.constitutions[claim.constitution_id]\n        _require(isinstance(category', '        constitution = self.constitutions[claim.constitution_id]\n        _require(isinstance(category', ["tests/direct/test_stage2_freeze_and_fingerprint.py"]),
    ("source eligibility: exact host policy", 'is_eligible = parsed.scheme == _ALLOWED_SCHEME and _host_allowed(parsed.hostname, policy_hosts)', 'is_eligible = parsed.scheme == _ALLOWED_SCHEME', ["tests/direct/test_stage2_source_eligibility.py"]),
    ("evidence cap: 10 adjudicable records", 'prior_eligible < _MAX_ADJUDICABLE_EVIDENCE,', 'True,', ["tests/direct/test_stage3_5_hardening.py"]),
    ("adjudication validation: covered clauses must be targeted", 'if not isinstance(cid, str) or cid not in ctx["targeted"]:', 'if not isinstance(cid, str):', ["tests/direct/test_stage3_malformed_output.py"]),
    ("adjudication: one adjudication per claim", '_require(self.adjudication_id_by_claim.get(claim_id) is None, "claim has already been adjudicated")', 'pass', ["tests/direct/test_stage3_adjudication.py"]),
    ("challenge validation: corrections limited to the ground's fields", 'if not isinstance(key, str) or key not in allowed:', 'if not isinstance(key, str):', ["tests/direct/test_stage4_challenge.py", "tests/direct/test_stage45_freeze.py"]),
    ("challenge: window closes exactly at the frozen deadline", '_require(now <= original.challenge_window_closes_at, "challenge window has closed")', '_require(now < original.challenge_window_closes_at, "challenge window has closed")', ["tests/direct/test_stage4_challenge.py"]),
    ("remedy completeness at constitution creation", '        _check_remedy_completeness(remedy_rows, covered_ids)\n', '        pass\n', ["tests/direct/test_stage45_freeze.py"]),
    ("reservation accounting: settlement capped by remaining reservation", 'payable = min(int(fd.remedy_amount), remaining)', 'payable = int(fd.remedy_amount)', ["tests/direct/test_stage4_economics.py"]),
    ("withdrawal: only the recorded recipient", '_require(_sender().as_bytes == fd.recipient.as_bytes, "caller is not the settlement recipient")', 'pass', ["tests/direct/test_stage4_economics.py"]),
    ("double withdrawal guard", '_require(fd.withdrawn_at == 0, "settlement already withdrawn")', 'pass', ["tests/direct/test_stage4_economics.py", "tests/direct/test_stage4_lifecycle.py"]),
    ("claim deadline boundary", 'now <= int(passport.coverage_end) + int(constitution.claim_deadline_s),', 'True,', ["tests/direct/test_stage2_claims.py", "tests/direct/test_temporal.py"]),
    ("response deadline boundary", '_require(_now() <= claim.response_deadline, "response window has closed")', 'pass', ["tests/direct/test_stage2_response.py"]),
    ("reservation release waits for the claim-deadline grace", '_now() > int(passport.coverage_end) + int(governing.claim_deadline_s),', 'True,', ["tests/direct/test_stage45_freeze.py"]),
    ("reservation release blocked by unsettled claims", '_require(self.claims[u32(raw)].status == CLAIM_SETTLED, "warranty has an unsettled claim")', 'pass', ["tests/direct/test_stage45_freeze.py"]),
    ("no finalize while the challenge window is open", '_require(now > auth.challenge_window_closes_at, "application challenge window is still open")', 'pass', ["tests/direct/test_stage4_lifecycle.py"]),
    ("cancellation: only the holder may cancel an issued warranty", '_require(_sender().as_bytes == passport.holder.as_bytes, "caller is not this warranty\'s holder: only the holder can cancel an issued warranty")', 'pass', ["tests/direct/test_stage6a1_cancellation.py", "tests/direct/test_authorization.py"]),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    assert sha(CONTRACT) == AUDITED, "contract is not the audited release candidate"
    original = CONTRACT.read_bytes()
    results = []
    try:
        for name, old, new, tests in MUTATIONS:
            text = original.decode("utf-8")
            if text.count(old) != 1:
                results.append({"guard": name, "result": "MUTATION-NOT-APPLICABLE", "detail": f"pattern occurs {text.count(old)} times"})
                print("N/A ", name)
                continue
            CONTRACT.write_bytes(text.replace(old, new).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONUTF8": "1"})
            killed = r.returncode != 0
            CONTRACT.write_bytes(original)
            results.append({"guard": name, "tests": tests, "result": "KILLED" if killed else "SURVIVED"})
            print("KILLED  " if killed else "SURVIVED", name, flush=True)
    finally:
        CONTRACT.write_bytes(original)
    assert sha(CONTRACT) == AUDITED, "contract not restored!"
    (ROOT / "docs" / "RELEASE_MUTATION_SWEEP.json").write_text(json.dumps({"audited_sha256": AUDITED, "results": results}, indent=2), encoding="utf-8")
    survived = [r for r in results if r["result"] != "KILLED"]
    print(f"\n{len(results) - len(survived)}/{len(results)} guards killed; audited file restored (sha ok)")
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
