#!/bin/sh
# Run once on 10.10.11.4 with sudo: folders, the media copy, nginx and the certificate.
set -eu
SITE=/etc/nginx/sites-available/member_onboarding
HERE=$(dirname "$0")

install -d -o hashkmpcl -g hashkmpcl /opt/member-onboarding
install -d -o 10001 -g 10001 -m 750 /opt/member-onboarding/media
if [ -d /home/hashkmpcl/mo_media ]; then
    cp -a /home/hashkmpcl/mo_media/. /opt/member-onboarding/media/
    chown -R 10001:10001 /opt/member-onboarding/media
fi

# Port 80 first, so certbot can prove the domain.
sed -n '1,/^}/p' "$HERE/support.kasheemilk.com.conf" > "$SITE"
ln -sf "$SITE" /etc/nginx/sites-enabled/member_onboarding
nginx -t
systemctl reload nginx

if [ ! -d /etc/letsencrypt/live/support.kasheemilk.com ]; then
    certbot certonly --webroot -w /var/www/certbot -d support.kasheemilk.com --non-interactive
fi

cp "$HERE/support.kasheemilk.com.conf" "$SITE"
nginx -t
systemctl reload nginx
echo "done: https://support.kasheemilk.com"
