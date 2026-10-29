#!/bin/bash
cd /opt/cfdt/repo
git pull
docker compose config
docker compose up -d
docker ps
