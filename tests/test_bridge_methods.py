"""The frontend keeps its own copy of the bridge's shape. Keep them equal.

pywebview sometimes leaves `window.pywebview.api` empty on Windows, so the
frontend can rebuild it from a hardcoded list. That list is only correct while
it matches this class, and a silent mismatch would produce methods that call
nothing, so compare them here rather than trusting a comment.
"""

import inspect
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool.api_bridge import Api  # noqa: E402

API_TS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "api.ts"


def python_methods() -> list[dict]:
    api = Api()
    out = []
    for name in sorted(n for n in dir(api) if not n.startswith("_")):
        attr = getattr(api, name)
        if inspect.ismethod(attr) or inspect.isfunction(attr):
            out.append({"func": name, "params": list(inspect.signature(attr).parameters)})
    return out


def typescript_methods() -> list[dict]:
    source = API_TS.read_text(encoding="utf-8")
    block = re.search(r"const BRIDGE_METHODS = \[(.*?)\n\]", source, re.S)
    assert block, "BRIDGE_METHODS not found in api.ts"
    out = []
    for func, params in re.findall(
        r'\{\s*func:\s*"([^"]+)",\s*params:\s*\[([^\]]*)\]', block.group(1)
    ):
        names = [p.strip().strip('"') for p in params.split(",") if p.strip()]
        out.append({"func": func, "params": names})
    return sorted(out, key=lambda d: d["func"])


def test_the_frontend_list_matches_the_python_class():
    expected, actual = python_methods(), typescript_methods()
    assert actual == expected, (
        "frontend/src/lib/api.ts BRIDGE_METHODS is out of date.\n"
        f"expected: {json.dumps(expected, indent=2)}\n"
        f"found:    {json.dumps(actual, indent=2)}"
    )


def test_the_probe_the_frontend_waits_on_is_a_real_method():
    source = API_TS.read_text(encoding="utf-8")
    probe = re.search(r'const PROBE = "([^"]+)"', source)
    assert probe, "PROBE not found"
    assert probe.group(1) in {m["func"] for m in python_methods()}
