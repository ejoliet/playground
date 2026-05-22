# Papyrus DMS Setup Guide with Reverse Proxy

This guide will help you set up Papyrus Document Management System (DMS) accessible at `dms.626733.xyz:1222` using Docker and Nginx reverse proxy.

## Architecture Overview

```
Internet (dms.626733.xyz:1222)
    ↓
Your Server (Public IP)
    ↓
Nginx Reverse Proxy (localhost:1222)
    ↓
Papyrus DMS Container (localhost:8080)
```

## Prerequisites

1. A server with Docker and Docker Compose installed
2. Domain `626733.xyz` registered and DNS configured
3. Port 1222 open in your firewall
4. Root or sudo access to your server

## DNS Configuration

Configure your DNS records at your domain registrar:

```
Type: A
Name: dms
Value: <Your Server's Public IP Address>
TTL: 3600 (or default)
```

This will make `dms.626733.xyz` point to your server.

## Setup Instructions

### 1. Configure Environment Variables

Copy the example environment file and customize it:

```bash
cp .env.example .env
nano .env  # Edit with your preferred editor
```

Update these critical values:
- `APP_BASE_URL`: Set to `http://dms.626733.xyz:1222`
- `SECRET_KEY`: Generate a secure key (run: `openssl rand -hex 32`)

### 2. Create Required Directories

The setup script will create these automatically, but you can also create them manually:

```bash
mkdir -p papyrus-data papyrus-uploads papyrus-config
mkdir -p nginx/conf.d nginx/ssl nginx/logs
```

### 3. Configure Firewall

Open port 1222 in your server's firewall:

**For UFW (Ubuntu/Debian):**
```bash
sudo ufw allow 1222/tcp
sudo ufw reload
```

**For firewalld (CentOS/RHEL):**
```bash
sudo firewall-cmd --permanent --add-port=1222/tcp
sudo firewall-cmd --reload
```

**For iptables:**
```bash
sudo iptables -A INPUT -p tcp --dport 1222 -j ACCEPT
sudo iptables-save > /etc/iptables/rules.v4
```

### 4. Start the Services

Start all services using Docker Compose:

```bash
docker-compose up -d
```

This will:
- Pull the Papyrus DMS image
- Pull the Nginx image
- Create the necessary network
- Start both containers

### 5. Verify the Setup

Check if containers are running:

```bash
docker-compose ps
```

Check logs:

```bash
# View all logs
docker-compose logs -f

# View only Papyrus DMS logs
docker-compose logs -f papyrus-dms

# View only Nginx logs
docker-compose logs -f nginx-proxy
```

### 6. Access Your DMS

Open your browser and navigate to:
- From anywhere: `http://dms.626733.xyz:1222`
- From local server: `http://localhost:1222`

## Testing the Reverse Proxy

Test the proxy configuration:

```bash
# From your server
curl -I http://localhost:1222

# Test DNS resolution
nslookup dms.626733.xyz

# Test from outside (replace with your server's IP)
curl -I http://dms.626733.xyz:1222
```

## Variable App Base URL Explained

The `APP_BASE_URL` environment variable allows the application to:
1. Generate correct absolute URLs in emails and redirects
2. Handle CORS properly
3. Generate correct asset URLs
4. Ensure proper OAuth/authentication callbacks

When you change domains or ports, simply update the `.env` file and restart:

```bash
docker-compose restart papyrus-dms
```

## Nginx Reverse Proxy Configuration

The reverse proxy configuration (`nginx/conf.d/papyrus-dms.conf`) provides:

1. **Port Mapping**: Maps external port 1222 to internal port 8080
2. **Header Forwarding**: Passes client information to the backend
3. **WebSocket Support**: Enables real-time features if needed
4. **Security Headers**: Adds security headers to responses
5. **Static File Caching**: Optimizes performance for static assets
6. **Health Checks**: Monitors backend availability

### Key Proxy Headers

```nginx
X-Real-IP: Client's actual IP address
X-Forwarded-For: Chain of proxy IPs
X-Forwarded-Proto: Original protocol (http/https)
X-Forwarded-Host: Original hostname
X-Forwarded-Port: Original port
```

These headers ensure the application knows the original request details.

## Optional: Enable HTTPS (Recommended for Production)

### Using Let's Encrypt (Free SSL Certificate)

1. Install Certbot:
```bash
sudo apt-get update
sudo apt-get install certbot
```

2. Get SSL certificate:
```bash
sudo certbot certonly --standalone -d dms.626733.xyz
```

3. Copy certificates to nginx directory:
```bash
sudo cp /etc/letsencrypt/live/dms.626733.xyz/fullchain.pem nginx/ssl/dms.626733.xyz.crt
sudo cp /etc/letsencrypt/live/dms.626733.xyz/privkey.pem nginx/ssl/dms.626733.xyz.key
```

4. Uncomment the HTTPS server block in `nginx/conf.d/papyrus-dms.conf`

5. Restart nginx:
```bash
docker-compose restart nginx-proxy
```

6. Access via: `https://dms.626733.xyz:1222`

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs papyrus-dms

# Check if port is already in use
sudo netstat -tulpn | grep 1222

# Restart services
docker-compose restart
```

### Cannot access from external network

1. Verify DNS propagation:
```bash
nslookup dms.626733.xyz
dig dms.626733.xyz
```

2. Check firewall:
```bash
sudo ufw status
sudo iptables -L -n | grep 1222
```

3. Verify containers are running:
```bash
docker-compose ps
```

4. Test local connectivity:
```bash
curl http://localhost:1222
```

### 502 Bad Gateway

This means Nginx can't reach the backend:

```bash
# Check if papyrus-dms is running
docker-compose ps papyrus-dms

# Check backend health
docker-compose exec papyrus-dms curl http://localhost:8080/health

# Check network connectivity
docker network ls
docker network inspect workspace_dms-network
```

### Performance Issues

1. Increase nginx worker connections:
   - Edit `nginx/nginx.conf`
   - Increase `worker_connections` value

2. Adjust proxy buffers:
   - Edit `nginx/conf.d/papyrus-dms.conf`
   - Increase buffer sizes

3. Monitor resources:
```bash
docker stats
```

## Maintenance

### Backup

Backup important data:

```bash
# Backup data directory
tar -czf papyrus-backup-$(date +%Y%m%d).tar.gz papyrus-data papyrus-uploads

# Backup database (if using PostgreSQL)
docker-compose exec postgres pg_dump -U papyrus papyrus_dms > backup.sql
```

### Update

Update to the latest version:

```bash
docker-compose pull
docker-compose up -d
```

### View Logs

```bash
# Nginx access logs
tail -f nginx/logs/papyrus-dms-access.log

# Nginx error logs
tail -f nginx/logs/papyrus-dms-error.log

# Container logs
docker-compose logs -f
```

### Restart Services

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart nginx-proxy
docker-compose restart papyrus-dms
```

### Stop Services

```bash
# Stop all services
docker-compose stop

# Stop and remove containers
docker-compose down

# Stop and remove containers, volumes, and networks
docker-compose down -v
```

## Security Best Practices

1. **Change Default Credentials**: Update `SECRET_KEY` in `.env`
2. **Use HTTPS**: Enable SSL/TLS for production
3. **Regular Updates**: Keep Docker images updated
4. **Firewall**: Only expose necessary ports
5. **Backup**: Regular backups of data and configuration
6. **Monitor Logs**: Check logs regularly for suspicious activity
7. **Strong Passwords**: Use strong passwords for admin accounts

## Advanced Configuration

### Using PostgreSQL Instead of SQLite

1. Update `docker-compose.yml` to add PostgreSQL service
2. Update `.env` with PostgreSQL credentials
3. Update `DATABASE_URL` to use PostgreSQL connection string

### Adding Multiple Domains

Edit `nginx/conf.d/papyrus-dms.conf` and add domains to `server_name`:

```nginx
server_name dms.626733.xyz another-domain.com localhost;
```

### Custom Port

To change from port 1222:

1. Update port mapping in `docker-compose.yml`
2. Update `APP_BASE_URL` in `.env`
3. Update DNS/firewall rules
4. Restart services

## Support and Documentation

- **Docker Documentation**: https://docs.docker.com/
- **Nginx Documentation**: https://nginx.org/en/docs/
- **Let's Encrypt**: https://letsencrypt.org/

## Quick Reference Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose stop

# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Check status
docker-compose ps

# Update and restart
docker-compose pull && docker-compose up -d

# View nginx config test
docker-compose exec nginx-proxy nginx -t

# Reload nginx config
docker-compose exec nginx-proxy nginx -s reload
```

## File Structure

```
/workspace/
├── docker-compose.yml          # Main orchestration file
├── .env                        # Environment variables (create from .env.example)
├── .env.example               # Template for environment variables
├── nginx/
│   ├── nginx.conf            # Main nginx configuration
│   ├── conf.d/
│   │   └── papyrus-dms.conf  # DMS-specific nginx config
│   ├── ssl/                  # SSL certificates (optional)
│   └── logs/                 # Nginx logs
├── papyrus-data/             # Application data
├── papyrus-uploads/          # Uploaded files
└── papyrus-config/           # Application configuration
```

---

**Note**: Replace `dms.626733.xyz` with your actual domain throughout the configuration if different.
