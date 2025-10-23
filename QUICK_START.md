# Quick Start Guide - Papyrus DMS

## One-Command Setup

Run the automated setup script:

```bash
./setup.sh
```

This will:
1. Create the `.env` file with a secure random secret key
2. Create all required directories
3. Validate the nginx configuration
4. Optionally start the services

## Manual Setup (Alternative)

If you prefer manual setup:

```bash
# 1. Copy and configure environment
cp .env.example .env
nano .env  # Update APP_BASE_URL and SECRET_KEY

# 2. Start services
docker-compose up -d

# 3. Check status
docker-compose ps
```

## Accessing Your DMS

- **Local**: http://localhost:1222
- **Domain**: http://dms.626733.xyz:1222

## DNS Configuration Required

At your domain registrar (where you bought 626733.xyz), add this DNS record:

```
Type: A
Name: dms
Value: <Your Server's Public IP>
TTL: 3600
```

## Firewall Configuration Required

Open port 1222:

**Ubuntu/Debian:**
```bash
sudo ufw allow 1222/tcp
```

**CentOS/RHEL:**
```bash
sudo firewall-cmd --permanent --add-port=1222/tcp
sudo firewall-cmd --reload
```

## Verify Installation

```bash
# Check containers are running
docker-compose ps

# Check logs
docker-compose logs -f

# Test locally
curl http://localhost:1222

# Test DNS (after propagation)
nslookup dms.626733.xyz
```

## Key Configuration Files

- `docker-compose.yml` - Container orchestration
- `.env` - Environment variables (create from `.env.example`)
- `nginx/conf.d/papyrus-dms.conf` - Reverse proxy configuration
- `nginx/nginx.conf` - Main nginx configuration

## Important Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `APP_BASE_URL` | Public URL of your DMS | `http://dms.626733.xyz:1222` |
| `SECRET_KEY` | Security key (generate with `openssl rand -hex 32`) | `abc123...` |
| `DATABASE_URL` | Database connection | `sqlite:///data/papyrus.db` |

## Common Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose stop

# Restart services
docker-compose restart

# View logs
docker-compose logs -f

# Update containers
docker-compose pull && docker-compose up -d

# Remove everything
docker-compose down -v
```

## How It Works

```
Internet Request (dms.626733.xyz:1222)
    ↓
Your Server (receives on port 1222)
    ↓
Nginx Container (nginx-proxy:1222)
    ↓ [reverse proxy]
Papyrus DMS Container (papyrus-dms:8080)
```

The reverse proxy:
- Handles external requests on port 1222
- Forwards to internal Papyrus DMS on port 8080
- Adds security headers
- Manages SSL/TLS (when configured)
- Provides caching and optimization
- Preserves original request information via proxy headers

## Variable App Base URL

The `APP_BASE_URL` environment variable ensures:
- Correct URLs in emails and notifications
- Proper redirects after login/logout
- Correct asset URLs (CSS, JS, images)
- OAuth callbacks work correctly

When you access via `http://dms.626733.xyz:1222`, the application knows this is its public URL and generates all links accordingly.

## Troubleshooting

**Can't access from external network?**
- Check DNS: `nslookup dms.626733.xyz`
- Check firewall: `sudo ufw status`
- Check containers: `docker-compose ps`

**502 Bad Gateway?**
- Check if backend is running: `docker-compose ps papyrus-dms`
- Check logs: `docker-compose logs papyrus-dms`

**Need SSL/HTTPS?**
See the "Enable HTTPS" section in `DMS_SETUP_GUIDE.md`

## Full Documentation

For detailed documentation, see: [DMS_SETUP_GUIDE.md](./DMS_SETUP_GUIDE.md)

## Support

If you encounter issues:
1. Check logs: `docker-compose logs -f`
2. Verify configuration: `docker-compose config`
3. Test nginx: `docker-compose exec nginx-proxy nginx -t`
4. Check connectivity: `curl -v http://localhost:1222`
