const { fontFamily } = require("tailwindcss/defaultTheme");

/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx,jsx,js}"],
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: {
        "2xl": "1320px",
      },
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", ...fontFamily.sans],
        heading: ["var(--font-heading)", ...fontFamily.sans],
      },
      borderColor: {
        DEFAULT: "var(--border)",
        accent: "var(--accent)",
      },
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        subtle: "var(--subtle)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        success: {
          DEFAULT: "var(--success-bg)",
          foreground: "var(--success-text)",
        },
        info: {
          DEFAULT: "var(--info-bg)",
          foreground: "var(--info-text)",
        },
        warning: {
          DEFAULT: "var(--warning-bg)",
          foreground: "var(--warning-text)",
        },
        link: {
          DEFAULT: "var(--link)",
        },
      },
      boxShadow: {
        "floating-card": "0px 30px 80px rgba(18, 19, 28, 0.12)",
      },
    },
  },
  plugins: [
    function ({ addVariant }) {
      addVariant("supports-hover", "@media (hover:hover)");
    },
  ],
};
