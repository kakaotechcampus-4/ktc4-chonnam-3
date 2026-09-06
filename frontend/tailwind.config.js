/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#1B1C20',
        muted: '#6C7078',
        line: '#CDD2D8',
        'line-soft': '#E6E8EB',
        accent: '#3652FF',
        'accent-soft': '#ECEFFF',
        paper: '#F6F6F3',
        surface: '#FFFFFF',
        error: '#E5484D',
        'error-soft': '#FDECEC',
      },
      fontFamily: {
        sans: ['Pretendard Variable', 'Pretendard', '-apple-system', 'sans-serif'],
      },
      borderRadius: {
        card: '10px',
      },
    },
  },
  plugins: [],
};
