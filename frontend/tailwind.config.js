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
        card: "var(--card)",
        foreground: "var(--foreground)",
        "muted-foreground": "var(--muted-foreground)",
        border: "var(--border)",
        // Trade DIRECTION only — never generic success/error. `success` holds
        // the same values by coincidence, and stays separate on purpose.
        buy: "var(--buy)",
        sell: "var(--sell)",
        success: "var(--success)",
        warning: "var(--warning)",
        info: "var(--info)",
        destructive: "var(--destructive)",
        leovee: {
          accent: "var(--accent)",
          surface: "var(--background)",
          panel: "var(--card)",
        },
      },
    },
  },
  plugins: [],
};
