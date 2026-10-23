"""Print / save the evaluation environment (tool versions) as JSON evidence.

    python scripts/collect_environment.py                      # print
    python scripts/collect_environment.py -o reports/evidence/environment.json
    python scripts/collect_environment.py --garak-python ~/DAY_4/.venv-garak/bin/python
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a4sec.config import resolve_endpoint  # noqa: E402
from a4sec.evidence import collect_environment  # noqa: E402
from a4sec.ollama_client import OllamaClient, OllamaError  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--output", type=Path, help="write JSON here")
    parser.add_argument("--endpoint", default=None, help="Ollama URL")
    parser.add_argument("--garak-python", default=None, help="python of the Garak virtualenv")
    args = parser.parse_args()

    env = collect_environment(garak_python=args.garak_python)
    endpoint = resolve_endpoint(args.endpoint)
    env["ollama_endpoint"] = endpoint
    try:
        with OllamaClient(endpoint, timeout=10) as client:
            env["ollama_server"] = client.version()
            env["ollama_models"] = client.list_models()
    except OllamaError as exc:
        env["ollama_server"] = f"unreachable: {exc}"
        env["ollama_models"] = []

    text = json.dumps(env, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"environment -> {args.output}")
    print(text)


if __name__ == "__main__":
    main()
