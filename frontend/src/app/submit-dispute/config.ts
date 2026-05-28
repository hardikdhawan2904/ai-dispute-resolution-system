import type { TxType } from "./schema";

export interface ExtraField {
  key: string;
  label: string;
  type: "text" | "select" | "toggle" | "masked-digits";
  options?: string[];
  placeholder?: string;
  help?: string;
  required?: boolean;
  transform?: "uppercase" | "digits-only";
}

export interface TxConfig {
  description: string;
  extraFields: ExtraField[];
  disputeReasons: string[];
  uploadSuggestions: string[];
  contextHelp: string;
}

export const TX_CONFIG: Record<TxType, TxConfig> = {
  "Credit Card": {
    description: "Online, POS, recurring subscription and international card transactions",
    extraFields: [
      {
        key: "last_4_digits",
        label: "Last 4 Digits of Card",
        type: "masked-digits",
        required: true,
        help: "Last 4 digits printed on your card",
      },
      {
        key: "card_network",
        label: "Card Network",
        type: "select",
        options: ["Visa", "Mastercard", "Amex", "RuPay", "Diners"],
        required: false,
      },
      {
        key: "transaction_mode",
        label: "Transaction Mode",
        type: "select",
        options: ["Online CNP", "POS Terminal", "Contactless", "Chip & PIN"],
      },
      {
        key: "merchant_country",
        label: "Merchant Country",
        type: "text",
        placeholder: "e.g. India, USA",
      },
      {
        key: "authorization_code",
        label: "Authorization Code",
        type: "text",
        placeholder: "6-digit auth code from statement",
      },
      {
        key: "is_international",
        label: "International Transaction",
        type: "toggle",
        help: "Was this transaction made with a foreign merchant?",
      },
    ],
    disputeReasons: [
      "Unauthorized card transaction",
      "Card charged twice (duplicate)",
      "Subscription charged after cancellation",
      "Card not present fraud",
      "Incorrect amount charged",
      "EMI conversion without consent",
      "Merchant dispute / service not received",
      "Refund not received",
    ],
    uploadSuggestions: [
      "Credit card statement",
      "Transaction SMS / email alert",
      "Merchant receipt or invoice",
      "Cancellation confirmation email",
    ],
    contextHelp:
      "For credit card disputes, ensure you have the last 4 digits and authorization code from your monthly statement. CNP (Card Not Present) disputes require additional verification.",
  },

  "Debit Card": {
    description: "ATM withdrawals, POS purchases and debit-based payments",
    extraFields: [
      {
        key: "last_4_digits",
        label: "Last 4 Digits of Card",
        type: "masked-digits",
        required: true,
        help: "Last 4 digits printed on your debit card",
      },
      {
        key: "transaction_mode",
        label: "Transaction Mode",
        type: "select",
        options: ["ATM", "POS Terminal", "Online", "Contactless"],
      },
      {
        key: "authorization_code",
        label: "Authorization Code",
        type: "text",
        placeholder: "From bank statement or SMS",
      },
      {
        key: "merchant_location",
        label: "Merchant Location",
        type: "text",
        placeholder: "City / area of the merchant",
      },
      {
        key: "cash_dispensed",
        label: "Was Cash Dispensed?",
        type: "toggle",
        help: "Did the ATM actually release any cash?",
      },
    ],
    disputeReasons: [
      "ATM cash not received",
      "Unauthorized debit transaction",
      "Duplicate debit",
      "Incorrect amount charged",
      "POS dispute",
      "Refund not received",
    ],
    uploadSuggestions: [
      "Bank account statement",
      "ATM receipt",
      "Transaction alert SMS",
      "POS charge slip",
    ],
    contextHelp:
      "Debit card disputes are processed directly against your bank account. Unauthorized transactions must be reported within 3 business days for zero liability under RBI guidelines.",
  },

  UPI: {
    description: "Instant account-to-account transfers via UPI apps and QR payments",
    extraFields: [
      {
        key: "utr_number",
        label: "UTR Number",
        type: "text",
        required: true,
        placeholder: "12-digit UTR",
        help: "12-digit Unique Transaction Reference from your payment app",
      },
      {
        key: "upi_id",
        label: "Your UPI ID",
        type: "text",
        placeholder: "yourname@bank",
      },
      {
        key: "psp_app",
        label: "Payment App Used",
        type: "select",
        options: [
          "Google Pay",
          "PhonePe",
          "Paytm",
          "BHIM",
          "Amazon Pay",
          "Other",
        ],
      },
      {
        key: "linked_bank",
        label: "Linked Bank",
        type: "text",
        placeholder: "e.g. SBI, HDFC, ICICI",
      },
      {
        key: "receiver_vpa",
        label: "Receiver VPA / UPI ID",
        type: "text",
        placeholder: "merchant@upi",
      },
      {
        key: "device_platform",
        label: "Device Platform",
        type: "select",
        options: ["Android", "iOS", "Web"],
      },
    ],
    disputeReasons: [
      "Unauthorized UPI transfer",
      "Wrong beneficiary credited",
      "Merchant payment failed but amount debited",
      "UPI scam / social engineering fraud",
      "QR code fraud",
      "Collect request fraud",
      "Refund pending",
      "Duplicate payment",
    ],
    uploadSuggestions: [
      "UPI transaction screenshot",
      "Bank statement showing debit",
      "Chat or call records with fraudster",
      "QR code screenshot (if applicable)",
    ],
    contextHelp:
      "UPI disputes are coordinated between your PSP (payment service provider) and the beneficiary bank via NPCI. The UTR number is critical for tracing the transaction. You can find it in your payment app under transaction history.",
  },

  "Net Banking": {
    description: "NEFT, RTGS, IMPS and online banking fund transfers",
    extraFields: [
      {
        key: "beneficiary_account",
        label: "Beneficiary Account",
        type: "text",
        required: true,
        help: "Last 4 digits of the beneficiary account are sufficient",
        placeholder: "XXXXXX1234",
      },
      {
        key: "ifsc_code",
        label: "Beneficiary IFSC Code",
        type: "text",
        required: true,
        placeholder: "e.g. HDFC0001234",
        transform: "uppercase",
      },
      {
        key: "beneficiary_bank",
        label: "Beneficiary Bank",
        type: "text",
        placeholder: "e.g. HDFC Bank",
      },
      {
        key: "device_platform",
        label: "Banking Platform",
        type: "select",
        options: ["Desktop Browser", "Mobile Browser", "Banking App"],
      },
    ],
    disputeReasons: [
      "Unauthorized NEFT/RTGS/IMPS transfer",
      "Incorrect beneficiary credited",
      "Failed transaction but amount debited",
      "Subscription / auto-debit dispute",
      "Refund pending",
    ],
    uploadSuggestions: [
      "Net banking transaction receipt",
      "Bank statement",
      "NEFT/RTGS/IMPS confirmation email",
      "Beneficiary addition confirmation",
    ],
    contextHelp:
      "For NEFT/RTGS/IMPS disputes, the IFSC code and beneficiary account are required to trace and recall the transfer. RTGS reversals may take up to 2 business days.",
  },

  Wallet: {
    description: "Wallet-based transactions through payment apps and stored balances",
    extraFields: [
      {
        key: "wallet_provider",
        label: "Wallet Provider",
        type: "select",
        required: true,
        options: [
          "Paytm",
          "Amazon Pay",
          "PhonePe",
          "Mobikwik",
          "Freecharge",
          "Other",
        ],
      },
      {
        key: "linked_mobile",
        label: "Registered Mobile Number",
        type: "text",
        placeholder: "Mobile linked to the wallet",
      },
      {
        key: "wallet_transaction_id",
        label: "Wallet Transaction ID",
        type: "text",
        placeholder: "From your wallet transaction history",
      },
      {
        key: "device_platform",
        label: "Device Platform",
        type: "select",
        options: ["Android", "iOS", "Web"],
      },
    ],
    disputeReasons: [
      "Unauthorized wallet payment",
      "Wallet balance debited incorrectly",
      "Failed payment but balance deducted",
      "Refund not credited to wallet",
      "Cashback / reward dispute",
    ],
    uploadSuggestions: [
      "Wallet transaction screenshot",
      "Wallet statement export",
      "Merchant order confirmation",
      "Cashback terms screenshot",
    ],
    contextHelp:
      "Wallet disputes are handled by the wallet provider. Once we raise a chargeback, the provider has 7 days to respond. Keep your wallet transaction ID handy.",
  },

  POS: {
    description: "Point-of-sale terminal transactions using physical cards",
    extraFields: [
      {
        key: "last_4_digits",
        label: "Last 4 Digits of Card",
        type: "masked-digits",
      },
      {
        key: "card_network",
        label: "Card Network",
        type: "select",
        options: ["Visa", "Mastercard", "Amex", "RuPay"],
      },
      {
        key: "authorization_code",
        label: "Authorization Code",
        type: "text",
        placeholder: "From the charge slip",
      },
      {
        key: "merchant_location",
        label: "Merchant Location",
        type: "text",
        required: true,
        placeholder: "Store / city name",
      },
      {
        key: "transaction_mode",
        label: "POS Method",
        type: "select",
        options: [
          "Chip & PIN",
          "Contactless",
          "Swipe",
          "Manual Imprint",
        ],
      },
    ],
    disputeReasons: [
      "Unauthorized POS charge",
      "Duplicate POS charge",
      "Incorrect amount charged",
      "POS transaction failed but account debited",
      "Refund not received",
    ],
    uploadSuggestions: [
      "POS charge slip / receipt",
      "Bank statement",
      "Merchant invoice",
      "Transaction alert SMS",
    ],
    contextHelp:
      "POS disputes require the merchant's authorization code from the charge slip. If you have the physical receipt, please upload it as it significantly speeds up investigation.",
  },

  ATM: {
    description: "Cash withdrawals, failed withdrawals and ATM debit disputes",
    extraFields: [
      {
        key: "atm_id",
        label: "ATM ID / Terminal ID",
        type: "text",
        placeholder: "e.g. SBI00012345",
        help: "Found on the ATM screen or printed receipt",
      },
      {
        key: "atm_location",
        label: "ATM Location",
        type: "text",
        required: true,
        placeholder: "Branch / area / address of the ATM",
      },
      {
        key: "atm_bank",
        label: "ATM Bank (Acquiring Bank)",
        type: "text",
        required: true,
        placeholder: "Bank that owns the ATM",
      },
      {
        key: "cash_dispensed",
        label: "Was Cash Dispensed?",
        type: "toggle",
        help: "Did the ATM release any cash at all?",
      },
      {
        key: "partial_cash",
        label: "Partial Cash Dispensed?",
        type: "toggle",
        help: "Was only a portion of the requested amount dispensed?",
      },
    ],
    disputeReasons: [
      "Cash not dispensed but account debited",
      "Partial cash dispensed",
      "ATM card captured",
      "Unauthorized ATM withdrawal",
      "ATM receipt error",
    ],
    uploadSuggestions: [
      "ATM receipt",
      "Bank account statement",
      "FIR copy (if card stolen)",
      "Transaction alert SMS",
    ],
    contextHelp:
      "ATM disputes are investigated using CCTV footage and ATM journal logs. Providing the ATM ID speeds up the investigation significantly. If your card was captured, please also file an FIR.",
  },

  "Online Purchase": {
    description: "E-commerce orders, merchant disputes and delivery-related issues",
    extraFields: [
      {
        key: "merchant_website",
        label: "Merchant Website / App",
        type: "text",
        required: true,
        placeholder: "e.g. amazon.in, flipkart.com",
      },
      {
        key: "order_id",
        label: "Order ID",
        type: "text",
        required: true,
        placeholder: "Order reference from the merchant",
      },
      {
        key: "delivery_status",
        label: "Delivery Status",
        type: "select",
        options: [
          "Not Delivered",
          "Partially Delivered",
          "Delivered but Defective",
          "Delivered but Wrong Item",
          "Return Requested",
        ],
      },
      {
        key: "tracking_id",
        label: "Shipment Tracking ID",
        type: "text",
        placeholder: "Logistics tracking number",
      },
      {
        key: "refund_request_status",
        label: "Refund Request Status",
        type: "select",
        options: [
          "Not Raised",
          "Raised but Pending",
          "Rejected by Merchant",
          "No Response",
        ],
      },
    ],
    disputeReasons: [
      "Product not delivered",
      "Defective / wrong product received",
      "Refund not received",
      "Subscription charged incorrectly",
      "Merchant charged incorrect amount",
      "Duplicate order charged",
    ],
    uploadSuggestions: [
      "Order confirmation email",
      "Delivery proof / photo",
      "Return shipping receipt",
      "Merchant refusal email",
      "Product photos (if defective)",
    ],
    contextHelp:
      "For online purchase disputes, always try resolving with the merchant first. If the merchant does not respond within 7 days, we can initiate a chargeback on your behalf. Keep order and communication records.",
  },

  International: {
    description: "Cross-border transactions and foreign merchant payments",
    extraFields: [
      {
        key: "last_4_digits",
        label: "Last 4 Digits of Card",
        type: "masked-digits",
      },
      {
        key: "card_network",
        label: "Card Network",
        type: "select",
        options: ["Visa", "Mastercard", "Amex", "Diners"],
      },
      {
        key: "merchant_country",
        label: "Merchant Country",
        type: "text",
        required: true,
        placeholder: "Country of the merchant",
      },
      {
        key: "billing_currency",
        label: "Original Billing Currency",
        type: "text",
        placeholder: "e.g. USD, EUR, GBP",
      },
      {
        key: "authorization_code",
        label: "Authorization Code",
        type: "text",
        placeholder: "From statement or alert",
      },
      {
        key: "transaction_mode",
        label: "Transaction Mode",
        type: "select",
        options: ["Online", "POS", "ATM"],
      },
      {
        key: "is_international",
        label: "International Transaction Enabled",
        type: "toggle",
        help: "Was international usage enabled on your card?",
      },
    ],
    disputeReasons: [
      "Unauthorized international transaction",
      "Incorrect currency conversion",
      "International merchant dispute",
      "Refund not received in INR",
      "Card skimming abroad",
      "Service not received from international merchant",
    ],
    uploadSuggestions: [
      "Card statement showing international charge",
      "Passport / travel proof",
      "Merchant receipt in foreign currency",
      "Currency conversion slip",
      "FIR or police report (if card skimmed)",
    ],
    contextHelp:
      "International disputes involve the card network (Visa/Mastercard) and the foreign acquiring bank. Resolution typically takes 30–45 business days. Dynamic Currency Conversion (DCC) disputes require the original receipt.",
  },
};
