"""Generates the machine-derived parts of docs/FRONTEND_CONTRACT_INTERFACE.md from contracts/clause_protocol.py
(AST only; nothing is executed). Usage: python scripts/gen_frontend_interface.py [--check]
--check exits non-zero if the committed doc is out of sync (also enforced by a test)."""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "contracts" / "clause_protocol.py"
DOC = ROOT / "docs" / "FRONTEND_CONTRACT_INTERFACE.md"
BEGIN = "<!-- BEGIN GENERATED -->"
END = "<!-- END GENERATED -->"


def dec_kind(fn):
    kinds = []
    for d in fn.decorator_list:
        text = ast.unparse(d)
        if text.startswith("gl.public."):
            kinds.append(text[len("gl.public."):])
    return ".".join(kinds) if kinds else None


def dict_keys(node):
    """Keys of a dict literal; nested dict / list-of-dict values become nested structures."""
    if isinstance(node, ast.Dict):
        out = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant):
                out[k.value] = dict_keys(v)
        return out
    if isinstance(node, (ast.List, ast.ListComp)):
        inner = node.elt if isinstance(node, ast.ListComp) else (node.elts[0] if node.elts else None)
        if isinstance(inner, ast.Dict):
            return [dict_keys(inner)]
    return None


def render_keys(struct, indent=0):
    lines = []
    pad = "  " * indent
    for k, v in struct.items():
        if isinstance(v, dict):
            lines.append(f"{pad}- `{k}`: object")
            lines.extend(render_keys(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{pad}- `{k}`: list of objects")
            lines.extend(render_keys(v[0], indent + 1))
        else:
            lines.append(f"{pad}- `{k}`")
    return lines


def messages(fn, private=None, _seen=None):
    """Error messages in `fn` and, transitively, in the private `self._helper()` methods it calls."""
    private = private or {}
    _seen = _seen if _seen is not None else set()
    msgs = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)                 and n.func.value.id == "self" and n.func.attr in private and n.func.attr not in _seen:
            _seen.add(n.func.attr)
            msgs.extend(messages(private[n.func.attr], private, _seen))
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            name = ast.unparse(n.func)
            if name == "_require" and len(n.args) >= 2:
                a = n.args[1]
                if isinstance(a, ast.Constant):
                    msgs.append(a.value)
                elif isinstance(a, ast.JoinedStr):
                    msgs.append(re.sub(r"\{[^}]*\}", "{...}", ast.unparse(a)[2:-1]))
            if name == "gl.vm.UserError" and n.args and isinstance(n.args[0], ast.Constant):
                msgs.append(n.args[0].value)
    seen, out = set(), []
    for m in msgs:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def generate():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ClauseProtocol")
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and dec_kind(n)]
    private = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef) and not dec_kind(n) and n.name.startswith("_")}
    views = [m for m in methods if dec_kind(m) == "view"]
    writes = [m for m in methods if dec_kind(m) != "view"]
    payable = [m for m in methods if "payable" in (dec_kind(m) or "")]
    out = []
    out.append(f"Method counts: **{len(methods)} public methods = {len(views)} view + {len(writes)} write** "
               f"({len(payable)} payable: {', '.join('`' + m.name + '`' for m in payable)}).\n")

    def sig(m):
        args = []
        for a in m.args.args[1:]:
            ann = ast.unparse(a.annotation) if a.annotation is not None else "untyped"
            args.append(f"{a.arg}: {ann}")
        ret = ast.unparse(m.returns) if m.returns is not None else "None"
        return f"{m.name}({', '.join(args)}) -> {ret}"

    out.append("### Write methods\n")
    for m in writes:
        out.append(f"#### `{sig(m)}`")
        out.append(f"- kind: {dec_kind(m)}")
        doc = ast.get_docstring(m)
        if doc:
            out.append("- note: " + " ".join(doc.split())[:400])
        errs = messages(m, private)
        if errs:
            out.append("- errors (method body and its internal helpers; module-level validators add more, e.g. clause/remedy/model-output checks):")
            out.extend(f"  - `{e}`" for e in errs)
        out.append("")
    out.append("### View methods\n")
    for m in views:
        out.append(f"#### `{sig(m)}`")
        rets = [n for n in ast.walk(m) if isinstance(n, ast.Return) and n.value is not None]
        struct = None
        delegated = None
        for r in rets:
            if isinstance(r.value, ast.Dict) and r.value.keys:
                struct = dict_keys(r.value)
            elif isinstance(r.value, ast.Call) and ast.unparse(r.value.func).startswith("self.get_"):
                delegated = ast.unparse(r.value.func)[len("self."):]
        if struct:
            out.append("- returns object with keys (empty object `{}` when the id is unknown):")
            out.extend("  " + line for line in render_keys(struct))
        elif delegated:
            out.append(f"- returns the same structure as `{delegated}` (empty object `{{}}` when none)")
        elif rets:
            out.append("- returns: " + ast.unparse(rets[-1].value)[:120])
        out.append("")

    out.append("### Enumerations (module constants)\n")
    consts = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            name = n.targets[0].id
            try:
                val = ast.literal_eval(n.value)
            except Exception:
                continue
            consts[name] = val
    groups = [
        ("Program status", "PROGRAM_"), ("Passport status", "PASSPORT_"), ("Reservation status", "RESERVATION_"),
        ("Clause kind", "CLAUSE_"), ("Remedy kind", "REMEDY_"), ("Claim status", "CLAIM_"), ("Manufacturer response", "RESPONSE_"),
        ("Evidence eligibility", "EVIDENCE_"), ("Retrieval status", "RETRIEVAL_"), ("Challenge status", "CHALLENGE_"),
        ("Challenge result", "RESULT_"),
    ]
    for title, prefix in groups:
        vals = [f"`{v}`" if v != "" else '`""` (pending)' for k, v in consts.items() if k.startswith(prefix) and isinstance(v, str)]
        if vals:
            out.append(f"- **{title}**: " + ", ".join(vals))
    for title, name in (("Outcomes (adjudication / final)", "_OUTCOMES"), ("Challenge grounds", "_CHALLENGE_GROUNDS"),
                        ("Tri-state findings", "_TRI"), ("Challenge model decisions", "_CHALLENGE_DECISIONS"),
                        ("Citation timestamp fields", "_TIMESTAMP_FIELDS"), ("Evidence-gap behaviours", "_EVIDENCE_GAP_BEHAVIORS")):
        if name in consts:
            out.append(f"- **{title}**: " + ", ".join(f"`{v}`" for v in consts[name]))
    out.append("")
    out.append("### Limits\n")
    for k in ("_MAX_ADJUDICABLE_EVIDENCE", "_MAX_CLAUSES_PER_KIND", "_MAX_REMEDY_ROWS", "_MAX_EVIDENCE_CATEGORIES", "_MAX_SHORT_LEN",
              "_MAX_TEXT_LEN", "_MAX_URL_LEN", "_MAX_EXTRACT_LEN", "_MAX_RATIONALE_LEN", "_MAX_EXPLANATION_LEN", "_MAX_REMAND_ISSUE_LEN",
              "_MAX_CITATIONS", "_MAX_CHALLENGE_DEPTH"):
        if k in consts:
            out.append(f"- `{k}` = {consts[k]}")
    return "\n".join(out) + "\n"


def main():
    body = generate()
    doc = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
    head, rest = doc.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    new = head + BEGIN + "\n" + body + END + tail
    if "--check" in sys.argv:
        if new != doc:
            print("FRONTEND_CONTRACT_INTERFACE.md is out of sync with the contract")
            sys.exit(1)
        print("in sync")
        return
    DOC.write_text(new, encoding="utf-8", newline="\n")
    print("written", DOC)


if __name__ == "__main__":
    main()
