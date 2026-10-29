#!/bin/bash

DATE=$(date +%F)

docker exec umap-db-1 pg_dump -U umap umap > /opt/cfdt/backups/umap_$(DATE).sql

tar -czf /opt/cfdt/backups/umap_uploads_$(DATE).tar.gz /opt/cfdt/umap/uploads

tar -czf /opt/cfdt/backups/config_$(DATE).tar.gz /etc/nginx /opt/cfdt/cfdt-accompagnement /opt/cfdt/umap

