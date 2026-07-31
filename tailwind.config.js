/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        rig: {
          950: "#0D1013",
          900: "#14181C",
          800: "#1C2126",
          700: "#272E35",
          600: "#3A4249",
          500: "#5B6570",
          400: "#8A939C",
          200: "#D7DBDE",
          50: "#EDEFF2",
        },
        signal: {
          DEFAULT: "#F2B705",
          600: "#D9A600",
          200: "#FDE8A0",
        },
        rust: {
          DEFAULT: "#D9531E",
          600: "#B84416",
        },
        ok: {
          DEFAULT: "#3FA34D",
        },
      },
      fontFamily: {
        display: ["'Barlow Condensed'", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      backgroundImage: {
        "diagonal-hazard":
          "repeating-linear-gradient(135deg, rgba(242,183,5,0.08) 0px, rgba(242,183,5,0.08) 10px, transparent 10px, transparent 20px)",
      },
      borderRadius: {
        tag: "4px",
      },
      boxShadow: {
        rivet: "inset 0 1px 0 rgba(255,255,255,0.04), 0 1px 0 rgba(0,0,0,0.4)",
      },
    },
  },
  plugins: [],
};
