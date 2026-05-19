from __future__ import annotations

import argparse
import json

from .agentic import AgenticKeyBoySystem
from .agents import KeyBoySystem


def main() -> None:
    parser = argparse.ArgumentParser(description="KeyBoy command line tools")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--mode", default="hybrid", choices=["hybrid", "lexical", "semantic"])

    research = sub.add_parser("research")
    research.add_argument("query")
    research.add_argument("--offline", action="store_true", help="Skip online source APIs and use local corpus only")

    sub.add_parser("evaluate")

    args = parser.parse_args()
    system = KeyBoySystem()
    system.bootstrap()

    if args.command == "search":
        response = system.search(args.query, mode=args.mode, limit=5)
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "research":
        agentic = AgenticKeyBoySystem()
        response = agentic.research(args.query, online=not args.offline, include_local=True, limit=8)
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "evaluate":
        print(json.dumps(system.eval_metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
