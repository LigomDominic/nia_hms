"""One-off production cleanup for the LIVE database (instance/hms.db).

Removes: all test patients and their linked clinical/financial records,
seeded sample inventory (pharmacy drugs, store items, emergency cupboard),
all station requisitions/expenses, and every staff account except admin.

Keeps: admin account, settings, the 138-test lab catalog.

Run while the app is stopped:  python clean_for_production.py
A backup is always made to backups/ first.
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("instance/hms.db")

# Leaf-first order: every row in these tables is test/sample data.
# FK targets listed after their dependents; all FKs are NO ACTION.
TRANSACTIONAL_TABLES = [
    "treatment_administration",   # -> treatment_order
    "treatment_order",            # -> prescription_item
    "prescription_item",          # -> prescription, drug
    "prescription",               # -> patient, visit, bill
    "lab_request_item",           # -> lab_request, lab_test (tests kept)
    "lab_request",                # -> patient, visit, bill
    "emergency_stock_movement",   # -> emergency_drug_use, emergency_drug
    "emergency_drug_use",         # -> patient, visit, emergency_drug
    "requisition_item",           # -> station_requisition, drug
    "station_requisition",
    "drug_stock_movement",        # -> drug
    "drug",                       # sample pharmacy stock
    "store_movement",             # -> store_item
    "store_item",                 # sample store stock
    "emergency_drug",             # sample emergency cupboard
    "wallet_transaction",         # -> patient, bill
    "payment",                    # -> patient, bill
    "bill",                       # -> visit, patient
    "doctor_assignment",          # -> visit
    "anc_visit",                  # -> anc_profile
    "anc_profile",                # -> patient
    "fluid_balance_entry",        # -> patient
    "patient_consumable",         # -> patient
    "patient_observation",        # -> patient
    "visit",                      # -> patient
    "patient",
    "cleaning_task",
    "expense",
]


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = Path("backups") / f"{DB_PATH.stem}_pre_clean_{stamp}.db"
    backup.parent.mkdir(exist_ok=True)
    shutil.copy2(DB_PATH, backup)
    print(f"Backup: {backup}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")  # must precede any transaction
    cur = conn.cursor()
    cur.execute("BEGIN")

    for table in TRANSACTIONAL_TABLES:
        n = cur.execute(f'DELETE FROM "{table}"').rowcount
        if n:
            print(f"  {table}: {n} deleted")

    n = cur.execute(
        "DELETE FROM user_access WHERE user_id NOT IN (SELECT id FROM user WHERE username = 'admin')"
    ).rowcount
    if n:
        print(f"  user_access: {n} deleted")

    n = cur.execute("DELETE FROM user WHERE username <> 'admin'").rowcount
    print(f"  user: {n} staff accounts removed (kept: admin)")

    conn.commit()

    errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if errors:
        print(f"FK violations remain: {errors}")
        sys.exit(1)
    ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.execute("VACUUM")
    conn.close()
    print(f"integrity_check: {ok}")
    print("Done.")


if __name__ == "__main__":
    main()
