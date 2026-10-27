#!/usr/bin/env python3
"""Check the translations in locales/*.json against the texts used in the code.

Reports missing entries, unused entries and placeholder mismatches ({name}, {size:.1f} …).
With --template it writes locales/_template.json (all English texts) for new translations.

Usage:  python tools/check_locales.py [--template]
"""
import ast
import json
import re
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "wda_gui.py", ROOT / "wda_tool.py"]


def msgids():
    ids = []
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "T" and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                ids.append(node.args[0].value)
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "ERROR_CODES":
                ids += [v.value for v in node.value.values]        # translated via T(variable)
    ids.append("unknown")
    return list(dict.fromkeys(ids))


def fields(s):
    return sorted(f for _, f, spec, _ in string.Formatter().parse(s) if f is not None)


def main():
    ids = msgids()
    if "--template" in sys.argv:
        (ROOT / "locales" / "_template.json").write_text(
            json.dumps({i: "" for i in ids}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"locales/_template.json: {len(ids)} texts")
    ok = True
    for f in sorted((ROOT / "locales").glob("*.json")):
        if f.name.startswith("_"):
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        fallback = data.pop("_fallback", None)
        problems = []
        if not fallback:
            missing = [i for i in ids if i not in data]
            if missing:
                problems.append(f"{len(missing)} missing, e.g. {missing[0]!r}")
        unused = [k for k in data if k not in ids]
        if unused:
            problems.append(f"{len(unused)} unused, e.g. {unused[0]!r}")
        for k, v in data.items():
            if k in ids and fields(k) != fields(v):
                problems.append(f"placeholders differ: {k!r} -> {v!r}")
        status = "OK" if not problems else "; ".join(problems[:4])
        ok &= not problems
        # kein "→": die Windows-Konsole (cp1252/cp850) kann es nicht ausgeben
        print(f"{f.name:12s} {len(data):4d} entries{' (-> ' + fallback + ')' if fallback else ''}  {status}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
