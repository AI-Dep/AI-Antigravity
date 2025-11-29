@echo off
echo Installing Frontend Dependencies...
call npm install
call npm install -D tailwindcss postcss autoprefixer
call npm install lucide-react clsx tailwind-merge class-variance-authority react-router-dom

echo.
echo Starting Development Server...
call npm run dev
pause
