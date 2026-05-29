"""
Generates a realistic bank SMS notification image to use as dispute proof.
"""
from PIL import Image, ImageDraw, ImageFont
import os

# ── Canvas ─────────────────────────────────────────────────────────────────────
W, H = 420, 580
img = Image.new("RGB", (W, H), "#0d0d0d")  # dark phone background
draw = ImageDraw.Draw(img)

# ── Load fonts (fallback to default if custom not available) ───────────────────
def font(size, bold=False):
    try:
        name = "arialbd.ttf" if bold else "arial.ttf"
        return ImageFont.truetype(name, size)
    except Exception:
        try:
            name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
            return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)
        except Exception:
            return ImageFont.load_default()

# ── Status bar ─────────────────────────────────────────────────────────────────
draw.rectangle([0, 0, W, 28], fill="#1a1a1a")
draw.text((14, 6), "9:41 AM", font=font(12), fill="#ffffff")
draw.text((W - 60, 6), "📶 🔋", font=font(12), fill="#ffffff")

# ── SMS header ─────────────────────────────────────────────────────────────────
draw.rectangle([0, 28, W, 80], fill="#1e1e1e")
# Bank logo circle
draw.ellipse([14, 36, 58, 72], fill="#003580")
draw.text((24, 46), "SBI", font=font(13, bold=True), fill="#ffffff")

draw.text((68, 38), "SBI-ALERTS", font=font(15, bold=True), fill="#ffffff")
draw.text((68, 58), "Bank Message", font=font(12), fill="#888888")
draw.text((W - 60, 42), "25 May", font=font(12), fill="#888888")

# ── Message bubble ─────────────────────────────────────────────────────────────
bx0, by0, bx1, by1 = 14, 90, W - 14, 500
# Shadow
draw.rounded_rectangle([bx0+3, by0+3, bx1+3, by1+3], radius=16, fill="#111111")
# Bubble
draw.rounded_rectangle([bx0, by0, bx1, by1], radius=16, fill="#1c2333")

# ── Message content ────────────────────────────────────────────────────────────
tx, ty = 28, 108

def line(text, y_offset, size=14, bold=False, color="#e8e8e8"):
    draw.text((tx, ty + y_offset), text, font=font(size, bold), fill=color)

line("Dear SBI Customer,",            0,  13, color="#aaaaaa")
line("Your A/c **XXXXXX9842 has",    22,  14)
line("been DEBITED with",             42,  14)

# Amount — big and red (unauthorized feel)
draw.text((tx, ty + 68), "₹12,500.00",  font=font(28, bold=True), fill="#ff4444")
draw.text((tx + 155, ty + 76), "debited", font=font(15), fill="#cccccc")

line("on 25-05-2026 at 02:17:34 AM",  110, 13, color="#aaaaaa")
line("(IST) — Ref No. 403592817634",  128, 13, color="#aaaaaa")

line("Info: POS/AMAZON*MERCHANT/",    158, 14)
line("MUMBAI/MH/IN",                  176, 14)

draw.line([(28, ty + 202), (bx1 - 14, ty + 202)], fill="#2e3a55", width=1)

line("Avail Bal: ₹1,847.22",          214, 13, color="#888888")

# Warning line
draw.rounded_rectangle([28, ty + 238, bx1 - 14, ty + 278], radius=8, fill="#2a1a1a")
draw.text((38, ty + 248), "⚠  Not done by you? Call",  font=font(12), fill="#ff8c42")
draw.text((38, ty + 264), "    1800-11-2211 (Toll Free)", font=font(12), fill="#ff8c42")

# Footer
draw.text((tx, ty + 296), "Do NOT share OTP / PIN / CVV",
          font=font(11), fill="#555555")
draw.text((tx, ty + 312), "with anyone. SBI never asks.",
          font=font(11), fill="#555555")

# ── Bottom bar ─────────────────────────────────────────────────────────────────
draw.rectangle([0, H - 52, W, H], fill="#1a1a1a")
draw.text((W // 2 - 20, H - 36), "◀   ●   ■", font=font(14), fill="#555555")

# ── Save ───────────────────────────────────────────────────────────────────────
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_bank_sms.png")
img.save(out)
print(f"Saved: {out}")
print()
print("=" * 60)
print("FORM FIELDS TO FILL IN:")
print("=" * 60)
print("Full Name        : Arjun Sharma")
print("Customer ID      : CUST-ARJ-8842")
print("Email            : arjun.sharma@gmail.com")
print("Phone            : 9876543210")
print()
print("Transaction Type : UPI")
print("Transaction ID   : UTR403592817634")
print("Merchant         : AMAZON*MERCHANT/MUMBAI")
print("Amount           : 12500")
print("Currency         : INR")
print("Date             : 2026-05-25")
print("Time             : 02:17")
print()
print("Dispute Reason   : Unauthorised transaction")
print("Description      : I was asleep when this transaction")
print("                   happened at 2 AM. I never shop on")
print("                   Amazon at that hour. My phone was")
print("                   with me. I did not receive any OTP.")
print()
print("Supporting Evidence:")
print("  OTP Received?  : No")
print("  Card Blocked?  : Yes (blocked next morning)")
print("  Bank Contacted?: Yes (called 1800-11-2211)")
print("  Location       : Mumbai, Maharashtra")
print()
print("Unauthorised Transaction: YES (check the box)")
print()
print("Fraud Questions:")
print("  OTP shared?          : No")
print("  Bank impersonation?  : No")
print("  Remote access app?   : No")
print("  Phishing link?       : No")
print("  SIM swap suspected?  : No")
print("  Device lost/stolen?  : No")
print("  Card lost/stolen?    : No")
print("  Unknown beneficiary? : No")
print("  UPI collect fraud?   : No")
print()
print("PROOF IMAGE: sample_bank_sms.png  <-- upload this")
print("=" * 60)
