#!/bin/bash
# =============================================================================
# Oracle Cloud VM Initial Setup Script
# Run this ONCE after first SSH into your new Ubuntu 22.04 ARM VM
# Usage: bash setup-server.sh
# =============================================================================

set -e

echo "============================================"
echo "  Podcast Tool - Server Setup"
echo "============================================"

# --- System Updates ---
echo ""
echo "[1/6] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# --- Install Docker ---
echo ""
echo "[2/6] Installing Docker..."
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER

# --- Install Nginx ---
echo ""
echo "[3/6] Installing Nginx..."
sudo apt install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx

# --- Install Certbot (for SSL) ---
echo ""
echo "[4/6] Installing Certbot..."
sudo apt install -y certbot python3-certbot-nginx

# --- Install Git and utilities ---
echo ""
echo "[5/6] Installing utilities..."
sudo apt install -y git curl htop

# --- Open firewall ports (Oracle Linux uses iptables) ---
echo ""
echo "[6/6] Configuring OS firewall..."
# Ubuntu on Oracle Cloud uses iptables by default
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8080 -j ACCEPT

# Persist iptables rules
sudo apt install -y iptables-persistent
sudo netfilter-persistent save

echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "IMPORTANT: Log out and log back in for Docker group to take effect:"
echo "  exit"
echo "  ssh ubuntu@<your-vm-ip>"
echo ""
echo "Next steps:"
echo "  1. Clone your repo:  git clone <repo-url> podcast-tool"
echo "  2. Create .env file: cp deploy/.env.production .env"
echo "  3. Edit .env:        nano .env"
echo "  4. Deploy:           bash deploy/deploy.sh"
echo ""
