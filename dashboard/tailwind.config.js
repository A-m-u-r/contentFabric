/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#09090b",
        surface: "#18181b",
        // Single brand accent across the whole app (was split blue/violet).
        // primary === accent === Tailwind violet-500 so `bg-primary`,
        // `text-primary`, focus rings and the violet-* scale all agree.
        primary: "#8b5cf6",
        accent: "#8b5cf6",
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}
