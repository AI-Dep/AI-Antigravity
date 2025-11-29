#!/bin/bash
# Setup script for Fixed Asset AI environment variables

echo "========================================"
echo "Fixed Asset AI - Environment Setup"
echo "========================================"
echo ""

# Check if .env already exists
if [ -f ".env" ]; then
    echo "⚠️  .env file already exists!"
    echo ""
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled. Existing .env file preserved."
        exit 0
    fi
fi

# Get OpenAI API key
echo "1️⃣  OpenAI API Key Setup"
echo ""
echo "   Get your API key from: https://platform.openai.com/api-keys"
echo ""
read -p "   Enter your OpenAI API key (starts with 'sk-'): " OPENAI_KEY

if [[ ! $OPENAI_KEY =~ ^sk- ]]; then
    echo ""
    echo "❌ Error: API key should start with 'sk-'"
    echo "   Please check your key and try again."
    exit 1
fi

# Get application password
echo ""
echo "2️⃣  Application Password Setup"
echo ""
echo "   Set a password to protect your app (12+ characters recommended)"
echo ""
read -p "   Enter your application password: " APP_PASS

if [ ${#APP_PASS} -lt 6 ]; then
    echo ""
    echo "⚠️  Warning: Password is very short. Recommended 12+ characters."
    read -p "   Continue anyway? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled. Please try again with a stronger password."
        exit 1
    fi
fi

# Create .env file
echo ""
echo "3️⃣  Creating .env file..."

cat > .env << EOF
# OpenAI API Configuration
# Generated: $(date)

# OpenAI API Key (REQUIRED)
OPENAI_API_KEY=$OPENAI_KEY

# Application Password (REQUIRED)
APP_PASSWORD=$APP_PASS

# Optional: Set usage limits to prevent unexpected costs
# OPENAI_MAX_TOKENS=100000
# OPENAI_MAX_REQUESTS_PER_MINUTE=60

# Optional: Privacy settings
# INCLUDE_LOCATION_IN_GPT=true

# Optional: Maximum assets per run (default: 1000)
# MAX_ASSETS_PER_RUN=1000
EOF

chmod 600 .env

echo ""
echo "✅ Success! .env file created"
echo ""
echo "========================================"
echo "Next Steps:"
echo "========================================"
echo ""
echo "1. Start the application:"
echo "   streamlit run fixed_asset_ai/app.py"
echo ""
echo "2. Login with your password: $APP_PASS"
echo ""
echo "3. Upload your fixed asset data and start classifying!"
echo ""
echo "⚠️  IMPORTANT: Never commit .env to git!"
echo "   (It's already in .gitignore)"
echo ""
