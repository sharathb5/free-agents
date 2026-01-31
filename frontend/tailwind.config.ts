import type { Config } from "tailwindcss"

const config = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
	],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "#F0EDE8",
        foreground: "#271203",
        primary: {
          DEFAULT: "#496677",
          foreground: "#F0EDE8",
        },
        secondary: {
          DEFAULT: "#9FB2CD",
          foreground: "#271203",
        },
        accent: {
          DEFAULT: "#ABAC5A",
          foreground: "#271203",
        },
        muted: {
          DEFAULT: "#9FB2CD",
          foreground: "#496677",
        },
        // Custom palette
        "blue-bayoux": "#496677",
        "rock-blue": "#9FB2CD",
        "pampas": "#F0EDE8",
        "olive-green": "#ABAC5A",
        "kilamanjaro": "#271203",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config

export default config
