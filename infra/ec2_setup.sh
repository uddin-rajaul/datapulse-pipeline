#!/usr/bin/env bash
# =============================================================================
# datapulse-pipeline: EC2 setup script
#
# Run once on a fresh Ubuntu 24.04 t3.micro after SSH-ing in.
# Usage:
#   chmod +x infra/ec2_setup.sh
#   ./infra/ec2_setup.sh
#
# What this does:
#   1. Installs Docker and Docker Compose plugin
#   2. Adds ubuntu user to docker group (no sudo needed after re-login)
#   3. Clones the repo
#   4. Sets up the .env file (you fill in secrets manually)
#   5. Starts Airflow via Docker Compose
#
# This script is idempotent — safe to re-run.
# =============================================================================

set -euo pipefail

REPO_URL="https://github.com/uddin-rajaul/datapulse-pipeline.git"
APP_DIR="/home/ubuntu/datapulse-pipeline"

echo "==> [1/5] Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo "==> [2/5] Installing Docker..."
# Official Docker install — don't use the Ubuntu snap or apt version,
# they lag behind and have been known to have compose issues.
sudo apt-get install -y ca-certificates curl gnupg lsb-release

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable docker
sudo systemctl start docker

echo "==> [3/5] Adding ubuntu to docker group..."
sudo usermod -aG docker ubuntu
# Note: group change only takes effect after re-login.
# The rest of this script uses sudo docker to avoid that requirement.

echo "==> [4/5] Cloning repo..."
if [ -d "$APP_DIR" ]; then
    echo "    Repo already exists, pulling latest..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

echo "==> [5/5] Setting up .env file..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "  *** .env created from .env.example ***"
    echo "  You must fill in the following before starting Airflow:"
    echo "    OPENWEATHER_API_KEY"
    echo "    RDS_HOST, RDS_DB, RDS_WRITER_USER, RDS_WRITER_PASSWORD"
    echo ""
    echo "  Edit with:  nano $APP_DIR/.env"
    echo ""
else
    echo "    .env already exists — skipping."
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Fill in secrets:     nano $APP_DIR/.env"
echo "  2. Start Airflow:       cd $APP_DIR && sudo docker compose up -d"
echo "  3. Wait ~60s, then:     sudo docker compose ps"
echo "  4. Access Airflow UI:   http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8080"
echo "     Login: admin / admin  (change this in production)"
echo ""
echo "Note: Log out and back in for docker group to take effect (so you can drop sudo)."
