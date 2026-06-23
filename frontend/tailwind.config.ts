import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ops: {
          // Primary backgrounds
          bg:          "#1A2744",
          surface:     "#1E293B",
          panel:       "#111827",
          overlay:     "#0B1120",
          // Borders
          border:      "#334155",
          "border-subtle": "#1E293B",
          // Text
          text:        "#F8FAFC",
          secondary:   "#94A3B8",
          muted:       "#64748B",
          // Semantic
          success:     "#15803D",
          "success-bg":"#F0FDF4",
          "success-text": "#166534",
          warning:     "#B45309",
          "warning-bg":"#FFFBEB",
          "warning-text":"#92400E",
          critical:    "#B91C1C",
          "critical-bg":"#FEF2F2",
          "critical-text":"#991B1B",
          info:        "#2563EB",
          "info-bg":   "#EFF6FF",
          "info-text": "#1D4ED8",
          // Accent (subdued blue, not orange)
          accent:      "#2563EB",
          "accent-light": "#3B82F6",
        },
        // Legacy aliases — keep existing code working
        bfsi: {
          black:      "#1A2744",
          navy:       "#0B1120",
          dark:       "#111827",
          card:       "#1E293B",
          border:     "#334155",
          muted:      "#1E293B",
          gold:       "#2563EB",   // Remap gold → professional blue
          "gold-light":"#3B82F6",
          "gold-dark": "#1D4ED8",
          "gold-glow": "rgba(37,99,235,0.10)",
          success:    "#15803D",
          danger:     "#B91C1C",
          warning:    "#B45309",
          info:       "#2563EB",
          text:       "#F8FAFC",
          "text-muted":"#94A3B8",
          "text-dim": "#64748B",
          accent:     "#2563EB",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        "ops-card": "0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3)",
        "ops-elevated": "0 4px 12px rgba(0,0,0,0.5)",
        "bfsi-card": "0 1px 3px rgba(0,0,0,0.4)",
        "bfsi-glow":  "none",
      },
      animation: {
        "fade-in":  "fade-in 0.2s ease-out",
        "slide-up": "slide-up 0.2s ease-out",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { transform: "translateY(6px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
