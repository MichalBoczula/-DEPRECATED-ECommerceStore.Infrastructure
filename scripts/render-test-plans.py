#!/usr/bin/env python3
"""Render action metadata only; never disclose plan/state/diagnostic values."""
from collections import Counter
import json
from pathlib import Path
import re
import sys


def label(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_./-]+", value):
        raise ValueError("Unexpected test metadata label.")
    return value


def render(messages, root):
    lines = [f"### Offline configuration plans: {label(root)}", "",
             "Mocked configuration preview; no Azure authentication, live state comparison or deployment.", "",
             "Only action metadata is shown. Raw values, IDs and diagnostics are withheld.", ""]
    summaries = []
    for message in messages:
        if message.get("type") == "test_summary":
            summaries.append(message["test_summary"])
        if message.get("type") != "test_plan":
            continue
        plan = message["test_plan"]
        lines.extend([f"**{label(message['@testrun'])}**", "",
                      "| Resource type | Actions | Count |", "| --- | --- | ---: |"])
        counts = Counter()
        for resource in plan.get("resource_changes", []):
            actions = tuple(resource["change"]["actions"])
            if not actions or not set(actions) <= {"create", "read", "update", "delete", "no-op"}:
                raise ValueError("Unexpected plan action.")
            counts[(label(resource["type"]), actions)] += 1
        if counts:
            for (resource_type, actions), count in sorted(counts.items()):
                lines.append(f"| {resource_type} | {', '.join(actions)} | {count} |")
        else:
            lines.append("| No resource changes | — | 0 |")
        lines.append("")
        names = sorted(label(name) for name in plan.get("output_changes", {}))
        lines.extend(["Output names: " + (", ".join(names) or "none") + ".", ""])
    if not summaries or summaries[-1].get("status") != "pass":
        raise ValueError("Terraform tests did not report success.")
    summary = summaries[-1]
    passed = int(summary.get("passed", 0))
    if passed < 1 or any(int(summary.get(key, 0)) for key in ("failed", "errored", "skipped")):
        raise ValueError("Terraform tests failed or were skipped.")
    lines.extend([f"Tests passed: {passed}.", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        messages = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line]
        print(render(messages, sys.argv[2]))
    except (ValueError, KeyError, TypeError, OSError):
        sys.exit("Cannot produce a safe, successful configuration-plan summary.")
