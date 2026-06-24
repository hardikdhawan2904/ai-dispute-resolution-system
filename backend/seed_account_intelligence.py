"""
Seed realistic account_events, customer_devices, and beneficiaries
for all 1,000 bank customers.

Preserves existing fraud demo data for CUST-00002 (Komal Mishra).
Run once from backend/: python seed_account_intelligence.py
"""
import os, random, uuid
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from database.database import SessionLocal, init_db
from database.models import (
    BankCustomer, Transaction, AccountEvent,
    CustomerDevice, Beneficiary,
)

random.seed(42)   # reproducible
init_db()

db = SessionLocal()

# ── Protect fraud demo cases ──────────────────────────────────────────────────
PROTECTED_CUSTOMERS = {"CUST-00002"}   # Komal Mishra — ATO demo

now = datetime.now(timezone.utc)

def rdate(days_ago_max: int, days_ago_min: int = 0) -> datetime:
    """Random UTC datetime between days_ago_min and days_ago_max days ago."""
    offset = random.randint(
        int(days_ago_min * 24 * 3600),
        int(days_ago_max * 24 * 3600),
    )
    return now - timedelta(seconds=offset)

def eid() -> str:
    return "EVT-" + uuid.uuid4().hex[:10].upper()

# ── Load all customers and their existing transaction device_ids ──────────────
customers = db.query(BankCustomer).all()
print(f"Seeding account intelligence for {len(customers)} customers...")

# Track what's already in the DB to avoid duplicates
existing_events   = {e.event_id for e in db.query(AccountEvent).all()}
existing_devices  = {(d.customer_id, d.device_id) for d in db.query(CustomerDevice).all()}
existing_benes    = {(b.customer_id, b.beneficiary_name.lower()) for b in db.query(Beneficiary).all()}

# ── Common device name pools ──────────────────────────────────────────────────
IOS_NAMES  = ["iPhone 12", "iPhone 13", "iPhone 14", "iPhone 15", "iPhone SE"]
AND_NAMES  = ["Samsung Galaxy S21", "Samsung Galaxy S23", "OnePlus 11", "Pixel 7", "Redmi Note 12"]
WEB_NAMES  = ["Chrome/Windows", "Firefox/Windows", "Chrome/Mac", "Safari/Mac", "Edge/Windows"]
SDK_NAMES  = ["PhonePe App", "GPay App", "Paytm App", "BHIM App", "Bank Mobile App"]

DEVICE_POOLS = {
    "IOS": IOS_NAMES, "AND": AND_NAMES,
    "WEB": WEB_NAMES, "SDK": SDK_NAMES,
}

# ── Common beneficiary names ──────────────────────────────────────────────────
COMMON_BENES = [
    "Amazon", "Flipkart", "Swiggy", "Zomato", "Ola", "Uber",
    "Netflix", "Hotstar", "YouTube Premium", "Spotify",
    "Electricity Board", "Gas Agency", "Water Board", "Mobile Recharge",
    "LIC Premium", "SIP Investment", "Mutual Fund",
    "Parent Transfer", "Rent Payment", "Salary Advance",
    "IRCTC", "MakeMyTrip", "Cleartrip", "BookMyShow",
    "Medical Store", "Hospital", "Gym Membership",
]

# ── Rare event candidates (only ~5% of customers) ────────────────────────────
rare_customers = set(random.sample(
    [c.customer_id for c in customers if c.customer_id not in PROTECTED_CUSTOMERS],
    k=max(1, len(customers) // 20)
))

events_added   = 0
devices_added  = 0
benes_added    = 0

for cust in customers:
    cid = cust.customer_id

    if cid in PROTECTED_CUSTOMERS:
        print(f"  Skipping {cid} (fraud demo — preserved)")
        continue

    # ── Build device list from transaction history ─────────────────────────────
    txn_devices = (
        db.query(Transaction.device_id, Transaction.transaction_date, Transaction.location)
        .filter(Transaction.customer_id == cid, Transaction.device_id != None)
        .order_by(Transaction.transaction_date)
        .all()
    )

    # Register historical devices as trusted (already done but topped up here)
    registered_this_customer: list[str] = []
    for td_id, td_date, td_loc in txn_devices:
        key = (cid, td_id)
        if key not in existing_devices:
            prefix = td_id.split("-")[0] if "-" in td_id else "WEB"
            dname  = random.choice(DEVICE_POOLS.get(prefix, WEB_NAMES))
            db.add(CustomerDevice(
                device_id   = td_id,
                customer_id = cid,
                device_name = dname,
                first_seen  = td_date,
                last_seen   = td_date,
                trusted     = True,
                location    = td_loc,
            ))
            existing_devices.add(key)
            devices_added += 1
        registered_this_customer.append(td_id)

    # ── Generate DEVICE_REGISTERED events for known devices ───────────────────
    for td_id, td_date, _ in txn_devices[:2]:   # register first 1-2 devices
        evt_id = eid()
        if evt_id not in existing_events:
            prefix = td_id.split("-")[0] if "-" in td_id else "WEB"
            dname  = random.choice(DEVICE_POOLS.get(prefix, WEB_NAMES))
            reg_ts = td_date - timedelta(days=random.randint(1, 30))
            db.add(AccountEvent(
                event_id        = evt_id,
                customer_id     = cid,
                event_type      = "DEVICE_REGISTERED",
                event_timestamp = reg_ts,
                metadata_json   = {"device_id": td_id, "device_name": dname},
            ))
            existing_events.add(evt_id)
            events_added += 1

    # ── PASSWORD_RESET (1-3 times over last 18 months) ────────────────────────
    for _ in range(random.randint(1, 3)):
        evt_id = eid()
        reasons = ["scheduled_change", "forgot_password", "security_prompt", "admin_reset"]
        db.add(AccountEvent(
            event_id        = evt_id,
            customer_id     = cid,
            event_type      = "PASSWORD_RESET",
            event_timestamp = rdate(540),   # up to 18 months ago
            metadata_json   = {"reason": random.choice(reasons)},
        ))
        existing_events.add(evt_id)
        events_added += 1

    # ── PROFILE_UPDATED (0-2 times) ───────────────────────────────────────────
    for _ in range(random.randint(0, 2)):
        evt_id = eid()
        fields = ["address", "nominee", "communication_preference", "email_alerts"]
        db.add(AccountEvent(
            event_id        = evt_id,
            customer_id     = cid,
            event_type      = "PROFILE_UPDATED",
            event_timestamp = rdate(400),
            metadata_json   = {"field_updated": random.choice(fields)},
        ))
        existing_events.add(evt_id)
        events_added += 1

    # ── EMAIL_CHANGED (rare — ~15% of customers) ──────────────────────────────
    if random.random() < 0.15:
        evt_id = eid()
        db.add(AccountEvent(
            event_id        = evt_id,
            customer_id     = cid,
            event_type      = "EMAIL_CHANGED",
            event_timestamp = rdate(365),
            metadata_json   = {"reason": "updated_personal_email"},
        ))
        existing_events.add(evt_id)
        events_added += 1

    # ── DEVICE_REMOVED (20% — people lose/replace phones) ────────────────────
    if registered_this_customer and random.random() < 0.20:
        old_dev = registered_this_customer[0]
        evt_id  = eid()
        db.add(AccountEvent(
            event_id        = evt_id,
            customer_id     = cid,
            event_type      = "DEVICE_REMOVED",
            event_timestamp = rdate(180),
            metadata_json   = {"device_id": old_dev, "reason": "device_lost"},
        ))
        existing_events.add(evt_id)
        events_added += 1

    # ── RARE security events (~5% of customers) ───────────────────────────────
    if cid in rare_customers:
        rare_type = random.choice([
            "MOBILE_NUMBER_CHANGED", "SIM_SWAP_DETECTED",
            "FRAUD_ALERT", "ACCOUNT_LOCKED",
        ])
        evt_id = eid()
        db.add(AccountEvent(
            event_id        = evt_id,
            customer_id     = cid,
            event_type      = rare_type,
            event_timestamp = rdate(90),
            metadata_json   = {"auto_detected": True, "source": "security_system"},
        ))
        existing_events.add(evt_id)
        events_added += 1

    # ── Beneficiaries (3-10 per customer) ─────────────────────────────────────
    num_benes  = random.randint(3, 10)
    bene_names = random.sample(COMMON_BENES, min(num_benes, len(COMMON_BENES)))

    for bname in bene_names:
        key = (cid, bname.lower())
        if key not in existing_benes:
            created = rdate(540)
            db.add(Beneficiary(
                customer_id       = cid,
                beneficiary_name  = bname,
                beneficiary_id    = bname.lower().replace(" ", "_") + "@upi",
                created_at        = created,
                last_used_at      = rdate(30, 0),
                transaction_count = random.randint(1, 25),
                trusted           = random.random() > 0.2,
            ))
            existing_benes.add(key)
            benes_added += 1

    # Commit in batches
    if events_added % 2000 == 0:
        db.commit()
        print(f"  ... {events_added} events, {devices_added} devices, {benes_added} beneficiaries")

db.commit()

# ── Summary ───────────────────────────────────────────────────────────────────
print()
total_events  = db.query(AccountEvent).count()
total_devices = db.query(CustomerDevice).count()
total_benes   = db.query(Beneficiary).count()

print("=== SEEDING COMPLETE ===")
print(f"account_events  : {total_events:,}")
print(f"customer_devices: {total_devices:,}")
print(f"beneficiaries   : {total_benes:,}")
print()

# Event type distribution
from sqlalchemy import func
dist = db.query(AccountEvent.event_type, func.count()).group_by(AccountEvent.event_type).all()
print("Event type distribution:")
for etype, cnt in sorted(dist, key=lambda x: -x[1]):
    print(f"  {etype:<30} {cnt:>5}")

db.close()
print()
print("Done. Fraud demo cases (CUST-00002) preserved unchanged.")

