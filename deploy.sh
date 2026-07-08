#!/bin/bash
# Deploy toy-seller-site (abbeystoys.com) to the GCP VM.
# Ships code only — venv, content/, images and legacy data stay put.
set -euo pipefail

PROJECT=warpmonger-prod
ZONE=asia-east1-b
VM=warpmonger-pos
TARBALL=$(mktemp -t abbeys-deploy).tar.gz

echo "==> packing"
tar czf "$TARBALL" \
    --exclude=venv --exclude=.git --exclude=__pycache__ \
    --exclude=content --exclude=all --exclude=line_shopping_output \
    --exclude=nohup.out --exclude='*.tar.gz' \
    app.py mailer.py payuni.py posdb.py linepay.py linepush.py memberdb.py notify_arrivals.py templates static requirements.txt

echo "==> uploading"
gcloud compute scp "$TARBALL" "$VM:/tmp/abbeys_deploy.tar.gz" \
    --project="$PROJECT" --zone="$ZONE" --quiet

echo "==> extracting + restarting"
gcloud compute ssh "$VM" --project="$PROJECT" --zone="$ZONE" --command='
    sudo -u warpmonger bash -c "cd /home/warpmonger/abbeystoys && tar xzf /tmp/abbeys_deploy.tar.gz" &&
    sudo systemctl restart abbeystoys && sleep 3 &&
    systemctl is-active abbeystoys &&
    curl -s -o /dev/null -w "local health: %{http_code}\n" http://127.0.0.1:5006/
'

echo "==> live check"
curl -s -o /dev/null -w "https://abbeystoys.com/ -> %{http_code}\n" --max-time 20 https://abbeystoys.com/
rm -f "$TARBALL"
echo "done"
