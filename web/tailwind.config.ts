import type { Config } from 'tailwindcss'

// Brand tokens from the project spec (@f1telemetryhub)
export default {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0B0E14',
        card: '#141923',
        line: '#232D3F',
        ink: '#E8ECF2',
        mute: '#93A0B4',
        cyan: '#00E5FF',
        purple: '#A855F7',
        gain: '#10B981',
        loss: '#EF4444',
      },
      fontFamily: {
        head: ['"Space Grotesk"', 'Inter', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
