#!/bin/bash

set -e

cd /opt/cfdt/cfdt-accompagnement

git pull

docker compose down

docker compose up -d --build

docker ps

