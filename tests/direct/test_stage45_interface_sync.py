"""Stage 4.5 freeze guard: the ABI inventory in docs/FRONTEND_CONTRACT_INTERFACE.md must match the contract."""
import subprocess
import sys


def test_frontend_interface_doc_is_in_sync_with_the_contract():
    r = subprocess.run([sys.executable, "scripts/gen_frontend_interface.py", "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
