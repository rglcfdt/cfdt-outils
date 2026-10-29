#!/bin/bash

set -e

echo "===================================="
echo " Déploiement CFDT"
echo "===================================="

cd /opt/cfdt/repo

echo ""
echo "=== Git status ==="
git status

echo ""
echo "=== Git add ==="
git add .

echo ""
read -p "Message du commit : " MESSAGE

git commit -m "$MESSAGE" || true

echo ""
echo "=== Push GitHub ==="
git push origin main

echo ""
echo "=== Pull sécurité ==="
git pull origin main

echo ""
echo "=== Build Docker ==="
docker compose build

echo ""
echo "=== Redémarrage ==="
docker compose up -d

echo ""
echo "=== Etat des conteneurs ==="
docker ps

echo ""
echo "=== Déploiement terminé ==="

