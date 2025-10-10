#!/bin/bash
set -e

echo "=== VPS Deployment Script (1GB RAM) ==="

if [ "$EUID" -ne 0 ]; then
   echo "Please run as root or with sudo"
   exit 1
fi

APP_DIR="/opt/defi-oi-monitor"
APP_USER="defioi"

echo "1. Creating app user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash $APP_USER
fi

echo "2. Installing dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv nginx

echo "3. Setting up application directory..."
mkdir -p $APP_DIR
cp -r . $APP_DIR/
chown -R $APP_USER:$APP_USER $APP_DIR

echo "4. Creating Python virtual environment..."
sudo -u $APP_USER python3 -m venv $APP_DIR/venv
sudo -u $APP_USER $APP_DIR/venv/bin/pip install --no-cache-dir -r $APP_DIR/requirements.txt

echo "5. Creating systemd services..."
cp deployment/scraper.service /etc/systemd/system/
cp deployment/streamlit.service /etc/systemd/system/

echo "6. Configuring nginx..."
cp deployment/nginx.conf /etc/nginx/sites-available/defi-oi
ln -sf /etc/nginx/sites-available/defi-oi /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t

echo "7. Starting services..."
systemctl daemon-reload
systemctl enable scraper streamlit nginx
systemctl start scraper streamlit
systemctl restart nginx

echo ""
echo "=== Deployment Complete ==="
echo "Application running at http://YOUR_VPS_IP"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status scraper"
echo "  sudo systemctl status streamlit"
echo "  sudo journalctl -u scraper -f"
echo "  sudo journalctl -u streamlit -f"
