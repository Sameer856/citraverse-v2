"""Bounded status sampling, not a per-frame continuity measurement."""
import argparse
import json
import time
from pathlib import Path
from laptop_control import exchange

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--local-evidence", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--label", required=True)
    options = parser.parse_args()
    if not 1 <= options.seconds <= 600:
        parser.error("duration must be 1..600 seconds")
    start = time.monotonic()
    samples = []
    output = options.local_evidence / (options.label+"_samples.json")
    while time.monotonic()-start < options.seconds:
        entry = {"elapsed_s": time.monotonic()-start}
        try:
            entry.update(exchange("status", options.library, options.local_evidence))
        except Exception as error:
            entry["error"] = str(error)
        samples.append(entry)
        output.write_text(json.dumps(samples, indent=2))
        print(json.dumps(entry), flush=True)
    valid = [x["reply"] for x in samples if "reply" in x]
    summary = {"label": options.label, "elapsed_s": time.monotonic()-start,
               "samples": len(samples), "valid": len(valid),
               "occupied_samples": sum(x["occupied"] for x in valid),
               "maximum_sampled_evidence_age_ms": max((x["evidence_age_ms"] for x in valid if x["evidence_age_ms"] != 0xffffffff), default=None),
               "limitation": "Approx. 3-second snapshots cannot establish uninterrupted detection or exclude between-sample false detections."}
    options.local_evidence.joinpath(options.label+"_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
