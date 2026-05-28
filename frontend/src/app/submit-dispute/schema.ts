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

export const formSchema = z.object({
  // Step 1
  customer_name: z.string().min(2, "Full name is required"),
  customer_id: z.string().min(4, "Customer ID is required"),
  email: z.string().email("Enter a valid email address"),
  phone: z.string().min(10, "Enter a valid 10-digit phone number"),

  // Step 2 core
  transaction_id: z.string().min(4, "Transaction ID is required"),
  transaction_type: z.enum(TX_TYPES, { required_error: "Select a transaction type" }),
  merchant: z.string().min(1, "Merchant / payee name is required"),
  amount: z.coerce
    .number()
    .positive("Amount must be greater than 0"),
  currency: z.string().default("INR"),
  transaction_date: z.string().min(1, "Transaction date is required"),
  transaction_time: z.string().optional(),

  // Type-specific optional fields
  last_4_digits: z.string().max(4).optional(),
  card_network: z.string().optional(),
  transaction_mode: z.string().optional(),
  merchant_country: z.string().optional(),
  authorization_code: z.string().optional(),
  billing_currency: z.string().optional(),
  is_international: z.boolean().optional(),
  cash_dispensed: z.boolean().optional(),
  partial_cash: z.boolean().optional(),
  atm_id: z.string().optional(),
  atm_location: z.string().optional(),
  atm_bank: z.string().optional(),
  merchant_location: z.string().optional(),
  utr_number: z.string().optional(),
  upi_id: z.string().optional(),
  psp_app: z.string().optional(),
  linked_bank: z.string().optional(),
  receiver_vpa: z.string().optional(),
  device_platform: z.string().optional(),
  beneficiary_account: z.string().optional(),
  ifsc_code: z.string().optional(),
  beneficiary_bank: z.string().optional(),
  wallet_provider: z.string().optional(),
  linked_mobile: z.string().optional(),
  wallet_transaction_id: z.string().optional(),
  merchant_website: z.string().optional(),
  order_id: z.string().optional(),
  delivery_status: z.string().optional(),
  tracking_id: z.string().optional(),
  refund_request_status: z.string().optional(),

  // Step 3
  dispute_reason: z.string().min(5, "Select a dispute reason"),
  customer_comment: z
    .string()
    .min(10, "Describe the issue (minimum 10 characters)")
    .max(2000),
  fraud_selected: z.boolean().default(false),

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
  fraud_additional_details: z.string().optional(),
});

export type FormValues = z.infer<typeof formSchema>;
