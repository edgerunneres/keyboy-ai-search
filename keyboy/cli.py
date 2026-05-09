from __future__ import annotations

import argparse
import json

from .agents import KeyBoySystem


def main() -> None:
    parser = argparse.ArgumentParser(description="KeyBoy command line tools")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--mode", default="hybrid", choices=["hybrid", "lexical", "semantic"])

    sub.add_parser("evaluate")

    args = parser.parse_args()
    system = KeyBoySystem()
    system.bootstrap()

    if args.command == "search":
        response = system.search(args.query, mode=args.mode, limit=5)
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "evaluate":
        print(json.dumps(system.eval_metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

