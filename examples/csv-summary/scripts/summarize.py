"""Summarize finite numeric cells in a CSV, without external dependencies."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Input CSV file")
    parser.add_argument("--precision", type=int, default=2, help="Decimal precision (0–10)")
    args = parser.parse_args()
    if not 0 <= args.precision <= 10:
        parser.error("precision must be between 0 and 10")
    with Path(args.input).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            parser.error("CSV needs a nonempty, unique header row")
        values = {name: [] for name in reader.fieldnames}
        rows = 0
        for row in reader:
            rows += 1
            for name in values:
                try:
                    number = float(row[name])
                    if math.isfinite(number):
                        values[name].append(number)
                except (ValueError, TypeError):
                    pass
    columns = [{"column": name, "count": len(numbers), "min": round(min(numbers), args.precision),
                "max": round(max(numbers), args.precision), "mean": round(statistics.fmean(numbers), args.precision),
                "sum": round(math.fsum(numbers), args.precision)} for name, numbers in values.items() if numbers]
    result = {"rows": rows, "columns": columns}
    Path("result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with Path("summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["column", "count", "min", "max", "mean", "sum"])
        writer.writeheader()
        writer.writerows(columns)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
