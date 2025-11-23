# Deployment Guide: Syncing Product Images

Product images are **not tracked in git** (they're in .gitignore). Here's how to sync them to your production server.

## Quick Start

### Option 1: Direct rsync to EC2 (Recommended for Start)

**Pros:** Simple, fast, maintains exact file structure
**Cons:** Not scalable for heavy traffic

```bash
# 1. Configure the script
nano sync-images.sh

# Update these variables:
EC2_USER="ubuntu"                    # Your EC2 username
EC2_HOST="your-server.com"           # Your EC2 IP or domain
SSH_KEY="~/.ssh/your-key.pem"        # Path to SSH key

# 2. Make executable and run
chmod +x sync-images.sh
./sync-images.sh
```

**What it does:**
- Uploads all images from `content/products/*/images/` to EC2
- Preserves directory structure
- Only syncs new/changed files (fast updates)
- Excludes product.md and tags.txt (those are in git)

### Option 2: S3 + CloudFront (Recommended for Production)

**Pros:** Scalable, fast CDN delivery, cheaper bandwidth
**Cons:** More setup, ongoing S3 costs

```bash
# 1. Create S3 bucket
aws s3 mb s3://your-toy-images

# 2. Configure the script
nano sync-to-s3.sh

# Update S3_BUCKET variable
S3_BUCKET="your-toy-images"

# 3. Sync to S3
chmod +x sync-to-s3.sh
./sync-to-s3.sh

# 4. (Optional) Also sync to EC2 for backup
./sync-to-s3.sh --with-ec2
```

## Deployment Workflow

### Initial Deployment

```bash
# On your Mac (local development)
git add .
git commit -m "Update product features"
git push origin main

# SSH to EC2
ssh -i ~/.ssh/your-key.pem ubuntu@your-server.com

# On EC2
cd ~/toy-seller-site
git pull origin main

# Install dependencies if needed
source venv/bin/activate
pip install -r requirements.txt

# Restart the app
sudo systemctl restart toy-seller
```

### Sync Images (Choose One)

**After importing new products:**

```bash
# Option A: Direct to EC2
./sync-images.sh

# Option B: To S3 (then optionally to EC2)
./sync-to-s3.sh --with-ec2
```

## File Structure After Sync

```
EC2: /home/ubuntu/toy-seller-site/
├── app.py                           # From git
├── content/products/
│   ├── Warhammer 40,000/
│   │   └── space-marine/
│   │       ├── product.md           # From git
│   │       ├── tags.txt             # From git
│   │       └── images/              # From rsync/S3 ✓
│   │           ├── editor_1.jpg
│   │           ├── gallery_1.jpg
│   │           └── video_001.mp4
```

## Using S3 for Image Serving

If you upload to S3, update your `app.py` to serve from S3:

```python
# app.py - Add configuration
USE_S3 = os.getenv('USE_S3', 'false').lower() == 'true'
S3_BUCKET = os.getenv('S3_BUCKET', '')
S3_PREFIX = os.getenv('S3_PREFIX', 'products')

# Update image URL generation
def get_image_url(category, slug, filename):
    if USE_S3:
        return f"https://{S3_BUCKET}.s3.amazonaws.com/{S3_PREFIX}/{category}/{slug}/images/{filename}"
    else:
        return f"/static/images/products/{category}/{slug}/{filename}"
```

Then set environment variables on EC2:

```bash
# On EC2, add to ~/.bashrc or systemd service
export USE_S3=true
export S3_BUCKET=your-toy-images
export S3_PREFIX=products
```

## AWS S3 Setup (Detailed)

### 1. Create S3 Bucket

```bash
# Install AWS CLI (if not installed)
brew install awscli  # On Mac
# OR
sudo apt install awscli  # On Ubuntu/EC2

# Configure AWS credentials
aws configure
# Enter: Access Key, Secret Key, Region (us-east-1), Format (json)

# Create bucket
aws s3 mb s3://your-toy-images --region us-east-1

# Set public read policy (for public website)
cat > bucket-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::your-toy-images/*"
    }
  ]
}
EOF

aws s3api put-bucket-policy --bucket your-toy-images --policy file://bucket-policy.json
```

### 2. (Optional) Add CloudFront CDN

CloudFront makes images load faster worldwide:

```bash
# Create CloudFront distribution via AWS Console:
# 1. Go to CloudFront > Create Distribution
# 2. Origin Domain: your-toy-images.s3.amazonaws.com
# 3. Viewer Protocol: Redirect HTTP to HTTPS
# 4. Cache Policy: CachingOptimized
# 5. Create

# Get your CloudFront domain (e.g., d111111abcdef8.cloudfront.net)
# Update app.py to use CloudFront URL
```

## Continuous Sync Setup

### Option A: Cron Job (Automated Sync)

On your Mac, set up automatic sync every hour:

```bash
# Edit crontab
crontab -e

# Add this line (sync every hour)
0 * * * * cd /Users/peienwang/toy-seller-site && ./sync-images.sh >> /tmp/sync-images.log 2>&1
```

### Option B: Git Hook (Sync on Commit)

Sync images whenever you commit:

```bash
# Create post-commit hook
cat > .git/hooks/post-commit <<'EOF'
#!/bin/bash
# Check if any product images changed
if git diff --name-only HEAD~1..HEAD | grep -q "content/products/.*/images/"; then
    echo "Product images changed, syncing to server..."
    ./sync-images.sh
fi
EOF

chmod +x .git/hooks/post-commit
```

## Troubleshooting

### "Permission denied" when syncing to EC2

```bash
# Fix SSH key permissions
chmod 400 ~/.ssh/your-key.pem
```

### "AWS credentials not found"

```bash
# Configure AWS CLI
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
```

### Images not showing on website

```bash
# Check file permissions on EC2
ssh -i ~/.ssh/your-key.pem ubuntu@your-server.com
cd ~/toy-seller-site/content/products
find . -name "*.jpg" -exec chmod 644 {} \;
find . -type d -exec chmod 755 {} \;
```

## Cost Estimates (AWS S3)

**For ~5,000 images (average 200KB each = ~1GB total):**

- **S3 Storage:** $0.023/GB/month = **~$0.03/month**
- **Data Transfer:** First 1GB free, then $0.09/GB
  - 10,000 views/month (~10GB) = **~$0.81/month**
- **CloudFront (optional):** First 50GB free = **$0/month** for small sites

**Total: ~$1/month** for small to medium traffic

## Best Practices

1. **Development (local):**
   - Keep all images in `content/products/*/images/`
   - Use `import_from_salessite.py` to import new products

2. **Version Control (git):**
   - Only commit code and `product.md` / `tags.txt`
   - Images stay in `.gitignore`

3. **Production (EC2):**
   - Sync images via rsync or S3
   - Code via git pull
   - Never edit files directly on server

4. **Scaling:**
   - Start with rsync (simple)
   - Move to S3 when traffic grows
   - Add CloudFront when going international

## Summary Commands

```bash
# Daily workflow
git add .
git commit -m "Update products"
git push

# When images change
./sync-images.sh              # Direct to EC2
# OR
./sync-to-s3.sh --with-ec2   # Via S3

# On EC2
ssh ubuntu@your-server
cd ~/toy-seller-site
git pull
sudo systemctl restart toy-seller
```
