#!/bin/bash
# Papyrus DMS Quick Setup Script

set -e

echo "========================================="
echo "Papyrus DMS Setup with Reverse Proxy"
echo "========================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Error: Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    
    # Generate a random secret key
    SECRET_KEY=$(openssl rand -hex 32)
    
    # Update the secret key in .env
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/change-me-in-production-use-a-long-random-string/$SECRET_KEY/" .env
    else
        # Linux
        sed -i "s/change-me-in-production-use-a-long-random-string/$SECRET_KEY/" .env
    fi
    
    echo "✓ Created .env file with generated SECRET_KEY"
    echo ""
    echo "IMPORTANT: Please edit .env and update APP_BASE_URL to match your domain:"
    echo "  APP_BASE_URL=http://dms.626733.xyz:1222"
    echo ""
else
    echo "✓ .env file already exists"
fi

# Create necessary directories
echo "Creating required directories..."
mkdir -p papyrus-data
mkdir -p papyrus-uploads
mkdir -p papyrus-config
mkdir -p nginx/conf.d
mkdir -p nginx/ssl
mkdir -p nginx/logs

echo "✓ Directories created"
echo ""

# Check if nginx config exists
if [ ! -f nginx/conf.d/papyrus-dms.conf ]; then
    echo "Error: nginx/conf.d/papyrus-dms.conf not found!"
    echo "Please ensure all configuration files are present."
    exit 1
fi

# Test nginx configuration syntax
echo "Testing nginx configuration..."
docker run --rm -v $(pwd)/nginx/nginx.conf:/etc/nginx/nginx.conf:ro \
    -v $(pwd)/nginx/conf.d:/etc/nginx/conf.d:ro \
    nginx:alpine nginx -t
echo "✓ Nginx configuration is valid"
echo ""

# Display current configuration
echo "Current configuration:"
echo "  - APP_BASE_URL: $(grep APP_BASE_URL .env | cut -d '=' -f2)"
echo "  - External Port: 1222"
echo "  - Internal Port: 8080"
echo ""

# Ask user if they want to start the services
read -p "Do you want to start the services now? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Starting services..."
    docker-compose up -d
    
    echo ""
    echo "========================================="
    echo "Setup Complete!"
    echo "========================================="
    echo ""
    echo "Your Papyrus DMS is now running at:"
    echo "  - Local: http://localhost:1222"
    echo "  - Domain: http://dms.626733.xyz:1222 (once DNS is configured)"
    echo ""
    echo "Useful commands:"
    echo "  - View logs: docker-compose logs -f"
    echo "  - Stop services: docker-compose stop"
    echo "  - Restart services: docker-compose restart"
    echo "  - Check status: docker-compose ps"
    echo ""
    echo "Next steps:"
    echo "  1. Configure DNS A record: dms.626733.xyz → Your Server IP"
    echo "  2. Open firewall port 1222"
    echo "  3. (Optional) Configure SSL/TLS for HTTPS"
    echo ""
    echo "For detailed documentation, see: DMS_SETUP_GUIDE.md"
    echo ""
else
    echo ""
    echo "Setup prepared but services not started."
    echo "To start services manually, run: docker-compose up -d"
    echo ""
fi
