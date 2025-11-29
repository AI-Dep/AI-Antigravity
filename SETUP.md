# FA CS Automator Setup

The frontend foundation has been created. Since the environment did not have `npm` accessible, you need to install the dependencies manually to run the app.

## 1. Install Dependencies
Open a terminal in this directory (`c:\Users\sejin\OneDrive\바탕 화면\AI Project\FA_Automator`) and run:

```bash
npm install
npm install -D tailwindcss postcss autoprefixer
npm install lucide-react clsx tailwind-merge class-variance-authority react-router-dom
```

## 2. Initialize Tailwind (If needed)
If the styles don't load, you might need to ensure tailwind is initialized (though the config files are already created).

## 3. Run the App
```bash
npm run dev
```

## 4. Verify
You should see the new "Premium" Dashboard with a Sidebar and Header.
