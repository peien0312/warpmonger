# Warpmonger Deployment Guide

## Quick Commands

### Restart after code changes
```bash
sudo systemctl restart warpmonger
```

### Check status
```bash
sudo systemctl status warpmonger
```

### View logs
```bash
# Recent logs
sudo journalctl -u warpmonger -n 50

# Follow logs in real-time
sudo journalctl -u warpmonger -f
```

### Stop/Start
```bash
sudo systemctl stop warpmonger
sudo systemctl start warpmonger
```

---

## Service Details

- **Service file:** `/etc/systemd/system/warpmonger.service`
- **App runs on:** `127.0.0.1:5006`
- **Workers:** 4 gunicorn workers
- **Auto-start:** Enabled on boot

---

## Nginx

### Reload nginx (after config changes)
```bash
sudo nginx -t && sudo systemctl reload nginx
```

### Config location
`/etc/nginx/sites-available/warpmonger`

---

## SSL Certificate

- **Domain:** www.johnactionfigure.com, johnactionfigure.com
- **Auto-renewal:** Enabled via certbot timer
- **Check expiry:**
```bash
sudo certbot certificates
```

---

## Common Tasks

### Deploy code update
```bash
cd /home/ec2-user/warpmonger
git pull
sudo systemctl restart warpmonger
```

### Install new Python dependency
```bash
cd /home/ec2-user/warpmonger
source venv/bin/activate
pip install <package>
# Add to requirements.txt
sudo systemctl restart warpmonger
```

### Edit service config
```bash
sudo nano /etc/systemd/system/warpmonger.service
sudo systemctl daemon-reload
sudo systemctl restart warpmonger
```
