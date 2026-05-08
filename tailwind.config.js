/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        asset: {
          blue: '#3b82f6',
          red: '#ef4444',
          green: '#22c55e',
        },
      },
    },
  },
  plugins: [],
}
