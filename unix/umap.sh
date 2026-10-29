#!/bin/bash
cd /opt/cfdt/umap
docker compose config
docker compose up -d
docker ps
