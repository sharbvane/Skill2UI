---
name: csv-summary
description: Summarize a CSV dataset with per-column numeric statistics and export verified JSON and CSV reports.
metadata:
  version: "1.0.0"
---

# CSV summary

Use this Skill to inspect a UTF-8 CSV file. The script uses Python's standard library.

1. Select an existing CSV file with a header row.
2. Set the numeric precision (0–10).
3. Approve the exact command shown by Skill2UI.
4. Read the actual numeric summaries, then download `result.json` or `summary.csv`.

Run manually: `python scripts/summarize.py --input assets/example.csv --precision 2`.
Reports are written to the current working directory. Inputs are read without modification.
