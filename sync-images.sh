#!/bin/bash
# Sync product images to EC2 server
# Usage: ./sync-images.sh

# Configuration
EC2_USER="ec2-user"  # Change to your EC2 username (ubuntu, ec2-user, etc.)
EC2_HOST="35.78.242.30"  # Change to your EC2 IP or domain
EC2_PATH="/home/ec2-user/warpmonger/content/products"  # Path on EC2 server
SSH_KEY="~/.ssh/nownews.pem"  # Path to your SSH key

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting product images sync to EC2...${NC}"

# Sync images directory only (preserves structure)
rsync -avz --progress \
  -e "ssh -i $SSH_KEY" \
  --include='*/' \
  --include='*/images/***' \
  --exclude='*' \
  content/products/ \
  $EC2_USER@$EC2_HOST:$EC2_PATH/

echo -e "${GREEN}✓ Sync complete!${NC}"
echo ""
echo "Files synced to: $EC2_USER@$EC2_HOST:$EC2_PATH"
