import json
from datetime import datetime, date

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager

ROLES = {
    "admin": "Administrator",
    "cashier": "Cashier",
    "doctor": "Doctor",
    "visiting_doctor": "Visiting Doctor",
    "nurse": "Nurse",
    "lab": "Lab Scientist",
    "pharmacist": "Pharmacist",
    "store_keeper": "Store Keeper",
    "cleaner": "Cleaner",
}
DOCTOR_ROLES = ("doctor", "visiting_doctor")
CLINICAL_ROLES = ("admin", "cashier", "doctor", "visiting_doctor", "nurse", "lab", "pharmacist")
PAYMENT_METHODS = {"cash": "Cash", "pos": "POS / Card", "transfer": "Bank Transfer", "wallet": "E-Wallet"}


def now():
    return datetime.now()


def money(value):
    return round(float(value or 0), 2)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    role = db.Column(db.String(30), nullable=False)
    specialty = db.Column(db.String(120))
    password_hash = db.Column(db.String(256), nullable=False)
    is_active_user = db.Column(db.Boolean, default=True)
    monthly_salary = db.Column(db.Float)                        # set on the payroll page
    created_at = db.Column(db.DateTime, default=now)

    @property
    def is_active(self):
        return bool(self.is_active_user)

    @property
    def role_label(self):
        return ROLES.get(self.role, self.role)

    @property
    def display_name(self):
        if self.role in DOCTOR_ROLES:
            return f"Dr. {self.full_name}"
        return self.full_name

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class UserAccess(db.Model):
    """Per-user module access override. No row = inherit role defaults."""
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    module = db.Column(db.String(30), primary_key=True)
    level = db.Column(db.String(10), nullable=False)  # none, view, manage

    user = db.relationship("User", backref=db.backref("access_overrides", cascade="all, delete-orphan"))

    LEVELS = ("none", "view", "manage")


class PatientObservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False, index=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False, index=True)
    notes = db.Column(db.Text, nullable=False)
    medication = db.Column(db.Text)
    signature = db.Column(db.String(120))
    temperature = db.Column(db.String(30))
    blood_pressure = db.Column(db.String(30))
    pulse = db.Column(db.String(30))
    respiration = db.Column(db.String(30))
    weight = db.Column(db.String(30))
    spo2 = db.Column(db.String(30))

    patient = db.relationship("Patient")
    recorded_by = db.relationship("User")


class PatientConsumable(db.Model):
    """One dated row of consumable items used on a patient."""
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False, index=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today)
    name = db.Column(db.String(160))
    urine_bag = db.Column(db.Integer, nullable=False, default=0)
    cannula = db.Column(db.Integer, nullable=False, default=0)
    syringes = db.Column(db.Integer, nullable=False, default=0)
    gloves = db.Column(db.Integer, nullable=False, default=0)
    blood_bag = db.Column(db.Integer, nullable=False, default=0)
    infusion_set = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=now, nullable=False)

    patient = db.relationship("Patient")
    recorded_by = db.relationship("User")

    ITEM_FIELDS = (("urine_bag", "Urine Bag"), ("cannula", "Cannula"), ("syringes", "Syringes"),
                   ("gloves", "Gloves"), ("blood_bag", "Blood Bag"), ("infusion_set", "Infusion Set"))


class FluidBalanceEntry(db.Model):
    """One row of the patient's fluid balance chart (amounts in ml)."""
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False, index=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    entry_at = db.Column(db.DateTime, nullable=False, default=now, index=True)
    fluid = db.Column(db.String(160))
    oral = db.Column(db.Integer, nullable=False, default=0)
    parenteral = db.Column(db.Integer, nullable=False, default=0)
    other_intake = db.Column(db.Integer, nullable=False, default=0)
    urine = db.Column(db.Integer, nullable=False, default=0)
    vomit = db.Column(db.Integer, nullable=False, default=0)
    aspirate = db.Column(db.Integer, nullable=False, default=0)
    bowels = db.Column(db.Integer, nullable=False, default=0)
    blood_loss = db.Column(db.Integer, nullable=False, default=0)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now, nullable=False)

    patient = db.relationship("Patient")
    recorded_by = db.relationship("User")

    INTAKE_FIELDS = (("oral", "Oral"), ("parenteral", "Parenteral"), ("other_intake", "Other"))
    OUTPUT_FIELDS = (("urine", "Urine"), ("vomit", "Vomit"), ("aspirate", "Aspirate"),
                     ("bowels", "Bowels"), ("blood_loss", "Blood loss"))
    ALL_FIELDS = INTAKE_FIELDS + OUTPUT_FIELDS

    @property
    def intake_total(self):
        return sum(getattr(self, key) or 0 for key, _l in self.INTAKE_FIELDS)

    @property
    def output_total(self):
        return sum(getattr(self, key) or 0 for key, _l in self.OUTPUT_FIELDS)

    @property
    def net(self):
        return self.intake_total - self.output_total


class Setting(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255))

    DEFAULTS = {"card_fee": "2000", "consultation_fee": "5000", "anc_fee": "15000",
                "file_retrieval_fee": "1000", "file_retrieval_days": "30"}

    @classmethod
    def get(cls, key):
        row = db.session.get(cls, key)
        return row.value if row else cls.DEFAULTS.get(key)

    @classmethod
    def get_money(cls, key):
        try:
            return money(cls.get(key))
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def set(cls, key, value):
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key)
            db.session.add(row)
        row.value = str(value)


class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.String(30), unique=True, index=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    other_names = db.Column(db.String(80))
    gender = db.Column(db.String(10))
    date_of_birth = db.Column(db.Date)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    address = db.Column(db.String(255))
    blood_group = db.Column(db.String(5))
    genotype = db.Column(db.String(5))
    allergies = db.Column(db.String(255))
    next_of_kin_name = db.Column(db.String(120))
    next_of_kin_phone = db.Column(db.String(30))
    status = db.Column(db.String(20), default="Outpatient")
    wallet_balance = db.Column(db.Float, default=0.0, nullable=False)
    registered_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)

    registered_by = db.relationship("User")
    visits = db.relationship("Visit", back_populates="patient", order_by="desc(Visit.created_at)")
    bills = db.relationship("Bill", back_populates="patient", order_by="desc(Bill.created_at)")
    wallet_transactions = db.relationship(
        "WalletTransaction", back_populates="patient", order_by="desc(WalletTransaction.id)"
    )
    lab_requests = db.relationship("LabRequest", back_populates="patient", order_by="desc(LabRequest.created_at)")
    prescriptions = db.relationship(
        "Prescription", back_populates="patient", order_by="desc(Prescription.created_at)"
    )
    anc_profiles = db.relationship("AncProfile", back_populates="patient", order_by="desc(AncProfile.created_at)")

    STATUSES = ("Outpatient", "Admitted", "Discharged", "Inactive")

    @property
    def full_name(self):
        parts = [self.first_name, self.other_names, self.last_name]
        return " ".join(p for p in parts if p)

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    @property
    def outstanding_balance(self):
        return money(sum(b.balance for b in self.bills if b.status in ("unpaid", "part_paid")))

    @property
    def total_paid(self):
        return money(sum(b.amount_paid for b in self.bills if b.status != "cancelled"))

    @property
    def current_visit(self):
        for v in self.visits:
            if v.status != "completed":
                return v
        return None

    @property
    def current_anc(self):
        for a in self.anc_profiles:
            if a.status == "active":
                return a
        return None


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    visit_type = db.Column(db.String(20), default="New")
    complaint = db.Column(db.Text)
    status = db.Column(db.String(20), default="waiting")  # waiting, in_consultation, completed
    consultation_fee = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    # vitals (nurse)
    temperature = db.Column(db.String(10))
    blood_pressure = db.Column(db.String(15))
    pulse = db.Column(db.String(10))
    respiration = db.Column(db.String(10))
    weight = db.Column(db.String(10))
    spo2 = db.Column(db.String(10))
    vitals_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    vitals_at = db.Column(db.DateTime)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)
    completed_at = db.Column(db.DateTime)

    patient = db.relationship("Patient", back_populates="visits")
    doctor = db.relationship("User", foreign_keys=[doctor_id])
    vitals_by = db.relationship("User", foreign_keys=[vitals_by_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    STATUS_LABELS = {"waiting": "Waiting", "in_consultation": "In consultation", "completed": "Completed"}

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def has_vitals(self):
        return self.vitals_at is not None

    def assign_doctor(self, doctor, user, note=None):
        """Assign or re-assign the consulting doctor, keeping an audit trail. Returns False if unchanged."""
        if self.doctor_id == doctor.id:
            return False
        db.session.add(DoctorAssignment(visit=self, from_doctor=self.doctor, to_doctor=doctor,
                                        assigned_by=user, note=note))
        self.doctor = doctor
        return True


class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    visit_id = db.Column(db.Integer, db.ForeignKey("visit.id"))
    category = db.Column(db.String(20), nullable=False)  # card, consultation, lab, pharmacy, service
    description = db.Column(db.String(255))
    amount = db.Column(db.Float, nullable=False)
    amount_paid = db.Column(db.Float, default=0.0, nullable=False)
    status = db.Column(db.String(20), default="unpaid")  # unpaid, part_paid, paid, cancelled
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)
    paid_at = db.Column(db.DateTime)

    patient = db.relationship("Patient", back_populates="bills")
    visit = db.relationship("Visit")
    created_by = db.relationship("User")
    payments = db.relationship("Payment", back_populates="bill", order_by="Payment.id")
    lab_request = db.relationship("LabRequest", back_populates="bill", uselist=False)
    prescription = db.relationship("Prescription", back_populates="bill", uselist=False)

    CATEGORY_LABELS = {
        "card": "Card / Registration",
        "consultation": "Consultation",
        "lab": "Laboratory",
        "pharmacy": "Pharmacy",
        "service": "Other Service",
    }
    STATUS_LABELS = {"unpaid": "Unpaid", "part_paid": "Part paid", "paid": "Paid", "cancelled": "Cancelled"}

    @property
    def balance(self):
        return money(self.amount - self.amount_paid)

    @property
    def category_label(self):
        return self.CATEGORY_LABELS.get(self.category, self.category)

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey("bill.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(20), nullable=False)
    reference = db.Column(db.String(80))
    received_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)

    bill = db.relationship("Bill", back_populates="payments")
    patient = db.relationship("Patient")
    received_by = db.relationship("User")

    @property
    def method_label(self):
        return PAYMENT_METHODS.get(self.method, self.method)


class WalletTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    kind = db.Column(db.String(10), nullable=False)  # deposit, debit, refund
    amount = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(20))
    reference = db.Column(db.String(80))
    description = db.Column(db.String(255))
    bill_id = db.Column(db.Integer, db.ForeignKey("bill.id"))
    performed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)

    patient = db.relationship("Patient", back_populates="wallet_transactions")
    bill = db.relationship("Bill")
    performed_by = db.relationship("User")


class LabTest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    category = db.Column(db.String(60))
    sample_type = db.Column(db.String(60))
    unit = db.Column(db.String(30))
    reference_range = db.Column(db.String(80))
    price = db.Column(db.Float, nullable=False, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    template = db.Column(db.String(60))  # key into lab_templates.RESULT_TEMPLATES

    @property
    def category_label(self):
        return self.category or "Other tests"

    @property
    def times_requested(self):
        return LabRequestItem.query.filter_by(test_id=self.id).count()


class LabRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    visit_id = db.Column(db.Integer, db.ForeignKey("visit.id"))
    doctor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    bill_id = db.Column(db.Integer, db.ForeignKey("bill.id"))
    clinical_notes = db.Column(db.Text)
    # awaiting_payment -> sent_to_lab -> in_progress -> completed
    status = db.Column(db.String(20), default="awaiting_payment")
    posted_to_lab_at = db.Column(db.DateTime)
    posted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    completed_at = db.Column(db.DateTime)
    completed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    lab_comment = db.Column(db.Text)
    delivery_method = db.Column(db.String(10))  # email, manual
    delivery_status = db.Column(db.String(20))  # emailed, email_failed, awaiting_collection, collected
    delivery_note = db.Column(db.String(255))
    collected_at = db.Column(db.DateTime)
    doctor_viewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now)

    patient = db.relationship("Patient", back_populates="lab_requests")
    visit = db.relationship("Visit")
    doctor = db.relationship("User", foreign_keys=[doctor_id])
    posted_by = db.relationship("User", foreign_keys=[posted_by_id])
    completed_by = db.relationship("User", foreign_keys=[completed_by_id])
    bill = db.relationship("Bill", back_populates="lab_request")
    items = db.relationship("LabRequestItem", back_populates="request", cascade="all, delete-orphan")

    STATUS_LABELS = {
        "awaiting_payment": "Awaiting payment (Cashier)",
        "sent_to_lab": "Paid - sent to Lab",
        "in_progress": "In progress (Lab)",
        "completed": "Result ready",
        "cancelled": "Cancelled",
    }
    DELIVERY_LABELS = {
        "emailed": "Emailed to patient",
        "email_failed": "Email failed - manual collection",
        "awaiting_collection": "Awaiting manual collection",
        "collected": "Collected by patient",
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def delivery_label(self):
        return self.DELIVERY_LABELS.get(self.delivery_status, self.delivery_status or "-")

    @property
    def total(self):
        return money(sum(i.price for i in self.items))

    @property
    def test_names(self):
        return ", ".join(i.test_name for i in self.items)

    @property
    def requester_label(self):
        return self.doctor.display_name if self.doctor else "Walk-in"


# Antibiotic panels printed on the microbiology (MCS) result sheet.
MICRO_CATEGORY = "Microbiology"
MICRO_DRUG_PANELS = {
    "pos": ["CIPROFLOXACIN (CPX)", "NORFLOXACIN (NB)", "GENTAMYCIN (CN)", "AMOXIL (AML)", "STREPTOMYCIN (S)",
            "RIFAMPICIN (RD)", "ERYTHROMYCIN (E)", "CHLORAMPHENICOL (CH)", "AMPICLOX (APX)", "LEVOFLOXACIN (LEV)",
            "TARIVID (OFX)", "REFLACINE (PEF)", "AUGMENTIN (AU)", "CEPOREX (CEP)", "CEFTAZIDIME (CTZ)",
            "SEPTRIN (SXT)", "AMPLICIN (PN)", "CEFIXIME + CLAVULANIC ACID (CVC)", "CEFEPIME (UPM)", "CEFTRIAXONE (E)",
            "OFLOXACIN + ORNIDAZOLE (OFD)", "CEFTRIAXONE + TAZOBACTAM (ECF)", "CEFOXACINE", "AZITHROMYCIN (S2)"],
    "neg": ["CIPROFLOXACIN (CPX)", "GENTAMYCIN (CN)", "AMOXIL (AML)", "STREPTOMYCIN (S)", "AUGMENTIN (AU)",
            "PEFLACINE (PEF)", "CEFTAZIDIME (CTZ)", "CEPOREX (CEP)", "CEFTRIAXONE (TRX)", "CEFUROXIME (CEF)",
            "NORBACTINE (I)", "OFLOXACINE (OFX)"],
}
MICRO_PANEL_PAIRS = {(grp, name) for grp, names in MICRO_DRUG_PANELS.items() for name in names}


class LabRequestItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("lab_request.id"), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey("lab_test.id"))
    test_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(30))
    reference_range = db.Column(db.String(80))
    result = db.Column(db.String(255))
    flag = db.Column(db.String(10))  # Normal, High, Low, Positive, Negative
    micro_data = db.Column(db.Text)  # JSON: specimen, macroscopy, microscopy, culture, gram_stain, drugs[]
    result_data = db.Column(db.Text)  # JSON: {field name: {"v": value, "f": flag}} for templated tests

    request = db.relationship("LabRequest", back_populates="items")
    test = db.relationship("LabTest")

    @property
    def is_micro(self):
        """True for culture & sensitivity (microbiology) tests that use the MCS result sheet."""
        if self.test is not None and self.test.category == MICRO_CATEGORY:
            return True
        name = (self.test_name or "").lower()
        return "mcs" in name or "culture" in name

    @property
    def result_template(self):
        """Structured result template {"label", "fields"} for this item, or None."""
        if self.is_micro:
            return None
        from .lab_templates import LIBRARY_TEMPLATE_BY_NAME, RESULT_TEMPLATES
        key = self.test.template if self.test else None
        if not key:
            key = LIBRARY_TEMPLATE_BY_NAME.get(self.test_name)
        return RESULT_TEMPLATES.get(key) if key else None

    @property
    def result_values(self):
        """{field name: {"v": value, "f": flag}} entered on the template form."""
        if not self.result_data:
            return {}
        try:
            data = json.loads(self.result_data)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def micro(self):
        if not self.micro_data:
            return {}
        try:
            data = json.loads(self.micro_data)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def micro_sel(self):
        """{'pos:DRUG NAME': 'S'/'R'} for pre-selecting the entry form."""
        return {f"{d.get('group')}:{d.get('name')}": d.get("res") for d in self.micro.get("drugs", [])}

    @property
    def micro_extra(self):
        """Recorded antibiotics that are not on the standard printed panel."""
        return [d for d in self.micro.get("drugs", []) if (d.get("group"), d.get("name")) not in MICRO_PANEL_PAIRS]

    def micro_drug_pairs(self):
        """Zipped (gram+ve drug, gram-ve drug) rows for the printed sheet."""
        drugs = self.micro.get("drugs", [])
        pos = [d for d in drugs if d.get("group") == "pos"]
        neg = [d for d in drugs if d.get("group") == "neg"]
        n = max(len(pos), len(neg))
        return [(pos[k] if k < len(pos) else None, neg[k] if k < len(neg) else None) for k in range(n)]

    @property
    def micro_line(self):
        """One-line sensitivity summary, used in list views and emails."""
        drugs = self.micro.get("drugs", [])
        parts = []
        for res, label in (("S", "Sensitive"), ("R", "Resistant")):
            names = ", ".join(d["name"] for d in drugs if d.get("res") == res)
            if names:
                parts.append(f"{label}: {names}")
        return " | ".join(parts)


class Drug(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    form = db.Column(db.String(40))  # Tablet, Syrup, Injection...
    strength = db.Column(db.String(40))
    unit_price = db.Column(db.Float, nullable=False, default=0.0)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    reorder_level = db.Column(db.Integer, default=10)
    batch_no = db.Column(db.String(40))
    expiry_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)

    @property
    def label(self):
        return " ".join(p for p in [self.name, self.strength, self.form] if p)

    @property
    def is_low(self):
        return self.quantity <= (self.reorder_level or 0)

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < date.today())

    @property
    def expires_soon(self):
        return bool(self.expiry_date and 0 <= (self.expiry_date - date.today()).days <= 90)


class DrugStockMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drug.id"), nullable=False)
    change = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(20), nullable=False)  # opening, restock, dispense, adjustment
    note = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)

    drug = db.relationship("Drug")
    user = db.relationship("User")


class Prescription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    visit_id = db.Column(db.Integer, db.ForeignKey("visit.id"))
    doctor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    bill_id = db.Column(db.Integer, db.ForeignKey("bill.id"))
    notes = db.Column(db.Text)
    # awaiting_payment -> ready_to_dispense -> dispensed
    status = db.Column(db.String(20), default="awaiting_payment")
    posted_at = db.Column(db.DateTime)
    dispensed_at = db.Column(db.DateTime)
    dispensed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)

    patient = db.relationship("Patient", back_populates="prescriptions")
    visit = db.relationship("Visit")
    doctor = db.relationship("User", foreign_keys=[doctor_id])
    dispensed_by = db.relationship("User", foreign_keys=[dispensed_by_id])
    bill = db.relationship("Bill", back_populates="prescription")
    items = db.relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")

    STATUS_LABELS = {
        "awaiting_payment": "Awaiting payment (Cashier)",
        "ready_to_dispense": "Paid - ready to dispense",
        "dispensed": "Dispensed",
        "cancelled": "Cancelled",
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def total(self):
        return money(sum(i.line_total for i in self.items))


class PrescriptionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescription.id"), nullable=False)
    drug_id = db.Column(db.Integer, db.ForeignKey("drug.id"))
    drug_name = db.Column(db.String(160), nullable=False)
    dosage = db.Column(db.String(80))
    frequency = db.Column(db.String(80))
    duration = db.Column(db.String(80))
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False, default=0.0)

    prescription = db.relationship("Prescription", back_populates="items")
    drug = db.relationship("Drug")

    @property
    def line_total(self):
        return money(self.quantity * self.unit_price)


class TreatmentOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prescription_item_id = db.Column(db.Integer, db.ForeignKey("prescription_item.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    dose = db.Column(db.String(80), nullable=False)
    route = db.Column(db.String(30), nullable=False)
    frequency = db.Column(db.String(80), nullable=False)
    duration = db.Column(db.String(80), nullable=False)
    instructions = db.Column(db.Text)
    status = db.Column(db.String(20), default="active", nullable=False)
    stopped_at = db.Column(db.DateTime)
    stopped_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    stop_reason = db.Column(db.String(500))

    prescription_item = db.relationship("PrescriptionItem")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    stopped_by = db.relationship("User", foreign_keys=[stopped_by_id])


class TreatmentAdministration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("treatment_order.id"), nullable=False, index=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recorded_at = db.Column(db.DateTime, default=now, nullable=False)
    administered_at = db.Column(db.DateTime, nullable=False)
    outcome = db.Column(db.String(20), nullable=False)
    dose = db.Column(db.String(80))
    route = db.Column(db.String(30))
    notes = db.Column(db.Text)
    signature = db.Column(db.String(120), nullable=False)
    submission_token = db.Column(db.String(64), unique=True, nullable=False)

    order = db.relationship("TreatmentOrder")
    recorded_by = db.relationship("User")


class StoreItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60))
    unit = db.Column(db.String(30), default="pcs")
    quantity = db.Column(db.Integer, nullable=False, default=0)
    reorder_level = db.Column(db.Integer, default=5)
    location = db.Column(db.String(80))

    @property
    def is_low(self):
        return self.quantity <= (self.reorder_level or 0)


class StoreMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("store_item.id"), nullable=False)
    change = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer, nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # opening, received, issued, adjustment
    department = db.Column(db.String(80))
    note = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)

    item = db.relationship("StoreItem")
    user = db.relationship("User")


class CleaningTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    area = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    due_date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(20), default="pending")  # pending, done
    remark = db.Column(db.String(255))
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)
    completed_at = db.Column(db.DateTime)

    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])


class DoctorAssignment(db.Model):
    """Audit trail of who assigned (or re-assigned) a doctor to a visit."""
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey("visit.id"), nullable=False)
    from_doctor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    to_doctor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=now)

    visit = db.relationship("Visit", backref=db.backref("assignments", order_by="desc(DoctorAssignment.created_at)"))
    from_doctor = db.relationship("User", foreign_keys=[from_doctor_id])
    to_doctor = db.relationship("User", foreign_keys=[to_doctor_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])


class EmergencyDrug(db.Model):
    """Emergency drugs kept in the nurses' office (separate from pharmacy stock)."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    form = db.Column(db.String(40))
    strength = db.Column(db.String(40))
    unit = db.Column(db.String(30), default="unit")
    quantity = db.Column(db.Integer, nullable=False, default=0)
    reorder_level = db.Column(db.Integer, default=5)
    batch_no = db.Column(db.String(40))
    expiry_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)

    label = Drug.label
    is_low = Drug.is_low
    is_expired = Drug.is_expired
    expires_soon = Drug.expires_soon


class EmergencyDrugUse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("emergency_drug.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    visit_id = db.Column(db.Integer, db.ForeignKey("visit.id"))
    quantity = db.Column(db.Integer, nullable=False)
    dose = db.Column(db.String(60))
    route = db.Column(db.String(30))
    reason = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text)
    witness = db.Column(db.String(120))
    administered_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now)

    drug = db.relationship("EmergencyDrug")
    patient = db.relationship("Patient", backref=db.backref("emergency_drug_uses",
                                                            order_by="desc(EmergencyDrugUse.created_at)"))
    visit = db.relationship("Visit")
    administered_by = db.relationship("User")


class EmergencyStockMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("emergency_drug.id"), nullable=False)
    change = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer, nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # opening, received, used, expired, damaged, adjustment
    note = db.Column(db.String(255))
    use_id = db.Column(db.Integer, db.ForeignKey("emergency_drug_use.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)

    drug = db.relationship("EmergencyDrug", backref=db.backref("movements",
                                                               order_by="desc(EmergencyStockMovement.id)"))
    use = db.relationship("EmergencyDrugUse")
    user = db.relationship("User")

    KINDS = {"opening": "Opening stock", "received": "Received", "used": "Used on patient",
             "expired": "Expired - removed", "damaged": "Damaged / lost", "adjustment": "Count adjustment"}

    @property
    def kind_label(self):
        return self.KINDS.get(self.kind, self.kind)


class AncProfile(db.Model):
    """Ante-natal (ANC) booking card - one per pregnancy."""
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    status = db.Column(db.String(20), default="active")  # active, delivered, closed
    consultant_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    gravida = db.Column(db.String(10))
    para = db.Column(db.String(10))
    ethnic_group = db.Column(db.String(60))
    occupation = db.Column(db.String(80))
    husband_occupation = db.Column(db.String(80))
    special_points = db.Column(db.Text)
    past_obstetric_history = db.Column(db.Text)
    past_medical_history = db.Column(db.Text)
    family_history = db.Column(db.Text)
    lmp = db.Column(db.Date)
    edd = db.Column(db.Date)
    quickening_date = db.Column(db.Date)
    height = db.Column(db.String(15))
    weight = db.Column(db.String(15))
    # history review at booking
    hx_oedema = db.Column(db.String(120))
    hx_headache = db.Column(db.String(120))
    hx_bowels = db.Column(db.String(120))
    hx_breath = db.Column(db.String(120))
    hx_micturition = db.Column(db.String(120))
    hx_discharge = db.Column(db.String(120))
    # first examination
    ex_teeth = db.Column(db.String(120))
    ex_breasts = db.Column(db.String(120))
    ex_lungs = db.Column(db.String(120))
    ex_heart = db.Column(db.String(120))
    ex_varicose = db.Column(db.String(120))
    ex_pelvics = db.Column(db.String(120))
    ex_cervical = db.Column(db.String(120))
    ex_observations = db.Column(db.Text)
    ex_date = db.Column(db.Date)
    ex_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    # booking investigations
    inv_blood_group = db.Column(db.String(40))
    inv_rhesus = db.Column(db.String(40))
    inv_antibodies = db.Column(db.String(60))
    inv_genotype = db.Column(db.String(40))
    inv_vdrl = db.Column(db.String(40))
    inv_rtv = db.Column(db.String(60))
    inv_others = db.Column(db.String(120))
    inv_date = db.Column(db.Date)
    # examination at 35/7 weeks
    exam_head_brim = db.Column(db.String(120))
    exam_pelvic_capacity = db.Column(db.String(120))
    exam_date = db.Column(db.Date)
    exam_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    notes = db.Column(db.Text)
    booked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    delivered_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now)

    patient = db.relationship("Patient", back_populates="anc_profiles")
    consultant = db.relationship("User", foreign_keys=[consultant_id])
    ex_by = db.relationship("User", foreign_keys=[ex_by_id])
    exam_by = db.relationship("User", foreign_keys=[exam_by_id])
    booked_by = db.relationship("User", foreign_keys=[booked_by_id])
    visits = db.relationship("AncVisit", back_populates="anc", cascade="all, delete-orphan",
                             order_by="AncVisit.visit_date, AncVisit.id")

    STATUS_LABELS = {"active": "Active pregnancy", "delivered": "Delivered", "closed": "Closed"}

    # (field name, label) pairs used to render the booking history review on the card
    HISTORY_FIELDS = [("hx_oedema", "Oedema"), ("hx_headache", "Headache"), ("hx_bowels", "Bowels"),
                      ("hx_breath", "Breath"), ("hx_micturition", "Micturition"), ("hx_discharge", "Discharge")]
    EXAM_FIELDS = [("ex_teeth", "Teeth"), ("ex_breasts", "Breasts"), ("ex_lungs", "Lungs"),
                   ("ex_heart", "Heart"), ("ex_varicose", "Varicose veins"), ("ex_pelvics", "Pelvics"),
                   ("ex_cervical", "Cervical smear")]
    INVESTIGATIONS = [("inv_blood_group", "ABO Blood Group"), ("inv_rhesus", "Rhesus Blood Group"),
                      ("inv_antibodies", "Anti-Bodies"), ("inv_genotype", "Genotype"), ("inv_vdrl", "VDRL"),
                      ("inv_rtv", "RTV"), ("inv_others", "Others")]

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    def gest_age(self, on=None):
        """Gestational age like '24w 3d' computed from LMP."""
        if not self.lmp:
            return ""
        days = ((on or date.today()) - self.lmp).days
        if days < 0:
            return ""
        return f"{days // 7}w {days % 7}d"

    @property
    def gest_age_today(self):
        return self.gest_age()

    @property
    def next_visit(self):
        for v in reversed(self.visits):
            if v.next_visit:
                return v.next_visit
        return None


class AncVisit(db.Model):
    """One row of the ante-natal follow-up grid."""
    id = db.Column(db.Integer, primary_key=True)
    anc_id = db.Column(db.Integer, db.ForeignKey("anc_profile.id"), nullable=False)
    visit_date = db.Column(db.Date, nullable=False, default=date.today)
    gest_age = db.Column(db.String(15))
    weight = db.Column(db.String(15))
    urine_alb = db.Column(db.String(30))
    urine_sugar = db.Column(db.String(30))
    bp = db.Column(db.String(15))
    sfh = db.Column(db.String(15))
    presentation = db.Column(db.String(80))  # presentation / position / descent
    fhr = db.Column(db.String(20))
    oedema = db.Column(db.String(30))
    pcv = db.Column(db.String(15))
    next_visit = db.Column(db.Date)
    seen_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=now)

    anc = db.relationship("AncProfile", back_populates="visits")
    seen_by = db.relationship("User")


STATIONS = ("Nursing Station 1", "Nursing Station 2", "Theatre")
REQUISITION_STATUSES = {"pending": "Pending pharmacy", "issued": "Issued", "rejected": "Rejected"}


class StationRequisition(db.Model):
    """A ward/station request to pharmacy for drugs and consumables."""
    id = db.Column(db.Integer, primary_key=True)
    station = db.Column(db.String(40), nullable=False)          # one of STATIONS
    requested_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")        # pending / issued / rejected
    note = db.Column(db.String(255))
    actioned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    actioned_at = db.Column(db.DateTime)
    action_note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=now)

    requested_by = db.relationship("User", foreign_keys=[requested_by_id])
    actioned_by = db.relationship("User", foreign_keys=[actioned_by_id])
    items = db.relationship("RequisitionItem", back_populates="requisition",
                            cascade="all, delete-orphan", order_by="RequisitionItem.id")

    @property
    def status_label(self):
        return REQUISITION_STATUSES.get(self.status, self.status)

    @property
    def total_issued(self):
        return sum(i.quantity_issued or 0 for i in self.items)

    @property
    def total_requested(self):
        return sum(i.quantity_requested for i in self.items)


class RequisitionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requisition_id = db.Column(db.Integer, db.ForeignKey("station_requisition.id"), nullable=False)
    drug_id = db.Column(db.Integer, db.ForeignKey("drug.id"))   # None for free-text items
    item_name = db.Column(db.String(160), nullable=False)
    quantity_requested = db.Column(db.Integer, nullable=False)
    quantity_issued = db.Column(db.Integer)                     # set when pharmacy issues
    note = db.Column(db.String(160))

    requisition = db.relationship("StationRequisition", back_populates="items")
    drug = db.relationship("Drug")


EXPENSE_METHODS = {"cash": "Cash", "bank": "Bank"}
EXPENSE_CATEGORIES = ("Medical supplies", "Food & kitchen", "Utilities", "Fuel & transport",
                      "Repairs & maintenance", "Cleaning & sanitation", "Stationery & printing",
                      "Salaries & wages", "Bank charges", "Miscellaneous")


class Expense(db.Model):
    """A general running expense paid from cash or the bank account."""
    id = db.Column(db.Integer, primary_key=True)
    expense_date = db.Column(db.Date, nullable=False, default=date.today)
    category = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    method = db.Column(db.String(10), nullable=False)           # cash / bank
    amount = db.Column(db.Float, nullable=False)
    payee = db.Column(db.String(120))
    reference = db.Column(db.String(80))
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now)

    recorded_by = db.relationship("User")

    @property
    def method_label(self):
        return EXPENSE_METHODS.get(self.method, self.method)


IOU_STATUSES = {"outstanding": "Outstanding", "partial": "Partly settled", "settled": "Settled"}


class StaffIou(db.Model):
    """Money advanced to a staff member, to be repaid or deducted from salary."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    settled_amount = db.Column(db.Float, nullable=False, default=0.0)
    reason = db.Column(db.String(255), nullable=False)
    method = db.Column(db.String(10), nullable=False)           # cash / bank it was paid from
    expense_id = db.Column(db.Integer, db.ForeignKey("expense.id"))  # matching expenses entry
    issued_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now)

    user = db.relationship("User", foreign_keys=[user_id])
    issued_by = db.relationship("User", foreign_keys=[issued_by_id])
    expense = db.relationship("Expense")
    settlements = db.relationship("IouSettlement", back_populates="iou",
                                 cascade="all, delete-orphan", order_by="IouSettlement.id")

    @property
    def remaining(self):
        return round(self.amount - self.settled_amount, 2)

    @property
    def status(self):
        if self.settled_amount <= 0:
            return "outstanding"
        return "settled" if self.settled_amount >= self.amount else "partial"

    @property
    def status_label(self):
        return IOU_STATUSES[self.status]


class IouSettlement(db.Model):
    """One repayment or salary deduction applied against an IOU."""
    id = db.Column(db.Integer, primary_key=True)
    iou_id = db.Column(db.Integer, db.ForeignKey("staff_iou.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    kind = db.Column(db.String(20), nullable=False)             # salary_deduction / repayment
    method = db.Column(db.String(10))                           # cash / bank for repayments
    note = db.Column(db.String(160))
    salary_payment_id = db.Column(db.Integer, db.ForeignKey("salary_payment.id"))
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now)

    iou = db.relationship("StaffIou", back_populates="settlements")
    salary_payment = db.relationship("SalaryPayment", back_populates="iou_settlements")
    recorded_by = db.relationship("User")

    @property
    def kind_label(self):
        return "Salary deduction" if self.kind == "salary_deduction" else "Repayment"


class SalaryPayment(db.Model):
    """A staff salary payment for one month (period 'YYYY-MM')."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    period = db.Column(db.String(7), nullable=False)            # e.g. 2026-11
    gross = db.Column(db.Float, nullable=False)
    iou_deduction = db.Column(db.Float, nullable=False, default=0.0)
    net = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(10), nullable=False)           # cash / bank
    note = db.Column(db.String(255))
    expense_id = db.Column(db.Integer, db.ForeignKey("expense.id"))
    paid_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now)
    __table_args__ = (db.UniqueConstraint("user_id", "period", name="uq_salary_user_period"),)

    user = db.relationship("User", foreign_keys=[user_id])
    paid_by = db.relationship("User", foreign_keys=[paid_by_id])
    expense = db.relationship("Expense")
    iou_settlements = db.relationship("IouSettlement", back_populates="salary_payment")

    @property
    def period_label(self):
        return datetime.strptime(self.period, "%Y-%m").strftime("%B %Y")

    @property
    def method_label(self):
        return EXPENSE_METHODS.get(self.method, self.method)
