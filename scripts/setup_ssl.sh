#!/bin/bash
# ============================================
# SSL + Nginx Auto-Setup
# Run: bash scripts/setup_ssl.sh your_domain.com
# ============================================

set -e

DOMAIN=$1

if [ -z "$DOMAIN" ]; then
    echo "Usage: bash scripts/setup_ssl.sh your_domain.com"
    echo ""
    echo "Before running:"
    echo "1. Point your domain's DNS A record to this server's IP"
    echo "2. Wait for DNS propagation (5-30 minutes)"
    exit 1
fi

echo "=== SSL + Nginx Setup for $DOMAIN ==="

# --- 1. Install Nginx + Certbot ---
echo ">>> Installing Nginx and Certbot..."
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

# --- 2. Create Nginx config ---
echo ">>> Creating Nginx configuration..."
sudo cat > /etc/nginx/sites-available/trading-bot << EOF
server {
    listen 80;
    server_name $DOMAIN;

    # Certbot will add redirect to HTTPS

    location /webhook {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 10s;
        proxy_send_timeout 10s;
        proxy_read_timeout 10s;
        client_max_body_size 1k;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location / {
        return 404;
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test config
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
echo "Nginx configured"

# --- 3. Get SSL certificate ---
echo ">>> Obtaining SSL certificate..."
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@$DOMAIN --redirect

# --- 4. Auto-renewal ---
echo ">>> Setting up auto-renewal..."
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer

echo ""
echo "=== SSL Setup Complete ==="
echo ""
echo "Your webhook URL:"
echo "  https://$DOMAIN/webhook"
echo ""
echo "Health check URL:"
echo "  https://$DOMAIN/health"
echo ""
echo "SSL auto-renewal is enabled."
echo "Use this webhook URL in TradingView alerts."
