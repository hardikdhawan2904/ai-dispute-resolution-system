import { z } from "zod";

export const TX_TYPES = [
  "Credit Card",
  "Debit Card",
  "UPI",
  "Net Banking",
  "Wallet",
  "POS",
  "ATM",
  "Online Purchase",
  "International",
] as const;
export type TxType = (typeof TX_TYPES)[number];

/** Optional field that can be empty string OR must satisfy regex if filled. */
const optionalRegex = (regex: RegExp, message: string) =>
  z.string().optional().refine((val) => !val || regex.test(val), { message });

export const formSchema = z.object({
  // ── Step 1 — Customer Details ──────────────────────────────────────────────
  customer_id: z
    .string()
    .min(1, "Customer ID is required")
    .regex(/^CUST-\d{4,8}$/i, "Customer ID must be in format CUST-XXXXX"),

  customer_name: z
    .string()
    .min(2, "Full name is required")
    .max(100, "Name must be under 100 characters")
    .regex(
      /^[a-zA-Z][a-zA-Z\s.'\-]{1,99}$/,
      "Name must contain only letters, spaces, hyphens or apostrophes"
    ),

  email: z.string().email("Enter a valid email address"),

  phone: z
    .string()
    .min(1, "Phone number is required"),

  // ── Step 2 — Transaction Details ──────────────────────────────────────────
  transaction_id: z
    .string()
    .min(1, "Transaction ID is required")
    .regex(
      /^[A-Z0-9][A-Z0-9\-]{3,63}$/i,
      "Transaction ID must be alphanumeric (e.g. TXN-00007525)"
    ),

  // transaction_type, merchant, amount, transaction_date are filled manually by the customer.
  // Transaction ID is used to verify the entered details match bank records.
  transaction_type: z.string().min(1, "Transaction type is required"),

  merchant: z.string().min(1, "Merchant / payee name is required"),

  amount: z.coerce
    .number({ invalid_type_error: "Enter a valid amount" })
    .positive("Amount must be greater than 0"),

  currency: z.string().default("INR"),

  transaction_date: z.string().min(1, "Transaction date is required"),

  transaction_time: z.string().optional(),

  // ── Type-specific optional fields ─────────────────────────────────────────
  last_4_digits: z.string().max(4).optional(),
  card_network: z.string().optional(),
  transaction_mode: z.string().optional(),
  merchant_country: z.string().optional(),

  authorization_code: optionalRegex(
    /^[A-Z0-9][A-Z0-9\-]{3,19}$/i,
    "Authorization code must be 4–20 alphanumeric characters (hyphens allowed)"
  ),

  billing_currency: z.string().optional(),
  is_international: z.boolean().optional(),
  cash_dispensed: z.boolean().optional(),
  partial_cash: z.boolean().optional(),

  atm_id: optionalRegex(
    /^[A-Z0-9\-]{3,20}$/i,
    "ATM ID must be 3–20 alphanumeric characters"
  ),

  atm_location: z.string().optional(),
  atm_bank: z.string().optional(),
  merchant_location: z.string().optional(),

  utr_number: optionalRegex(
    /^\d{12,22}$/,
    "UTR number must be 12–22 digits"
  ),

  upi_id: optionalRegex(
    /^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$/,
    "Enter a valid UPI ID (e.g. name@okaxis or 9876543210@paytm)"
  ),

  psp_app: z.string().optional(),
  linked_bank: z.string().optional(),

  receiver_vpa: optionalRegex(
    /^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$/,
    "Enter a valid VPA (e.g. name@upi)"
  ),

  device_platform: z.string().optional(),

  beneficiary_account: optionalRegex(
    /^\d{9,18}$/,
    "Account number must be 9–18 digits"
  ),

  ifsc_code: optionalRegex(
    /^[A-Z]{4}0[A-Z0-9]{6}$/,
    "IFSC must be in format ABCD0123456 (e.g. HDFC0001234)"
  ),

  beneficiary_bank: z.string().optional(),
  wallet_provider: z.string().optional(),

  linked_mobile: optionalRegex(
    /^\d{10}$/,
    "Linked mobile number must be 10 digits"
  ),

  wallet_transaction_id: z.string().optional(),

  merchant_website: optionalRegex(
    /^(https?:\/\/)?([\w\-]+\.)+[\w]{2,}(\/[\w\-._~:/?#[\]@!$&'()*+,;=]*)?$/i,
    "Enter a valid website URL (e.g. https://example.com)"
  ),

  order_id: z.string().optional(),
  delivery_status: z.string().optional(),
  tracking_id: z.string().optional(),
  refund_request_status: z.string().optional(),

  // ── Step 3 — Dispute Description ──────────────────────────────────────────
  dispute_reason: z.string().min(5, "Select a dispute reason"),

  customer_comment: z
    .string()
    .min(10, "Describe the issue (minimum 10 characters)")
    .max(2000, "Description cannot exceed 2000 characters")
    .refine(
      (val) => /[a-zA-Z]{3,}/.test(val),
      "Please describe the issue in words (minimum 3 letters required)"
    ),

  fraud_selected: z.boolean().default(false),

  // Supporting evidence
  otp_received: z.boolean().optional(),
  card_blocked: z.boolean().optional(),
  bank_contacted: z.boolean().optional(),
  transaction_location: z.string().optional(),

  // Fraud indicators
  otp_shared: z.boolean().optional(),
  device_lost: z.boolean().optional(),
  bank_impersonation: z.boolean().optional(),
  remote_access: z.boolean().optional(),
  phishing_link: z.boolean().optional(),
  card_lost: z.boolean().optional(),
  sim_swap_suspected: z.boolean().optional(),
  screen_sharing: z.boolean().optional(),
  unknown_beneficiary: z.boolean().optional(),
  upi_collect_fraud: z.boolean().optional(),
  fraud_additional_details: z
    .string()
    .max(1000, "Additional details cannot exceed 1000 characters")
    .optional(),
});

export type FormValues = z.infer<typeof formSchema>;
