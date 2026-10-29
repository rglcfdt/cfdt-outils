#!/usr/bin/env bash
set -u

OUTPUT="${1:-/opt/cfdt/data/audit/vps_security_audit.json}"
HOSTNAME="$(hostname -f 2>/dev/null || hostname)"
DATE="$(date -Is)"

json_escape() {
    python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

run() {
    "$@" 2>&1 || true
}

echo "{" > "$OUTPUT"
echo "  \"audit\": {" >> "$OUTPUT"
echo "    \"date\": $(printf '%s' "$DATE" | json_escape)," >> "$OUTPUT"
echo "    \"hostname\": $(printf '%s' "$HOSTNAME" | json_escape)" >> "$OUTPUT"
echo "  }," >> "$OUTPUT"

echo '  "checks": {' >> "$OUTPUT"

# OS
OS="$(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2- | tr -d '"')"
echo "    \"os\": $(printf '%s' "$OS" | json_escape)," >> "$OUTPUT"

# Kernel
KERNEL="$(uname -r)"
echo "    \"kernel\": $(printf '%s' "$KERNEL" | json_escape)," >> "$OUTPUT"

# Uptime
UPTIME="$(uptime -p 2>/dev/null || true)"
echo "    \"uptime\": $(printf '%s' "$UPTIME" | json_escape)," >> "$OUTPUT"

# Listening ports
PORTS="$(ss -lntup 2>/dev/null || true)"
echo "    \"listening_ports\": $(printf '%s' "$PORTS" | json_escape)," >> "$OUTPUT"

# Firewall
if command -v ufw >/dev/null 2>&1; then
    FIREWALL="$(ufw status 2>/dev/null || true)"
elif command -v firewall-cmd >/dev/null 2>&1; then
    FIREWALL="$(firewall-cmd --list-all 2>/dev/null || true)"
else
    FIREWALL="No supported firewall detected"
fi

echo "    \"firewall\": $(printf '%s' "$FIREWALL" | json_escape)," >> "$OUTPUT"

# SSH
SSH_CONFIG=""

if [ -f /etc/ssh/sshd_config ]; then
    SSH_CONFIG="$(
        grep -Ei \
        '^(Port|PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|PermitEmptyPasswords|MaxAuthTries)' \
        /etc/ssh/sshd_config 2>/dev/null || true
    )"
fi

echo "    \"ssh\": $(printf '%s' "$SSH_CONFIG" | json_escape)," >> "$OUTPUT"

# Streamlit
STREAMLIT_VERSION="not detected"

if command -v python3 >/dev/null 2>&1; then
    STREAMLIT_VERSION="$(
        python3 -m pip show streamlit 2>/dev/null |
        awk '/^Version:/ {print $2}'
    )"
fi

echo "    \"streamlit_version\": $(printf '%s' "$STREAMLIT_VERSION" | json_escape)," >> "$OUTPUT"

# Streamlit process
STREAMLIT_PROCESS="$(ps aux | grep '[s]treamlit' || true)"
echo "    \"streamlit_process\": $(printf '%s' "$STREAMLIT_PROCESS" | json_escape)," >> "$OUTPUT"

# Port 8501
if ss -lnt 2>/dev/null | grep -q ':8501'; then
    STREAMLIT_PORT="LISTENING"
else
    STREAMLIT_PORT="NOT_LISTENING"
fi

echo "    \"streamlit_port\": \"$STREAMLIT_PORT\"," >> "$OUTPUT"

# Nginx
if command -v nginx >/dev/null 2>&1; then
    NGINX_VERSION="$(nginx -v 2>&1)"
else
    NGINX_VERSION="not installed"
fi

echo "    \"nginx\": $(printf '%s' "$NGINX_VERSION" | json_escape)," >> "$OUTPUT"

# Docker
if command -v docker >/dev/null 2>&1; then
    DOCKER_VERSION="$(docker --version 2>/dev/null || true)"
    DOCKER_CONTAINERS="$(docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null || true)"
else
    DOCKER_VERSION="not installed"
    DOCKER_CONTAINERS=""
fi

echo "    \"docker\": $(printf '%s' "$DOCKER_VERSION" | json_escape)," >> "$OUTPUT"
echo "    \"docker_containers\": $(printf '%s' "$DOCKER_CONTAINERS" | json_escape)," >> "$OUTPUT"

# Secrets filenames only - never content
SECRETS="$(
    find /var/www /opt /srv /home \
    -type f \
    \( -name '.env' -o -name 'secrets.toml' -o -name '*.pem' -o -name '*.key' \) \
    2>/dev/null |
    head -n 200
)"

echo "    \"potential_secrets\": $(printf '%s' "$SECRETS" | json_escape)," >> "$OUTPUT"

# World writable files
WRITABLE="$(
    find /var/www /opt /srv \
    -type f -perm -0002 \
    2>/dev/null |
    head -n 100
)"

echo "    \"world_writable\": $(printf '%s' "$WRITABLE" | json_escape)," >> "$OUTPUT"

# Failed systemd services
FAILED_SERVICES="$(
    systemctl --failed --no-legend 2>/dev/null || true
)"

echo "    \"failed_services\": $(printf '%s' "$FAILED_SERVICES" | json_escape)" >> "$OUTPUT"

echo "  }" >> "$OUTPUT"
echo "}" >> "$OUTPUT"

chmod 600 "$OUTPUT"

echo "$OUTPUT"
