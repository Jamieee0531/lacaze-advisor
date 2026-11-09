"""Export the v0.2.3 evaluation runs as stage-by-stage replays for the workbench.

Usage: uv run python scripts/export_demo_replays.py RUN_DIR [RUN_DIR ...]

Writes data/demo/replays.json. Each case keeps its input, the final result (without the raw model
trace), and per stage the payload the model received, its output, and how many retries it took.
"""

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "demo" / "replays.json"


def stage_record(messages: list[dict]) -> dict:
    parts = [p for m in messages for p in m["parts"]]
    prompt = next(p["content"] for p in parts if p["part_kind"] == "user-prompt")
    answer = [p["content"] for p in parts if p["part_kind"] == "text"][-1]
    retries = sum(p["part_kind"] == "retry-feedback" for p in parts)
    return {"input": json.loads(prompt), "output": json.loads(answer), "retries": retries}


def replay(record: dict) -> dict:
    result = dict(record["result"])
    trace = result.pop("trace")
    return {
        "input": record["input"],
        "result": result,
        "stages": {stage: stage_record(messages) for stage, messages in trace.items()},
    }


def main(run_dirs: list[str]) -> None:
    replays = {}
    for run in map(Path, run_dirs):
        for path in sorted(run.glob("C*.json")):
            record = json.loads(path.read_text())
            if record["status"] != "success":
                sys.exit(f"{path} did not succeed; refusing to export a partial set")
            replays[record["input"]["case_id"]] = replay(record)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(replays, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(replays)} cases -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1:])
