#!/bin/bash
# ============================================
# VPS Initial Setup Script
# Run this once on a fresh AWS Lightsail Ubuntu instance
# ============================================

set -e

echo "=== IB Trading Bot VPS Setup ==="

# 1. System update
echo ">>> Updating system..."
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install Docker
echo ">>> Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
rm get-docker.sh

# 3. Install Docker Compose
echo ">>> Installing Docker Compose..."
sudo apt-get install -y docker-compose-plugin

# 4. Install Nginx
echo ">>> Installing Nginx..."
sudo apt-get install -y nginx

# 5. Install Certbot (Let's Encrypt SSL)
echo ">>> Installing Certbot..."
sudo apt-get install -y certbot python3-certbot-nginx

# 6. Install Java (required for IB Gateway)
echo ">>> Installing Java..."
sudo apt-get install -y default-jre

# 7. Install IBC (IB Controller) dependencies
echo ">>> Installing IBC dependencies..."
sudo apt-get install -y xvfb x11vnc

# 8. Create project directory
echo ">>> Creating project directory..."
mkdir -p ~/ib-trading-bot
cd ~/ib-trading-bot

# 9. Set up firewall
echo ">>> Configuring firewall..."
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (redirect to HTTPS)
sudo ufw allow 443/tcp   # HTTPS (webhook)
sudo ufw --force enable

# 10. Create swap (helps on 2GB instances)
echo ">>> Creating swap..."
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Log out and back in (for Docker group)"
echo "2. Copy project files to ~/ib-trading-bot/"
echo "3. Copy .env.example to .env and fill in values"
echo "4. Install IB Gateway and IBC"
echo "5. Set up SSL: sudo certbot --nginx -d your_domain.com"
echo "6. Start services: docker compose up -d"
echo ""
