/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
          950: '#082f49',
        },
        secondary: {
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
          950: '#022c22',
        },
        accent: {
          50: '#fef7ff',
          100: '#fdf4ff',
          200: '#fae8ff',
          300: '#f5d0fe',
          400: '#f0abfc',
          500: '#e879f9',
          600: '#d946ef',
          700: '#c026d3',
          800: '#a21caf',
          900: '#86198f',
          950: '#581c87',
        },
        penguin: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
          950: '#020617',
        },
        success: {
          50: '#f0fdf4',
          500: '#22c55e',
          600: '#16a34a',
        },
        warning: {
          50: '#fffbeb',
          500: '#f59e0b',
          600: '#d97706',
        },
        error: {
          50: '#fef2f2',
          500: '#ef4444',
          600: '#dc2626',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'Monaco', 'monospace'],
      },
      typography: {
        DEFAULT: {
          css: {
            maxWidth: 'none',
            color: 'rgb(51 65 85)',
            hr: {
              borderColor: 'rgb(226 232 240)',
              marginTop: '2em',
              marginBottom: '2em',
            },
            'h1, h2, h3, h4': {
              color: 'rgb(15 23 42)',
            },
            code: {
              color: 'rgb(79 70 229)',
              backgroundColor: 'rgb(238 242 255)',
              padding: '0.25rem 0.375rem',
              borderRadius: '0.25rem',
              fontWeight: '500',
            },
            'code::before': {
              content: '""',
            },
            'code::after': {
              content: '""',
            },
            pre: {
              backgroundColor: 'rgb(15 23 42)',
              color: 'rgb(226 232 240)',
              border: '1px solid rgb(51 65 85)',
            },
            'pre code': {
              backgroundColor: 'transparent',
              color: 'inherit',
              padding: '0',
            },
            a: {
              color: 'rgb(37 99 235)',
              textDecoration: 'none',
              fontWeight: '500',
              '&:hover': {
                color: 'rgb(29 78 216)',
                textDecoration: 'underline',
              },
            },
            blockquote: {
              borderLeftColor: 'rgb(99 102 241)',
              backgroundColor: 'rgb(248 250 252)',
              padding: '1rem 1.5rem',
              borderRadius: '0.5rem',
            },
            'thead th': {
              color: 'rgb(15 23 42)',
              fontWeight: '600',
            },
            'tbody td': {
              borderColor: 'rgb(226 232 240)',
            },
          },
        },
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'bounce-slow': 'bounce 2s infinite',
        'ping': 'ping 2s cubic-bezier(0, 0, 0.2, 1) infinite',
        'pulse': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      animationDelay: {
        '1000': '1s',
        '2000': '2s',
        '4000': '4s',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
      screens: {
        'xs': '475px',
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
    require('@tailwindcss/forms'),
  ],
};