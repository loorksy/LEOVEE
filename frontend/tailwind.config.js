/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Semantic names over var() so a component says what it means
        // (`text-buy`) and the value lives in one place (src/styles/tokens.css).
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: { DEFAULT: "var(--card)", foreground: "var(--card-foreground)" },
        popover: { DEFAULT: "var(--popover)", foreground: "var(--popover-foreground)" },
        // Monochrome action color — the one accent this product uses. No brand
        // indigo, no purple: color is spent on trading/status meaning only.
        primary: { DEFAULT: "var(--primary)", foreground: "var(--primary-foreground)" },
        secondary: { DEFAULT: "var(--secondary)", foreground: "var(--secondary-foreground)" },
        muted: { DEFAULT: "var(--muted)", foreground: "var(--muted-foreground)" },
        "muted-foreground": "var(--muted-foreground)",
        // Neutral hover/highlight tint — background role only, never text.
        accent: { DEFAULT: "var(--accent)", foreground: "var(--accent-foreground)" },
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        sidebar: {
          DEFAULT: "var(--sidebar)",
          foreground: "var(--sidebar-foreground)",
          border: "var(--sidebar-border)",
          ring: "var(--sidebar-ring)",
          "active-bg": "var(--sidebar-active-bg)",
          "active-text": "var(--sidebar-active-text)",
        },
        "surface-elevated": "var(--surface-elevated)",
        // Trade DIRECTION only — never generic success/error. `success` holds
        // the same values by coincidence, and stays separate on purpose.
        buy: "var(--buy)",
        sell: "var(--sell)",
        success: "var(--success)",
        warning: "var(--warning)",
        info: "var(--info)",
        destructive: { DEFAULT: "var(--destructive)", foreground: "var(--destructive-foreground)" },
        chart: {
          1: "var(--chart-1)",
          2: "var(--chart-2)",
          3: "var(--chart-3)",
          4: "var(--chart-4)",
          5: "var(--chart-5)",
        },
        // Back-compat aliases for the pre-redesign palette — `accent` now maps
        // to the new monochrome `primary`, not the old indigo brand color.
        leovee: {
          accent: "var(--primary)",
          surface: "var(--background)",
          panel: "var(--card)",
        },
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
        lg: "var(--radius-lg)",
      },
      fontFamily: {
        sans: ["Cairo", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
