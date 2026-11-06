# CI resolves upstream latest once; each platform uses the same immutable index.
# Deployment uses ghcr.io/zhangtyzzz/filecodebox-ratefix:latest, not this build input.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BASE_DIGEST
ARG MAINTENANCE_REVISION
ARG UPSTREAM_REVISION

COPY scripts/check_upstream.py /tmp/filecodebox-ratefix-check.py
COPY upstream-policy.json /tmp/filecodebox-ratefix-policy.json
COPY dependencies.py /tmp/filecodebox-ratefix-dependencies.py
RUN python /tmp/filecodebox-ratefix-check.py \
      --upstream /app/apps/base/dependencies.py \
      --replacement /tmp/filecodebox-ratefix-dependencies.py \
      --policy /tmp/filecodebox-ratefix-policy.json \
 && cp /tmp/filecodebox-ratefix-dependencies.py /app/apps/base/dependencies.py \
 && rm /tmp/filecodebox-ratefix-check.py /tmp/filecodebox-ratefix-policy.json /tmp/filecodebox-ratefix-dependencies.py

# Keep notices, patch source and the exact source archives named by upstream labels.
COPY LICENSE NOTICE.txt /usr/share/doc/filecodebox-ratefix/
COPY legal/ /usr/share/doc/filecodebox-ratefix/legal/
COPY dependencies.py upstream-policy.json /usr/share/doc/filecodebox-ratefix/source/
COPY build/source/ /usr/share/doc/filecodebox-ratefix/source/upstream/
LABEL org.opencontainers.image.source="https://github.com/zhangtyzzz/filecodebox-ratefix" \
      org.opencontainers.image.revision="${MAINTENANCE_REVISION}" \
      org.opencontainers.image.licenses="LGPL-3.0" \
      io.filecodebox.maintenance.base.digest="${BASE_DIGEST}" \
      io.filecodebox.maintenance.upstream.revision="${UPSTREAM_REVISION}" \
      io.filecodebox.maintenance.ratefix="bounded-per-event-sliding-window"
