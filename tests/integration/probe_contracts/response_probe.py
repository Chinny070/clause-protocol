# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json


class ResponseProbe(gl.Contract):
    get_out: str
    render_out: str

    def __init__(self):
        self.get_out = ""
        self.render_out = ""

    @gl.public.write
    def probe_get(self, url: str) -> None:
        def leader():
            try:
                r = gl.nondet.web.get(url)
                return json.dumps({
                    "ok": True,
                    "type": type(r).__name__,
                    "module": type(r).__module__,
                    "public_attrs": sorted(k for k in dir(r) if not k.startswith("_")),
                    "has_status": hasattr(r, "status"),
                    "has_status_code": hasattr(r, "status_code"),
                    "status": getattr(r, "status", None),
                    "status_type": type(getattr(r, "status", None)).__name__,
                    "body_type": type(r.body).__name__,
                    "body_len": len(r.body or b""),
                    "body_head": (r.body or b"")[:80].decode("utf-8", errors="replace"),
                    "header_count": len(r.headers),
                }, sort_keys=True)
            except Exception as e:
                return json.dumps({"ok": False, "error": repr(e)}, sort_keys=True)

        def validator(res):
            return isinstance(res, gl.vm.Return)

        self.get_out = gl.vm.run_nondet_unsafe(leader, validator)

    @gl.public.write
    def probe_render(self, url: str) -> None:
        def leader():
            try:
                t = gl.nondet.web.render(url, mode="text")
                return json.dumps({"ok": True, "type": type(t).__name__, "len": len(t), "head": t[:120]}, sort_keys=True)
            except Exception as e:
                return json.dumps({"ok": False, "error": repr(e)}, sort_keys=True)

        def validator(res):
            return isinstance(res, gl.vm.Return)

        self.render_out = gl.vm.run_nondet_unsafe(leader, validator)

    @gl.public.view
    def read_get(self) -> str:
        return self.get_out

    @gl.public.view
    def read_render(self) -> str:
        return self.render_out
