"""
STEP 8 — SCRIPTNUM Similarity via Structured TXT1 Parsing

TXT1 structure:
  <FAMILY>-<SIZE>  <TYPECODE>-<rest>
  e.g.  V30D-095   RKN-1-0-02/LV*

Three parsed dimensions:
  family    : V30D, V30E, V30GL, V30B
  size      : 095, 140, 075, 066 ...
  type_code : RKN, RSN, RKGN, LKGN, RDN ...

Scoring per match:
  family + size + type_code = 4  (exact variant match)
  family + size              = 3  (same pump, different control)
  family + type_code         = 2  (same range, different size)
  type_code only             = 1  (same control type, different family)
"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(__file__))

from db_connection import get_connection
from collections import Counter

DATASET = 'INL'

# ─────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────
def parse_txt1(txt1):
    """
    Returns (family, size, type_code) from a TXT1 string.

    Examples:
      'V30D-095 RKN-1-0-02/LV*'   → ('V30D', '095', 'RKN')
      'V30GL-160 R D1 F V 1/LR'   → ('V30GL', '160', None)
      'V30B-066,128 ...'           → ('V30B', '066', ...)
      'Seal kit NBR V30D-...'      → (None, None, None)  ← non-standard
    """
    if not txt1:
        return None, None, None

    txt1 = txt1.strip()
    parts = txt1.split()
    if not parts:
        return None, None, None

    first_token = parts[0]

    # Family+size: e.g. V30D-095  V30GL-160  V30B-066
    # Pattern: letters(+digits) DASH digits
    m = re.match(r'^([A-Z][A-Z0-9]*)-(\d+)', first_token)
    if not m:
        return None, None, None

    family = m.group(1)          # V30D, V30GL, V30B, V30E
    size   = m.group(2)          # 095, 160, 066, 140

    # Type code: leading uppercase letters from second token
    type_code = None
    if len(parts) >= 2:
        m2 = re.match(r'^([A-Z]{2,})', parts[1])
        if m2:
            type_code = m2.group(1)   # RKN, RKGN, RSN, LKGN, RDN ...

    return family, size, type_code


# ─────────────────────────────────────────────────────────────────────
# Fetch all scripts from DB
# ─────────────────────────────────────────────────────────────────────
def fetch_all_scripts(cursor):
    cursor.execute("""
        SELECT DISTINCT
            b.SCRIPTNUM,
            b.FATHERITEMNUM,
            st.ITEMNAME,
            tx.TXT1
        FROM XALinl.dbo.B407SBM_INL b
        JOIN XALinl.dbo.STOCKTABLE  st
            ON st.DATASET = b.DATASET AND st.ITEMNUMBER = b.FATHERITEMNUM
        JOIN XALinl.dbo.TEXTS       tx
            ON tx.DATASET = b.DATASET AND tx.TXTID = b.FATHERITEMNUM
        WHERE b.DATASET = ?
    """, (DATASET,))

    scripts = {}
    for row in cursor.fetchall():
        scriptnum, fatheritem, itemname, txt1 = row
        txt1_clean = str(txt1 or '').strip()
        family, size, type_code = parse_txt1(txt1_clean)
        scripts[scriptnum] = {
            'father'    : fatheritem,
            'itemname'  : str(itemname or '').strip(),
            'txt1'      : txt1_clean,
            'family'    : family,
            'size'      : size,
            'type_code' : type_code,
        }
    return scripts


# ─────────────────────────────────────────────────────────────────────
# SECTION 1 — Parser sanity check (sample rows)
# ─────────────────────────────────────────────────────────────────────
def section1_parse_sample(scripts):
    print("\n" + "=" * 90)
    print("  SECTION 1 — Parser output (first 30 scripts)")
    print("=" * 90)
    print(f"  {'SCRIPTNUM':<15} {'FAMILY':<8} {'SIZE':<6} {'TYPE':<8} TXT1")
    print(f"  {'-'*15} {'-'*8} {'-'*6} {'-'*8} {'-'*45}")

    for i, (snum, d) in enumerate(scripts.items()):
        if i >= 30:
            break
        print(f"  {str(snum):<15} "
              f"{(d['family'] or '?'):<8} "
              f"{(d['size']   or '?'):<6} "
              f"{(d['type_code'] or '?'):<8} "
              f"{d['txt1'][:50]}")

    # How many parsed OK vs not?
    total   = len(scripts)
    ok      = sum(1 for d in scripts.values() if d['family'])
    no_type = sum(1 for d in scripts.values() if d['family'] and not d['type_code'])
    failed  = total - ok
    print(f"\n  Parsed OK (family+size found) : {ok} / {total}")
    print(f"  Has type_code                 : {ok - no_type} / {ok}")
    print(f"  Could not parse               : {failed}")


# ─────────────────────────────────────────────────────────────────────
# SECTION 2 — Distribution of families, sizes, type codes
# ─────────────────────────────────────────────────────────────────────
def section2_distributions(scripts):
    fam_count  = Counter(d['family']    for d in scripts.values() if d['family'])
    size_count = Counter(d['size']      for d in scripts.values() if d['size'])
    tc_count   = Counter(d['type_code'] for d in scripts.values() if d['type_code'])

    print("\n" + "=" * 90)
    print("  SECTION 2a — Product families")
    print("=" * 90)
    for fam, cnt in fam_count.most_common():
        bar = '█' * cnt
        print(f"  {fam:<10} {cnt:>4}  {bar}")

    print("\n" + "=" * 90)
    print("  SECTION 2b — Sizes (top 15)")
    print("=" * 90)
    for size, cnt in size_count.most_common(15):
        bar = '█' * min(cnt, 60)
        print(f"  {size:<8} {cnt:>4}  {bar}")

    print("\n" + "=" * 90)
    print("  SECTION 2c — Type codes (top 20)")
    print("=" * 90)
    for tc, cnt in tc_count.most_common(20):
        bar = '█' * min(cnt, 60)
        print(f"  {tc:<12} {cnt:>4}  {bar}")


# ─────────────────────────────────────────────────────────────────────
# SECTION 3 — Similarity search for a target SCRIPTNUM
# ─────────────────────────────────────────────────────────────────────
def section3_similarity(scripts, target_scriptnum=None):
    print("\n" + "=" * 90)
    print("  SECTION 3 — Similarity search")
    print("=" * 90)

    # Default: pick first script with all three fields
    if target_scriptnum is None:
        for snum, d in scripts.items():
            if d['family'] and d['size'] and d['type_code']:
                target_scriptnum = snum
                break

    if target_scriptnum not in scripts:
        print(f"  Script '{target_scriptnum}' not found.")
        return

    t = scripts[target_scriptnum]
    print(f"  Target SCRIPTNUM : {target_scriptnum}")
    print(f"  Father item      : {t['father']}")
    print(f"  TXT1             : {t['txt1']}")
    print(f"  → Family         : {t['family']}")
    print(f"  → Size           : {t['size']}")
    print(f"  → Type code      : {t['type_code']}")

    results = []
    for snum, d in scripts.items():
        if snum == target_scriptnum:
            continue

        fam_match  = bool(t['family']    and d['family']    == t['family'])
        size_match = bool(t['size']      and d['size']      == t['size'])
        tc_match   = bool(t['type_code'] and d['type_code'] == t['type_code'])

        # Only show if at least type_code or (family+size) matches
        if not (tc_match or (fam_match and size_match)):
            continue

        # Score: family+size = 3 pts, type_code = 1 pt  (max = 4)
        score = (3 if (fam_match and size_match) else 0) + (1 if tc_match else 0)

        match_parts = []
        if fam_match and size_match: match_parts.append('family+size')
        elif fam_match:              match_parts.append('family')
        if tc_match:                 match_parts.append('type')
        match_label = ' & '.join(match_parts)

        results.append((score, match_label, snum, d))

    results.sort(key=lambda x: -x[0])

    print(f"\n  Found {len(results)} similar scripts:\n")
    print(f"  {'Sc':<4} {'Match':<22} {'SCRIPTNUM':<15} {'FAM':<8} {'SZ':<6} {'TYPE':<8} TXT1")
    print(f"  {'-'*4} {'-'*22} {'-'*15} {'-'*8} {'-'*6} {'-'*8} {'-'*45}")

    for score, match_label, snum, d in results:
        print(f"  {score:<4} {match_label:<22} {str(snum):<15} "
              f"{(d['family'] or ''):<8} "
              f"{(d['size'] or ''):<6} "
              f"{(d['type_code'] or ''):<8} "
              f"{d['txt1'][:45]}")

    # Summary
    counts = Counter(r[0] for r in results)
    print(f"\n  Score 4 (family+size+type) : {counts[4]}")
    print(f"  Score 3 (family+size only) : {counts[3]}")
    print(f"  Score 1 (type only)        : {counts[1]}")


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────
def run():
    conn   = get_connection()
    cursor = conn.cursor()

    print("  Fetching scripts...")
    scripts = fetch_all_scripts(cursor)
    print(f"  Loaded {len(scripts)} scripts.")

    section1_parse_sample(scripts)
    section2_distributions(scripts)
    section3_similarity(scripts)   # auto-picks first fully-parsed script as target

    conn.close()
    print("\n  Done.")


if __name__ == "__main__":
    run()
