"""Billing, payments and e-wallet logic.

Every chargeable service creates a Bill through ``create_bill``. The patient's
e-wallet is charged automatically (fully or partially) the moment a bill is
raised; any remainder waits at the cashier. When a bill becomes fully paid the
linked lab request / prescription is released to the Lab / Pharmacy.
"""
from .extensions import db
from .models import Bill, Payment, WalletTransaction, money, now


class BillingError(Exception):
    pass


def _wallet_entry(patient, kind, amount, user, description, bill=None, method=None, reference=None):
    delta = amount if kind in ("deposit", "refund") else -amount
    patient.wallet_balance = money(patient.wallet_balance + delta)
    tx = WalletTransaction(
        patient=patient,
        kind=kind,
        amount=money(amount),
        balance_after=patient.wallet_balance,
        description=description,
        bill=bill,
        method=method,
        reference=reference,
        performed_by=user,
    )
    db.session.add(tx)
    return tx


def _release(bill, user):
    """Called once a bill is fully paid: route the service to its department."""
    bill.status = "paid"
    bill.paid_at = now()
    if bill.lab_request is not None and bill.lab_request.status == "awaiting_payment":
        bill.lab_request.status = "sent_to_lab"
        bill.lab_request.posted_to_lab_at = now()
        bill.lab_request.posted_by = user
    if bill.prescription is not None and bill.prescription.status == "awaiting_payment":
        bill.prescription.status = "ready_to_dispense"
        bill.prescription.posted_at = now()


def _apply(bill, amount, method, user, reference=None):
    amount = money(amount)
    payment = Payment(
        bill=bill, patient=bill.patient, amount=amount, method=method, reference=reference, received_by=user
    )
    db.session.add(payment)
    bill.amount_paid = money(bill.amount_paid + amount)
    if bill.balance <= 0:
        _release(bill, user)
    else:
        bill.status = "part_paid"
    return payment


def charge_from_wallet(bill, user):
    """Deduct as much of the bill as the wallet can cover. Returns amount taken."""
    patient = bill.patient
    take = money(min(patient.wallet_balance, bill.balance))
    if take <= 0 or bill.status in ("paid", "cancelled"):
        return 0.0
    _wallet_entry(patient, "debit", take, user, f"Auto-charge: {bill.description}", bill=bill)
    _apply(bill, take, "wallet", user, reference="AUTO")
    return take


def create_bill(patient, category, description, amount, user, visit=None, record=None, auto_wallet=True):
    """Raise a bill. ``record`` (LabRequest / Prescription) is linked so payment can release it."""
    bill = Bill(
        patient=patient,
        visit=visit,
        category=category,
        description=description,
        amount=money(amount),
        created_by=user,
    )
    db.session.add(bill)
    if record is not None:
        record.bill = bill
    db.session.flush()
    if bill.amount <= 0:
        _release(bill, user)
    elif auto_wallet:
        charge_from_wallet(bill, user)
    return bill


def record_payment(bill, amount, method, user, reference=None):
    amount = money(amount)
    if bill.status in ("paid", "cancelled"):
        raise BillingError("This bill is already settled.")
    if amount <= 0:
        raise BillingError("Enter an amount greater than zero.")
    if amount > bill.balance:
        raise BillingError(f"Amount is more than the outstanding balance ({bill.balance:,.2f}).")
    if method == "wallet":
        if amount > bill.patient.wallet_balance:
            raise BillingError("Insufficient wallet balance.")
        _wallet_entry(bill.patient, "debit", amount, user, f"Payment: {bill.description}", bill=bill)
    return _apply(bill, amount, method, user, reference)


def deposit_to_wallet(patient, amount, method, user, reference=None, apply_to_outstanding=True):
    amount = money(amount)
    if amount <= 0:
        raise BillingError("Enter a deposit amount greater than zero.")
    if method == "wallet":
        raise BillingError("Choose how the money was received (cash, POS or transfer).")
    _wallet_entry(patient, "deposit", amount, user, "Wallet deposit", method=method, reference=reference)
    covered = 0.0
    if apply_to_outstanding:
        for bill in sorted(patient.bills, key=lambda b: b.created_at):
            if bill.status in ("unpaid", "part_paid"):
                covered += charge_from_wallet(bill, user)
            if patient.wallet_balance <= 0:
                break
    return money(covered)


def withdraw_from_wallet(patient, amount, user, reason):
    amount = money(amount)
    if amount <= 0 or amount > patient.wallet_balance:
        raise BillingError("Refund amount must be between 0 and the wallet balance.")
    _wallet_entry(patient, "debit", amount, user, f"Refund to patient: {reason}")


def cancel_bill(bill, user):
    if bill.amount_paid > 0:
        # money already taken goes back to the wallet
        _wallet_entry(bill.patient, "refund", bill.amount_paid, user, f"Refund for cancelled bill #{bill.id}", bill=bill)
    bill.status = "cancelled"
