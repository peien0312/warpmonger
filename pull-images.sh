#!/bin/bash
# Pull product images from EC2 server (server is single source of truth)
# Usage: ./pull-images.sh

# Configuration
EC2_USER="ec2-user"  # Change to your EC2 username (ubuntu, ec2-user, etc.)
EC2_HOST="35.78.242.30"  # Change to your EC2 IP or domain
EC2_PATH="/home/ec2-user/warpmonger/content/products"  # Path on EC2 server
SSH_KEY="~/.ssh/nownews.pem"  # Path to your SSH key
LOCAL_PATH="content/products"  # Local path

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Pulling product images from EC2 (server is source of truth)...${NC}"
echo -e "${YELLOW}Warning: Local images not on server will be deleted!${NC}"
echo ""

# Sync images from server to local
# --delete removes local files not present on server
rsync -avz --progress --delete \
  -e "ssh -i $SSH_KEY" \
  --include='*/' \
  --include='*/images/***' \
  --exclude='*' \
  $EC2_USER@$EC2_HOST:$EC2_PATH/ \
  $LOCAL_PATH/

echo -e "${GREEN}✓ Pull complete!${NC}"
echo ""
echo "Images pulled from: $EC2_USER@$EC2_HOST:$EC2_PATH"
echo "Local images now match server."
