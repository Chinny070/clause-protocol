"""Shared test shims for the gltest direct runner on Windows.

Two harness gaps, neither related to CLAUSE contract correctness. Both are reused verbatim
from this workspace's own prior GenLayer projects (Protocol Court / AgentCourt), which
already root-caused them against the same installed genlayer-test==0.29.2 on Windows:

1. gltest 0.29.2's `loader._inject_message_to_fd0` unlinks a tempfile while its
   fd is still dup2'd onto stdin -> PermissionError (WinError 32) on Windows.
   We tolerate that single failure; the OS reclaims the file on exit.

2. The direct runner injects `gl.message_raw["datetime"]` once at deploy and
   `VMContext.warp()` does not reliably refresh the live `genlayer.gl.message_raw`
   object on this installed version. CLAUSE reads on-chain time exclusively via
   `gl.message_raw["datetime"]` (the correct, consensus-safe source per
   docs/NETWORK_AND_SDK_VERIFICATION.md), so we make `warp()` also poke that field.
"""

from __future__ import annotations

import os
import sys
import tempfile

# --- shim 1: tolerant unlink on Windows ------------------------------------
if sys.platform.startswith("win"):
    _real_unlink = os.unlink
    _tmpdir = os.path.realpath(tempfile.gettempdir())

    def _tolerant_unlink(path, *args, **kwargs):
        try:
            return _real_unlink(path, *args, **kwargs)
        except PermissionError:
            try:
                if os.path.realpath(os.path.dirname(str(path))) == _tmpdir:
                    return None
            except Exception:
                pass
            raise

    os.unlink = _tolerant_unlink

# --- shim 2: warp() also updates gl.message_raw["datetime"] ----------------
from gltest.direct.vm import VMContext as _VMContext  # noqa: E402

_real_warp = _VMContext.warp


def _warp_with_datetime(self, timestamp: str) -> None:
    _real_warp(self, timestamp)
    gl_mod = sys.modules.get("genlayer.gl")
    if gl_mod is not None and getattr(gl_mod, "message_raw", None) is not None:
        try:
            gl_mod.message_raw["datetime"] = timestamp
        except Exception:
            pass


_VMContext.warp = _warp_with_datetime
