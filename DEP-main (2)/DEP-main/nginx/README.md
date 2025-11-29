# HTTPS Reverse Proxy Configuration

This directory contains Nginx configuration for running Fixed Asset AI with HTTPS support.

## Quick Setup

### 1. Generate SSL Certificates

**Option A: Self-signed (development)**
```bash
mkdir -p ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/privkey.pem \
  -out ssl/fullchain.pem \
  -subj "/CN=localhost"

# Generate DH parameters (one-time, ~30 seconds)
openssl dhparam -out ssl/dhparam.pem 2048
```

**Option B: Let's Encrypt (production)**
```bash
# First, start nginx without SSL for domain validation
docker-compose -f docker-compose.nginx.yml up -d nginx

# Run certbot to get certificates
docker-compose -f docker-compose.nginx.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d fixed-asset-ai.example.com \
  --email admin@example.com \
  --agree-tos --no-eff-email

# Restart nginx to load new certificates
docker-compose -f docker-compose.nginx.yml restart nginx
```

### 2. Configure Domain

Edit `nginx.conf` and replace:
```nginx
server_name fixed-asset-ai.example.com;
```
with your actual domain.

### 3. Start Services

```bash
# Copy environment variables
cp ../.env.example ../.env
# Edit .env with your API keys

# Start all services
docker-compose -f docker-compose.nginx.yml up -d

# View logs
docker-compose -f docker-compose.nginx.yml logs -f
```

### 4. Access Application

- HTTP: `http://your-domain` (redirects to HTTPS)
- HTTPS: `https://your-domain`

## Architecture

```
                    ┌─────────────────────┐
                    │     Internet        │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Nginx (Port 443)  │
                    │   - HTTPS/TLS       │
                    │   - Security headers│
                    │   - Rate limiting   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Streamlit (Port 8501)│
                    │   - Fixed Asset AI  │
                    │   - Internal only   │
                    └─────────────────────┘
```

## Security Features

- **TLS 1.2/1.3**: Modern encryption protocols only
- **HTTP/2**: Faster, multiplexed connections
- **Security Headers**: X-Frame-Options, CSP, XSS protection
- **Rate Limiting**: 10 requests/second per IP
- **Connection Limits**: 10 concurrent connections per IP
- **OCSP Stapling**: Faster certificate validation

## Troubleshooting

### Certificate Issues
```bash
# Check certificate validity
openssl s_client -connect localhost:443 -servername fixed-asset-ai.example.com

# View certificate details
openssl x509 -in ssl/fullchain.pem -text -noout
```

### Connection Issues
```bash
# Check nginx status
docker-compose -f docker-compose.nginx.yml exec nginx nginx -t

# View nginx logs
docker-compose -f docker-compose.nginx.yml logs nginx

# Test WebSocket connection
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" https://localhost/_stcore/stream
```

### Performance Tuning
- Increase `worker_connections` for high traffic
- Adjust `client_max_body_size` for larger file uploads
- Enable `proxy_buffering` if memory is limited

## Production Checklist

- [ ] Replace self-signed cert with Let's Encrypt
- [ ] Update `server_name` to actual domain
- [ ] Configure firewall (allow 80, 443)
- [ ] Set up automated cert renewal
- [ ] Enable log rotation
- [ ] Configure monitoring/alerting
- [ ] Test WebSocket connectivity
- [ ] Verify file upload size limits
