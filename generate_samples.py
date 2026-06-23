"""Generate debit card fraud evidence samples with today's date."""
import os
from datetime import date
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from PIL import Image, ImageDraw, ImageFont

TODAY     = date.today()
TODAY_STR = TODAY.strftime('%d-%b-%Y')
PERIOD    = '15-Jun-' + str(TODAY.year) + ' to ' + TODAY_STR
FIR_NO    = 'CC/BLR/' + TODAY.strftime('%m%d') + '/' + str(TODAY.year)

W, H = A4
os.makedirs('samples', exist_ok=True)

def hline(c, y):
    c.setLineWidth(0.5)
    c.line(20*mm, y, 190*mm, y)

def txt(c, x, y, s, size=10, bold=False):
    c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
    c.drawString(x, y, s)
    return y - (size + 4)

# ── 1. Bank Statement ─────────────────────────────────────────────────────────
c = canvas.Canvas('samples/debit_card_bank_statement.pdf', pagesize=A4)
c.setFont('Helvetica-Bold', 16)
c.drawString(20*mm, H-25*mm, 'SecureBank — Account Statement')
c.setFont('Helvetica', 9)
c.drawString(20*mm, H-32*mm, 'Statement Period: ' + PERIOD)
hline(c, H-35*mm)
y = H-45*mm
for lbl, val in [('Account Holder','Deepak Ghosh'),('Account Number','XXXX XXXX 4821'),
                  ('Customer ID','CUST-00001'),('Account Type','Savings Account')]:
    c.setFont('Helvetica-Bold',10); c.drawString(20*mm,y,lbl+' :')
    c.setFont('Helvetica',10);      c.drawString(72*mm,y,val); y -= 14
y -= 6; hline(c, y); y -= 6
c.setFont('Helvetica-Bold',9)
for col,x in [('Date',20),('Description',50),('Debit (INR)',110),('Credit (INR)',145),('Balance (INR)',170)]:
    c.drawString(x*mm,y,col)
y -= 14; hline(c,y); y -= 6
rows = [
    ('15-Jun-'+str(TODAY.year), 'Opening Balance',                     '',          '',          '1,24,580.00'),
    ('17-Jun-'+str(TODAY.year), 'NEFT Rent Payment',                   '18,000.00', '',          '1,06,580.00'),
    ('19-Jun-'+str(TODAY.year), 'POS BigBazaar Bengaluru',             '2,340.00',  '',          '1,04,240.00'),
    ('20-Jun-'+str(TODAY.year), 'Salary Credit',                       '',          '75,000.00', '1,79,240.00'),
    (TODAY_STR,                 'IRCTC Debit Card POS Bengaluru *DISPUTED*','27,915.08','',      '1,51,324.92'),
    (TODAY_STR,                 'SMS Alert TXN-00000005 08:28 AM',     '',          '',          ''),
]
c.setFont('Helvetica',8)
for dt,desc,deb,cr,bal in rows:
    c.drawString(20*mm,y,dt); c.drawString(50*mm,y,desc)
    if deb: c.drawString(110*mm,y,deb)
    if cr:  c.drawString(145*mm,y,cr)
    if bal: c.drawString(170*mm,y,bal)
    y -= 14
hline(c,y-4); y -= 16
c.setFont('Helvetica-Bold',9)
c.drawString(20*mm,y,'** DISPUTED: '+TODAY_STR+'  IRCTC  INR 27,915.08 — NOT AUTHORISED BY CUSTOMER **')
y -= 14
c.setFont('Helvetica',8)
c.drawString(20*mm,y,'Customer report: Card in possession. No OTP/PIN shared. Transaction not initiated by customer.')
y -= 12
c.drawString(20*mm,y,'Generated: '+TODAY_STR+' | Branch: Bengaluru MG Road | IFSC: SECB0001234')
c.save()
print('1/5 Bank Statement   (' + TODAY_STR + ')')

# ── 2. SMS Alert PNG ──────────────────────────────────────────────────────────
img = Image.new('RGB', (600,360), '#1a1a2e')
d = ImageDraw.Draw(img)
try:
    fL = ImageFont.truetype('C:/Windows/Fonts/Arial.ttf', 22)
    fM = ImageFont.truetype('C:/Windows/Fonts/Arial.ttf', 17)
    fS = ImageFont.truetype('C:/Windows/Fonts/Arial.ttf', 14)
except Exception:
    fL = fM = fS = ImageFont.load_default()
d.rounded_rectangle([20,20,580,340], radius=16, fill='#16213e', outline='#0f3460', width=2)
d.text((40,40),  'SecureBank',                                    fill='#4ade80', font=fL)
d.text((40,75),  'TRANSACTION ALERT',                             fill='#94a3b8', font=fS)
d.line([(40,98),(560,98)], fill='#334155', width=1)
d.text((40,112), 'Dear Deepak,',                                  fill='#f8fafc', font=fM)
d.text((40,142), 'INR 27,915.08 debited from A/C XXXX4821',      fill='#fbbf24', font=fM)
d.text((40,172), 'on ' + TODAY_STR + ' at 08:28 AM via Debit Card.', fill='#f8fafc', font=fM)
d.text((40,202), 'Merchant : IRCTC | Ref: TXN-00000005',          fill='#f8fafc', font=fS)
d.text((40,224), 'Location : Bengaluru, KA',                      fill='#f8fafc', font=fS)
d.text((40,246), 'If not you, call 1800-XXX-0000 immediately.',   fill='#ef4444', font=fS)
d.text((40,275), 'Available Balance: INR 1,51,324.92',            fill='#94a3b8', font=fS)
d.text((40,310), TODAY_STR + ', 08:28:43 AM IST',                 fill='#475569', font=fS)
img.save('samples/debit_card_sms_alert.png')
print('2/5 SMS Alert        (' + TODAY_STR + ')')

# ── 3. Police FIR PDF ─────────────────────────────────────────────────────────
c = canvas.Canvas('samples/debit_card_police_fir.pdf', pagesize=A4)
y = H-20*mm
c.setFont('Helvetica-Bold',14); c.drawCentredString(W/2,y,'FIRST INFORMATION REPORT (FIR)')
y -= 8*mm
c.setFont('Helvetica-Bold',11); c.drawCentredString(W/2,y,'Cyber Crime Police Station, Bengaluru')
hline(c,y-4*mm); y -= 16*mm
for lbl,val in [
    ('FIR Number',     FIR_NO),
    ('Date of Filing', TODAY_STR),
    ('Police Station', 'Cyber Crime PS, Bengaluru'),
    ('Section',        'IT Act 2000 Sec 66C 66D | IPC 420'),
    ('Complainant',    'Deepak Ghosh'),
    ('Customer ID',    'CUST-00001'),
    ('Contact',        '7011080630'),
    ('Address',        '45 Indiranagar Bengaluru 560038'),
    ('',               ''),
    ('Incident Date',  TODAY_STR + ' at 08:28 AM'),
    ('Fraud Amount',   'INR 27,915.08'),
    ('Bank',           'SecureBank MG Road Branch Bengaluru'),
    ('Account No',     'XXXX XXXX 4821'),
    ('Merchant',       'IRCTC Indian Railway Catering and Tourism Corp'),
    ('Txn Reference',  'TXN-00000005'),
    ('Txn Type',       'Debit Card POS'),
]:
    if lbl:
        c.setFont('Helvetica-Bold',10); c.drawString(20*mm,y,lbl+' :')
        c.setFont('Helvetica',10);      c.drawString(68*mm,y,val)
    y -= 14
hline(c,y-4); y -= 14
c.setFont('Helvetica-Bold',10); c.drawString(20*mm,y,'Complaint Details:'); y -= 14
c.setFont('Helvetica',9)
for ln in [
    'On ' + TODAY_STR + ' a debit card transaction of INR 27915.08 was made from',
    'account XXXX4821 at IRCTC Bengaluru without knowledge or consent of complainant.',
    'Complainant was in possession of debit card at all times. No OTP or PIN was shared.',
    'Card blocked immediately after discovery. Transaction not initiated by complainant.',
    'FIR filed on ' + TODAY_STR + '. Cyber Crime complaint registered for financial fraud.',
]:
    c.drawString(20*mm,y,ln); y -= 12
y -= 10
c.setFont('Helvetica-Bold',10)
c.drawString(20*mm,y,'Signature of Complainant: ________________      Date: ' + TODAY_STR)
c.save()
print('3/5 Police FIR       (' + TODAY_STR + ')')

# ── 4. Complaint Letter PDF ───────────────────────────────────────────────────
c = canvas.Canvas('samples/debit_card_complaint_letter.pdf', pagesize=A4)
y = H-20*mm
c.setFont('Helvetica-Bold',13)
c.drawCentredString(W/2,y,'FORMAL COMPLAINT — UNAUTHORISED DEBIT CARD TRANSACTION')
hline(c,y-5*mm); y -= 18*mm
letter = [
    'To,', 'The Branch Manager,', 'SecureBank MG Road Branch,', 'Bengaluru 560001',
    '', 'Date: ' + TODAY_STR, '',
    'Subject: Unauthorised Debit Card Transaction — Account XXXX4821 — INR 27,915.08', '',
    'Dear Sir / Madam,', '',
    'I Deepak Ghosh (Customer ID: CUST-00001) holder of Savings Account XXXX XXXX 4821',
    'with SecureBank wish to formally lodge a complaint regarding an unauthorized debit card',
    'transaction debited from my account on ' + TODAY_STR + '.', '',
    'Transaction Details:',
    '  Date and Time : ' + TODAY_STR + ' at 08:28 AM',
    '  Amount        : INR 27,915.08',
    '  Merchant      : IRCTC (Indian Railway Catering)',
    '  Reference     : TXN-00000005',
    '  Type          : Debit Card POS Bengaluru', '',
    'I categorically state that:',
    '  1. I did not authorize or perform this transaction.',
    '  2. My debit card was in my physical possession at all times.',
    '  3. I did not share my card PIN OTP or CVV with anyone.',
    '  4. FIR filed at Cyber Crime PS Bengaluru on ' + TODAY_STR + ' (FIR: ' + FIR_NO + ').',
    '  5. Card blocked immediately upon discovering this transaction.', '',
    'I request you to:',
    '  a) Investigate this fraudulent transaction immediately.',
    '  b) Initiate a chargeback and credit INR 27,915.08 back to my account.',
    '  c) Provide transaction logs merchant terminal details and CCTV if applicable.', '',
    'Attachments: Bank Statement | SMS Alert | Police FIR | Card Copy', '',
    'Yours faithfully,', '', 'Deepak Ghosh', 'Mobile: 7011080630',
    'Email : deepak.ghosh@yahoo.com', 'Date  : ' + TODAY_STR,
]
for t in letter:
    c.setFont('Helvetica-Bold' if t.startswith('Subject') else 'Helvetica', 9)
    c.drawString(20*mm,y,t); y -= 12
    if y < 25*mm: c.showPage(); y = H-20*mm
c.save()
print('4/5 Complaint Letter (' + TODAY_STR + ')')

# ── 5. Card Details PNG ───────────────────────────────────────────────────────
img = Image.new('RGB',(640,380),'#0f172a')
d = ImageDraw.Draw(img)
try:
    fXL = ImageFont.truetype('C:/Windows/Fonts/Arial.ttf',26)
    fL  = ImageFont.truetype('C:/Windows/Fonts/Arial.ttf',20)
    fM  = ImageFont.truetype('C:/Windows/Fonts/Arial.ttf',15)
    fS  = ImageFont.truetype('C:/Windows/Fonts/Arial.ttf',12)
except Exception:
    fXL = fL = fM = fS = ImageFont.load_default()
d.rounded_rectangle([30,30,610,330],radius=20,fill='#1e3a5f',outline='#2563eb',width=2)
d.rounded_rectangle([60,90,130,140],radius=6,fill='#fbbf24')
d.text((50,50), 'SecureBank',          fill='#93c5fd',font=fL)
d.text((50,160),'**** **** **** 4821', fill='#f8fafc',font=fXL)
d.text((50,220),'DEEPAK GHOSH',        fill='#cbd5e1',font=fM)
d.text((50,250),'Valid Thru: 11/27',   fill='#94a3b8',font=fS)
d.text((50,275),'DEBIT',               fill='#4ade80',font=fM)
d.text((400,270),'VISA',               fill='#fbbf24',font=fXL)
d.text((50,310),'Card BLOCKED after fraudulent txn on ' + TODAY_STR + ' INR 27,915.08', fill='#ef4444',font=fS)
img.save('samples/debit_card_details.png')
print('5/5 Card Details     (' + TODAY_STR + ')')
print()
for f in sorted(os.listdir('samples')):
    sz = os.path.getsize('samples/' + f)
    print('  samples/' + f + '  (' + str(sz) + ' bytes)')
