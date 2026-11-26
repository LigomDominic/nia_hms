# NIA HOSPITAL — Hospital Management System (Flask)

Light black + light green themed HMS with a public landing page and role-based staff dashboards.

## Run it (Windows)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```
Open http://127.0.0.1:5000 . The SQLite database is created at `instance/hms.db` and seeded on first run.
(macOS/Linux: `source .venv/bin/activate`.)

Demo logins (password `password123`): `admin`, `cashier`, `doctor`, `visiting`, `nurse`, `lab`, `pharmacist`, `store`, `cleaner`.
Change passwords (or create real staff under Admin → Staff & Users) before going live, and set `SECRET_KEY`.

## Workflow
1. **Cashier / Admin only** register new patients → unique hospital ID (`NIA-000001`…), card fee collected, doctor (or visiting doctor) assigned. Consultation fee is optional per visit. Returning patients: *New visit → assign doctor* on their profile.
2. **Nurse** records vitals in the vitals queue.
3. **Doctor** consults, writes notes/diagnosis, requests lab tests and prescribes drugs. Each request becomes a bill posted to the Cashier.
4. **Cashier** collects payment (cash / POS / transfer / wallet). Once a bill is fully paid it is automatically posted to the **Lab** (tests) or **Pharmacy** (drugs).
5. **Lab** enters results → posted back to the doctor (shows as *New lab results*) and emailed to the patient, or kept for **manual collection** (print + *Mark collected*).
6. **Pharmacy** dispenses only paid prescriptions; stock is deducted automatically.

## E-Wallet
Cashier funds a patient's wallet (Profile → *Fund / manage wallet*, or at registration). Every new bill is auto-charged from the wallet — fully (service goes straight to Lab/Pharmacy) or partially (remainder waits at the cashier). A deposit can also settle outstanding bills immediately. Refunds and cancelled bills are recorded on the wallet statement.

## Patient lookup
Type a hospital ID (or name/phone) in the top search bar: you get an account-style view — status, wallet balance, outstanding bills, current medication, visits, lab results, prescriptions, payments and the wallet statement.

## Other modules
- Pharmacy inventory: drugs, prices, batches, expiry, reorder alerts, restock/remove, stock card.
- General store: items, receive stock, issue to departments, bin card, low-stock alerts.
- Admin: staff/users & roles, card & consultation fees, lab test catalog & prices, financial reports, cleaning task assignment.
- Cleaners: see assigned areas and mark them done.

## Hospital numbers
New patients get a unique hospital number like `NIA-10/26-4821` (prefix - registration month/year - 4 random digits).
Every number is checked for uniqueness. The prefix and format (month/year, compact `NIA-1026-4821`, or running
`NIA-000123`) can be changed in Admin → App Settings → Hospital; existing numbers never change.

## Lab Test Catalog (Admin → Lab Test Catalog)
Admin manages the tests the laboratory carries out: add, edit (name, category, sample, unit, reference range, price),
activate/deactivate and delete. Paste many tests at once, one per line: `Name | Category | Sample | Unit | Reference | Price`
(or copy rows from Excel). Tests already used on patients are deactivated instead of deleted so old results stay intact.
A fresh install starts with an empty catalog; set `SEED_SAMPLE_LAB_TESTS=1` to load the 10 demo tests.
Doctors see active tests grouped by category. "Remove sample tests" clears the demo tests from older databases.

## Voice typing (speech to text)
Doctors (and nurses/lab) can dictate instead of typing: click the microphone in the
presenting complaint, notes, diagnosis, lab notes or emergency-drug reason boxes and speak.
Say "full stop", "comma", "question mark" or "new line" for punctuation. Click the mic again to stop.
- Works in Google Chrome or Microsoft Edge, with an internet connection (the browser's speech service converts the audio).
- Open the app on `http://127.0.0.1:5000` / `http://localhost:5000` or over https; browsers block the microphone on plain http LAN addresses.
- Allow microphone access the first time the browser asks.

## App Settings (Admin → App Settings)
- **Hospital**: name, tagline, address, phone, email, patient ID prefix (new patients only)
- **Theme**: light black & light green (default), navy & blue, charcoal & teal, slate & lavender, graphite & rose
- **Currency & fees**: symbol, code, symbol position, decimals, card and consultation fees
- **Documents**: number prefixes for receipts, lab results and prescriptions, digits, footer note, show address / wallet balance
- **Printer**: receipt paper (A4, A5, Letter, 80 mm or 58 mm thermal), report paper, orientation, margins, auto-print receipts after payment
  (tip: start Chrome with `--kiosk-printing` on the cashier PC to print straight to the default printer)
- **Date & time**: date format and 12/24-hour time
- **Voice typing**: on/off, language/accent (e.g. English (Nigeria)), spoken punctuation

## Configuration (environment variables)
`SECRET_KEY`, `HOSPITAL_NAME` (default NIA HOSPITAL), `PATIENT_ID_PREFIX` (default NIA), `CURRENCY` (default ₦), `DATABASE_URL`.
Email for lab results: `MAIL_SERVER`, `MAIL_PORT` (587), `MAIL_USE_TLS` (1), `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_SENDER`. For Gmail use an App Password.

## Tests
`pip install pytest` then `python -m pytest tests`.
