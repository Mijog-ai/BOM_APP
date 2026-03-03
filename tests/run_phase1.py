"""
PHASE 1 RUNNER — Database Discovery
Runs all 7 steps in /tests, captures output, saves to phase1_results.txt
"""

import sys
import os
import io
from datetime import datetime
from contextlib import redirect_stdout

# Make tests/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))

import step1_big_picture
import step2_prefix_groups
import step3_dataset_column
import step4_key_table_columns
import step5_sample_data
import step6_foreign_keys
import step7_document

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), 'phase1_results.txt')

STEPS = [
    ("STEP 1 — Big Picture (Tables + Row Counts)",   step1_big_picture.run),
    ("STEP 2 — Prefix Groups (Module Detection)",    step2_prefix_groups.run),
    ("STEP 3 — Dataset Column (Multi-Company Check)", step3_dataset_column.run),
    ("STEP 4 — Key Table Column Inspector",           step4_key_table_columns.run),
    ("STEP 5 — Sample Raw Data",                      step5_sample_data.run),
    ("STEP 6 — Foreign Key Relationships",            step6_foreign_keys.run),
    ("STEP 7 — Full Database Document (db_map.txt)",  step7_document.run),
]


def run_step(title, func):
    """Run a step, capture its printed output, return (output, error)."""
    print(f"  Running {title} ...", end=' ', flush=True)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            func()
        print("OK")
        return buf.getvalue(), None
    except Exception as e:
        print(f"FAILED — {e}")
        return buf.getvalue(), str(e)


def main():
    print("=" * 60)
    print("  PHASE 1 — DATABASE DISCOVERY")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []
    for title, func in STEPS:
        output, error = run_step(title, func)
        results.append((title, output, error))

    # Write everything to file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("PHASE 1 — DATABASE DISCOVERY RESULTS\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Server    : DEBLNSVERP01  /  Database: XALinl\n")
        f.write("=" * 70 + "\n")

        for title, output, error in results:
            f.write(f"\n\n{'#' * 70}\n")
            f.write(f"# {title}\n")
            f.write(f"{'#' * 70}\n\n")

            if output.strip():
                f.write(output)

            if error:
                f.write(f"\n[ERROR] {error}\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("END OF PHASE 1\n")

    # Summary
    passed = sum(1 for _, _, e in results if e is None)
    failed = len(results) - passed

    print()
    print("=" * 60)
    print(f"  Completed : {passed}/{len(results)} steps passed")
    if failed:
        print(f"  Failed    : {failed} step(s) — see details in output file")
    print(f"  Saved to  : {OUTPUT_FILE}")
    if os.path.exists(os.path.join(os.path.dirname(__file__), 'tests', 'db_map.txt')):
        print(f"  DB Map    : tests/db_map.txt  (from step 7)")
    print("=" * 60)


if __name__ == "__main__":
    main()
