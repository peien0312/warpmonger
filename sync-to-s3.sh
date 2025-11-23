#!/bin/bash
# Sync product images to S3, then optionally to EC2
# Usage: ./sync-to-s3.sh [--with-ec2]

# Configuration
S3_BUCKET="your-bucket-name"  # Change to your S3 bucket name
S3_PREFIX="products"  # Folder in S3 bucket
EC2_USER="ubuntu"
EC2_HOST="your-ec2-ip-or-domain"
EC2_PATH="/home/ubuntu/toy-seller-site/content/products"
SSH_KEY="~/.ssh/your-key.pem"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Starting product images sync to S3...${NC}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${YELLOW}AWS CLI not found. Install with: brew install awscli${NC}"
    exit 1
fi

# Sync to S3 (only images folders)
echo -e "${BLUE}Uploading to s3://${S3_BUCKET}/${S3_PREFIX}/${NC}"

aws s3 sync content/products/ s3://${S3_BUCKET}/${S3_PREFIX}/ \
  --exclude "*" \
  --include "*/images/*" \
  --exclude "*/images/thumb_*" \
  --delete \
  --acl public-read

echo -e "${GREEN}✓ S3 sync complete!${NC}"
echo ""
echo "Images available at: https://${S3_BUCKET}.s3.amazonaws.com/${S3_PREFIX}/"
echo ""

# Optionally sync from S3 to EC2
if [[ "$1" == "--with-ec2" ]]; then
    echo -e "${BLUE}Syncing from S3 to EC2...${NC}"

    ssh -i $SSH_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
cd /home/ubuntu/toy-seller-site
aws s3 sync s3://YOUR_BUCKET/products/ content/products/ \
  --exclude "*" \
  --include "*/images/*"
ENDSSH

    echo -e "${GREEN}✓ EC2 sync complete!${NC}"
fi
