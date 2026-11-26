from flask import current_app

from datetime import date, timedelta

from .extensions import db
from .models import (Drug, DrugStockMovement, EmergencyDrug, EmergencyStockMovement, LabTest, Setting, StoreItem,
                     StoreMovement, User)

DEMO_USERS = [
    ("admin", "System Administrator", "admin", None),
    ("cashier", "Grace Okafor", "cashier", None),
    ("doctor", "Samuel Adeyemi", "doctor", "General Practice"),
    ("visiting", "Helen Bassey", "visiting_doctor", "Cardiology (Visiting)"),
    ("nurse", "Mary Johnson", "nurse", None),
    ("lab", "Peter Eze", "lab", None),
    ("pharmacist", "Ruth Danladi", "pharmacist", None),
    ("store", "Musa Ibrahim", "store_keeper", None),
    ("cleaner", "Joy Akpan", "cleaner", None),
]
DEMO_PASSWORD = "password123"

LAB_TESTS = [
    ("Full Blood Count (FBC)", "Haematology", "Blood", "", "", 4500),
    ("Malaria Parasite (MP)", "Parasitology", "Blood", "", "Not seen", 1500),
    ("Widal Test", "Serology", "Blood", "titre", "< 1:80", 2000),
    ("Fasting Blood Sugar", "Clinical Chemistry", "Blood", "mg/dL", "70 - 100", 1500),
    ("Urinalysis", "Urinalysis", "Urine", "", "", 1500),
    ("Packed Cell Volume (PCV)", "Haematology", "Blood", "%", "36 - 50", 1000),
    ("Lipid Profile", "Clinical Chemistry", "Blood", "mg/dL", "", 8000),
    ("Liver Function Test", "Clinical Chemistry", "Blood", "", "", 9000),
    ("HIV Screening", "Serology", "Blood", "", "Non-reactive", 2500),
    ("Pregnancy Test", "Urinalysis", "Urine", "", "", 1000),
    ("Urine MCS", "Microbiology", "Urine", "", "", 4000),
    ("Stool MCS", "Microbiology", "Stool", "", "", 4000),
    ("Throat Swab MCS", "Microbiology", "Throat swab", "", "", 4000),
    ("High Vaginal Swab (HVS) MCS", "Microbiology", "HVS", "", "", 4500),
    ("Urethral Swab MCS", "Microbiology", "Urethral swab", "", "", 4000),
    ("Wound Swab MCS", "Microbiology", "Wound swab", "", "", 4000),
    ("Sputum MCS", "Microbiology", "Sputum", "", "", 4000),
    ("Semen MCS", "Microbiology", "Semen", "", "", 4500),
    ("Blood Culture", "Microbiology", "Blood", "", "", 6000),
]
SAMPLE_LAB_TEST_NAMES = {t[0] for t in LAB_TESTS}

LAB_CATEGORIES = ["Haematology", "Clinical Chemistry", "Microbiology", "Parasitology", "Serology", "Immunology",
                  "Urinalysis", "Endocrinology", "Histopathology", "Molecular / PCR", "Blood Bank", "Radiology / Imaging"]

DRUGS = [
    ("Paracetamol", "Tablet", "500mg", 20, 500, 50),
    ("Amoxicillin", "Capsule", "500mg", 80, 300, 40),
    ("Artemether/Lumefantrine", "Tablet", "80/480mg", 1500, 120, 20),
    ("Ibuprofen", "Tablet", "400mg", 40, 300, 40),
    ("Metronidazole", "Tablet", "400mg", 30, 250, 40),
    ("ORS Sachet", "Sachet", "20.5g", 150, 100, 20),
    ("Vitamin C", "Tablet", "100mg", 10, 400, 50),
    ("Ceftriaxone", "Injection", "1g", 1200, 60, 15),
    ("Cough Syrup", "Syrup", "100ml", 900, 50, 10),
    ("Omeprazole", "Capsule", "20mg", 60, 200, 30),
]

STORE_ITEMS = [
    ("Hand Gloves (box)", "Consumables", "box", 40, 10, "Main Store"),
    ("Face Masks (box)", "Consumables", "box", 30, 10, "Main Store"),
    ("Syringes 5ml", "Consumables", "pcs", 600, 100, "Main Store"),
    ("Cotton Wool", "Consumables", "roll", 50, 10, "Main Store"),
    ("Hospital Bed Sheets", "Linen", "pcs", 80, 20, "Linen Room"),
    ("Liquid Detergent (5L)", "Cleaning", "gallon", 15, 5, "Janitor Store"),
    ("Disinfectant (5L)", "Cleaning", "gallon", 12, 5, "Janitor Store"),
    ("A4 Paper (ream)", "Stationery", "ream", 25, 5, "Admin Store"),
]

EMERGENCY_DRUGS = [
    ("Adrenaline (Epinephrine)", "Injection", "1mg/ml", "ampoule", 10, 4),
    ("Hydrocortisone", "Injection", "100mg", "vial", 10, 4),
    ("Diazepam", "Injection", "10mg/2ml", "ampoule", 8, 3),
    ("Dextrose 50%", "Injection", "50ml", "vial", 6, 2),
    ("Promethazine", "Injection", "25mg/ml", "ampoule", 10, 4),
    ("Paracetamol", "Infusion", "1g/100ml", "bottle", 10, 4),
    ("Salbutamol Inhaler", "Inhaler", "100mcg", "inhaler", 4, 2),
    ("Aspirin", "Tablet", "300mg", "tablet", 30, 10),
    ("Normal Saline", "Infusion", "500ml", "bag", 12, 5),
    ("Furosemide", "Injection", "20mg/2ml", "ampoule", 10, 4),
]


def seed_all(include_samples=None):
    if User.query.count() == 0:
        for username, name, role, specialty in DEMO_USERS:
            u = User(username=username, full_name=name, role=role, specialty=specialty,
                     email=f"{username}@hospital.local")
            u.set_password(DEMO_PASSWORD)
            db.session.add(u)
        db.session.flush()

    for key, value in Setting.DEFAULTS.items():
        if db.session.get(Setting, key) is None:
            db.session.add(Setting(key=key, value=value))

    if LabTest.query.count() == 0 and current_app.config.get("SEED_SAMPLE_LAB_TESTS"):
        for name, category, sample, unit, ref, price in LAB_TESTS:
            db.session.add(LabTest(name=name, category=category, sample_type=sample, unit=unit,
                                   reference_range=ref, price=price))

    if include_samples is None:
        include_samples = current_app.config.get("SEED_SAMPLE_INVENTORY", False)
    if not include_samples:
        db.session.commit()
        return

    if Drug.query.count() == 0:
        for i, (name, form, strength, price, qty, reorder) in enumerate(DRUGS):
            d = Drug(name=name, form=form, strength=strength, unit_price=price, quantity=qty,
                     reorder_level=reorder, batch_no=f"B{2026}{i + 1:03d}",
                     expiry_date=date.today() + timedelta(days=60 if i == 8 else 400))
            db.session.add(d)
            db.session.flush()
            db.session.add(DrugStockMovement(drug=d, change=qty, balance_after=qty, reason="opening",
                                             note="Opening stock"))

    if StoreItem.query.count() == 0:
        for name, cat, unit, qty, reorder, loc in STORE_ITEMS:
            it = StoreItem(name=name, category=cat, unit=unit, quantity=qty, reorder_level=reorder, location=loc)
            db.session.add(it)
            db.session.flush()
            db.session.add(StoreMovement(item=it, change=qty, balance_after=qty, kind="opening",
                                         note="Opening stock"))
    seed_emergency_drugs()
    db.session.commit()


def seed_emergency_drugs():
    """Nurses' office emergency drug cupboard. Runs on existing databases too (new table)."""
    if EmergencyDrug.query.count():
        return
    for i, (name, form, strength, unit, qty, reorder) in enumerate(EMERGENCY_DRUGS):
        d = EmergencyDrug(name=name, form=form, strength=strength, unit=unit, quantity=qty, reorder_level=reorder,
                          batch_no=f"ER2026{i + 1:03d}", expiry_date=date.today() + timedelta(days=45 if i == 3 else 300))
        db.session.add(d)
        db.session.flush()
        db.session.add(EmergencyStockMovement(drug=d, change=qty, balance_after=qty, kind="opening",
                                              note="Opening stock"))


def seed_demo_users():
    """Create any missing demo staff accounts (training DB only). Existing
    accounts — including a real admin copied from live — are left untouched."""
    existing = {u.username for u in User.query}
    for username, name, role, specialty in DEMO_USERS:
        if username in existing:
            continue
        u = User(username=username, full_name=name, role=role, specialty=specialty,
                 email=f"{username}@hospital.local")
        u.set_password(DEMO_PASSWORD)
        db.session.add(u)
    db.session.commit()
