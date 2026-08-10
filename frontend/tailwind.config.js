/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        leovee: {
          accent: "#6366f1",
          surface: "#0f1419",
          panel: "#1a2332",
        },
      },
    },
  },
  plugins: [],
};
