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
        // BFSI Enterprise Dark Theme
        bfsi: {
          black: "#080810",
          navy: "#0d0d1a",
          dark: "#111120",
          card: "#14141f",
          border: "#1e1e32",
          muted: "#252538",
          // Gold/amber accent
          gold: "#f59e0b",
          "gold-light": "#fbbf24",
          "gold-dark": "#d97706",
          "gold-glow": "rgba(245,158,11,0.15)",
          // Status colors
          success: "#10b981",
          danger: "#ef4444",
          warning: "#f59e0b",
          info: "#3b82f6",
          // Text
          text: "#e2e8f0",
          "text-muted": "#94a3b8",
          "text-dim": "#64748b",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      backgroundImage: {
        "bfsi-gradient": "linear-gradient(135deg, #080810 0%, #0d0d1a 50%, #111120 100%)",
        "card-gradient": "linear-gradient(145deg, #14141f 0%, #111120 100%)",
        "gold-gradient": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        "danger-gradient": "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
      },
      boxShadow: {
        "bfsi-card": "0 4px 24px rgba(0,0,0,0.4), 0 1px 4px rgba(0,0,0,0.3)",
        "bfsi-glow": "0 0 20px rgba(245,158,11,0.15)",
        "bfsi-danger": "0 0 20px rgba(239,68,68,0.15)",
        "bfsi-success": "0 0 20px rgba(16,185,129,0.15)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      animation: {
        "pulse-gold": "pulse-gold 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fade-in 0.3s ease-out",
        "slide-up": "slide-up 0.3s ease-out",
      },
      keyframes: {
        "pulse-gold": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { transform: "translateY(8px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
