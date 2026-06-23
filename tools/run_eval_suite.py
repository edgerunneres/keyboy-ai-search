from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keyboy.agentic import AgenticKeyBoySystem
from keyboy.eval_suite import load_eval_tasks, score_result, summarize_scores


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the KeyBoy 1.1 lightweight evaluation suite.")
    parser.add_argument("--max-tasks", type=int, default=5)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()

    tasks = load_eval_tasks()[: max(1, min(args.max_tasks, 30))]
    system = AgenticKeyBoySystem()
    rows = []
    for task in tasks:
        result = system.research(task["query"], online=args.online, include_local=True, limit=args.limit)
        result_dict = result.to_dict()
        rows.append({"task": task, "scores": score_result(result_dict), "result": result_dict})
        print(f"{task['id']} {task['category']} done")

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "online": args.online,
        "summary": summarize_scores(rows),
        "rows": rows,
    }
    out_dir = ROOT / "data" / "eval_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    with out_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
