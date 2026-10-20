from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: smoke_sidecar.py <sidecar.exe>")
    executable = Path(sys.argv[1]).resolve()
    if not executable.is_file():
        raise SystemExit(f"sidecar not found: {executable}")

    commands = (
        "ping",
        "style_catalog",
        "form_catalog",
        "kedufine_form_catalog",
        "table_catalog",
        "picture_symbol_catalog",
        "shutdown",
    )
    payload = "".join(
        json.dumps({"id": index, "command": command, "args": {}}, ensure_ascii=False)
        + "\n"
        for index, command in enumerate(commands, start=1)
    )
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    with tempfile.TemporaryDirectory(prefix="jb-hwp-sidecar-smoke-") as app_data:
        environment["APPDATA"] = app_data
        completed = subprocess.run(
            [str(executable)],
            input=payload,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=90,
            check=False,
            env=environment,
        )
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0:
        raise RuntimeError(
            f"sidecar exited with {completed.returncode}: {completed.stderr[-2000:]}"
        )
    if len(responses) != len(commands):
        raise RuntimeError(f"expected {len(commands)} responses, received {len(responses)}")
    if not all(response.get("ok") for response in responses):
        failures = [
            f"{command}: {response.get('message', '')}"
            for command, response in zip(commands, responses)
            if not response.get("ok")
        ]
        raise RuntimeError(f"sidecar command failed: {'; '.join(failures)}")

    by_command = dict(zip(commands, responses))
    styles = by_command["style_catalog"]["data"]["items"]
    forms = by_command["form_catalog"]["data"]["items"]
    kedufine_forms = by_command["kedufine_form_catalog"]["data"]["items"]
    tables = by_command["table_catalog"]["data"]["items"]
    groups = by_command["picture_symbol_catalog"]["data"]["groups"]
    if len(styles) < 7 or len(forms) < 4 or len(kedufine_forms) < 11 or len(tables) != 20 or len(groups) < 3:
        raise RuntimeError("bundled catalogs are incomplete")
    if sum(item.get("category") == "internal" for item in kedufine_forms) != 3:
        raise RuntimeError("internal kedufine form category is incomplete")
    if sum(item.get("category") == "outgoing" for item in kedufine_forms) != 8:
        raise RuntimeError("outgoing kedufine form category is incomplete")
    if any(not item.get("body") or "file_path" in item for item in kedufine_forms):
        raise RuntimeError("kedufine forms must contain body text, not HWP files")
    if max((len(group.get("items", [])) for group in groups), default=0) < 54:
        raise RuntimeError("bundled picture symbols are incomplete")

    print(
        "sidecar smoke ok: "
        f"styles={len(styles)} forms={len(forms)} kedufine_forms={len(kedufine_forms)} tables={len(tables)} "
        f"symbol_groups={len(groups)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
