/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        coral: {
          DEFAULT: "#FF7A5A",
          light: "#FFA38F",
          50: "#FFF5F2",
          100: "#FFE8E2",
          200: "#FFD1C5",
          300: "#FFA38F",
          400: "#FF8C73",
          500: "#FF7A5A",
          600: "#E8694B",
          700: "#CC5A40",
        },
        ocean: {
          DEFAULT: "#1F6F8B",
          deep: "#0B3C5D",
          sea: "#5FA8D3",
          aqua: "#CDEDF6",
          50: "#F0F9FC",
          100: "#CDEDF6",
          200: "#A3DAE9",
          300: "#5FA8D3",
          400: "#3D8FB5",
          500: "#1F6F8B",
          600: "#185A72",
          700: "#0B3C5D",
        },
        sand: {
          DEFAULT: "#F5E6CA",
          50: "#FDF9F1",
          100: "#F5E6CA",
          200: "#EDD5A8",
        },
        pearl: "#FAFAFA",
        slate: "#2E2E2E",
        positive: "#4CAF93",
        negative: "#E45757",
        highlight: "#FFD166",
      },
      borderRadius: {
        "2xl": "16px",
        "3xl": "24px",
      },
      boxShadow: {
        soft: "0 2px 16px rgba(11, 60, 93, 0.06)",
        card: "0 4px 24px rgba(11, 60, 93, 0.08)",
        glow: "0 0 24px rgba(255, 122, 90, 0.15)",
      },
      fontFamily: {
        sans: ['"Inter"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
