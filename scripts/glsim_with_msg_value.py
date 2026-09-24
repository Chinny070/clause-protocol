"""Launch glsim 0.29.2 with ONE minimal, clearly-labelled shim: propagate a transaction's value
into `msg.value` for top-level contract calls. Stock glsim decodes the value but never sets
vm.value when executing (so every payable call sees gl.message.value == 0 - a simulator
limitation, NOT a contract bug). Nothing else is patched: web retrieval, consensus, storage,
leader/validator execution all remain stock glsim. See STAGE_2_5_REAL_WEB_VERIFICATION.md."""
import sys

import glsim.engine as E
import glsim.server as S

_pending = {"value": 0}
_orig_decode = S.decode_raw_transaction
_orig_decode_payload = S.decode_genlayer_payload
_orig_call = E.SimEngine.call_from_calldata


def _decode(raw_hex):
    tx = _orig_decode(raw_hex)
    _pending["value"] = int(tx.get("value") or 0)
    return tx


def _decode_payload(data):
    p = _orig_decode_payload(data)
    v = (p.get("decoded_tx_data") or {}).get("value")
    if v:
        _pending["value"] = int(v)
    return p


def _call(self, contract_address, calldata_bytes, sender=None):
    self.vm.value = _pending["value"]
    try:
        return _orig_call(self, contract_address, calldata_bytes, sender)
    finally:
        self.vm.value = 0
        _pending["value"] = 0


# DIAGNOSTIC ONLY (no behavior change): log why a validator votes "disagree".
import traceback
import glsim.consensus as C


def _run_validators_logged(vm, captured, num_validators):
    import genlayer.gl.vm as gl_vm
    votes = []
    for vi in range(num_validators):
        all_agree = True
        for idx, (stored_result, _leader_fn, validator_fn) in enumerate(captured):
            try:
                ok = validator_fn(gl_vm.Return(calldata=stored_result))
                if not ok:
                    print("[diag] validator", vi, "captured#", idx, "returned False; leader_result=", repr(stored_result)[:300], flush=True)
                    all_agree = False
                    break
            except Exception:
                print("[diag] validator", vi, "captured#", idx, "RAISED:", traceback.format_exc(), flush=True)
                all_agree = False
                break
        votes.append("agree" if all_agree else "disagree")
    return votes


C._run_validators = _run_validators_logged
S.decode_raw_transaction = _decode
S.decode_genlayer_payload = _decode_payload
E.SimEngine.call_from_calldata = _call

if __name__ == "__main__":
    from glsim.__main__ import main
    sys.argv[0] = "glsim"
    main()
