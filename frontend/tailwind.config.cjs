/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        night:   '#08090e',
        surface: { DEFAULT: '#0f1117', 2: '#141b27', 3: '#1c2538' },
        accent:  { DEFAULT: '#5eead4', dim: 'rgba(94,234,212,0.12)', glow: 'rgba(94,234,212,0.22)' },
        body:    '#e2e8f0',
        muted:   '#8892a4',
        subtle:  '#4d5e73',
        hot:     { DEFAULT: '#fb7185', dim: 'rgba(251,113,133,0.14)' },
        gold:    { DEFAULT: '#fbbf24', dim: 'rgba(251,191,36,0.13)' },
        sky:     { DEFAULT: '#60a5fa', dim: 'rgba(96,165,250,0.14)' },
      },
      gridTemplateColumns: { sidebar: '300px 1fr' },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
      animation: { shimmer: 'shimmer 1.8s ease-in-out infinite' },
      keyframes: {
        shimmer: {
          '0%':   { backgroundPosition: '-600px 0' },
          '100%': { backgroundPosition:  '600px 0' },
        },
      },
    },
  },
  plugins: [],
}
