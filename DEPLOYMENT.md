# FA CS Automator - Deployment Guide

## Quick Reference

| Audience | Method | Command | Output |
|----------|--------|---------|--------|
| Testers | Docker | `docker-compose up` | URL access |
| Testers | Electron | `npm run dist` | .exe installer |
| Clients | Docker | `docker save` | .tar file |
| Production | Cloud | Deploy to AWS/Azure | Public URL |

---

## Option 1: Docker Deployment (Recommended for Testers)

### Build and Run
```bash
# Build containers
docker-compose build

# Run the application
docker-compose up

# Access at:
# - Frontend: http://localhost:5173
# - Backend API: http://localhost:8000
```

### Export for Offline Distribution
```bash
# Save images to tar file
docker save fa-cs-automator-backend fa-cs-automator-frontend > fa-cs-automator.tar

# Share the .tar file with testers
# They load it with:
docker load < fa-cs-automator.tar
docker-compose up
```

---

## Option 2: Electron Desktop Build

### Prerequisites
```bash
npm install
pip install pyinstaller
```

### Build Steps
```bash
# 1. Compile Python backend
cd backend
pyinstaller fa_cs_automator.spec
# Output: backend/dist/fa_cs_automator_api.exe

# 2. Build Electron app
cd ..
npm run dist
# Output: dist/FA-CS-Automator-Setup.exe
```

### What Testers Receive
- Single installer file (`.exe` for Windows)
- No source code visible
- Self-contained application

---

## Option 3: Cloud Deployment (Best Protection)

### Railway (Free Tier Available)
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

### Docker on DigitalOcean
```bash
# Create droplet with Docker
doctl compute droplet create fa-cs-automator \
  --image docker-20-04 \
  --size s-2vcpu-4gb \
  --region nyc1

# SSH and run
docker-compose up -d
```

### AWS ECS
```bash
# Push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker tag fa-cs-automator:latest <account>.dkr.ecr.<region>.amazonaws.com/fa-cs-automator:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/fa-cs-automator:latest

# Deploy via ECS console or CLI
```

---

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for GPT classification | Yes |
| `CORS_ALLOWED_ORIGINS` | Allowed frontend origins (comma-separated) | Production |
| `OBBBA_ENABLED` | Enable/disable OBBBA provisions | No (default: true) |

### Setting Environment Variables

**Docker:**
```bash
# Create .env file
echo "OPENAI_API_KEY=sk-your-key-here" > .env
docker-compose --env-file .env up
```

**Electron:**
```bash
# Create .env in project root
OPENAI_API_KEY=sk-your-key-here
```

---

## Security Checklist for Production

- [ ] Set `CORS_ALLOWED_ORIGINS` to specific domains
- [ ] Use HTTPS (SSL certificate)
- [ ] Secure OpenAI API key (use secrets manager)
- [ ] Enable rate limiting
- [ ] Set up monitoring/logging
- [ ] Regular security updates

---

## Code Protection Summary

| Method | Source Code Exposure |
|--------|---------------------|
| Give folder directly | **FULL EXPOSURE** - Don't do this |
| Electron build | Bundled JS (hard to read) |
| PyInstaller + Electron | Compiled binary (very hard) |
| Docker container | Inside container (hard to extract) |
| Cloud/SaaS | **ZERO EXPOSURE** - Best protection |

---

## Support

For deployment issues, check:
1. Docker logs: `docker-compose logs`
2. Backend health: `curl http://localhost:8000/`
3. Frontend build: Check `dist/` folder exists
