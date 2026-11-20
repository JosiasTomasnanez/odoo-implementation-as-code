# Caddy con el plugin DNS del proveedor elegido (ADR 0013).
# El plugin solo se usa en el modo "dominio" (Let's Encrypt por DNS-01); en el modo
# "interna" no molesta. Con CADDY_DNS_MODULE vacío se compila Caddy sin plugins.
ARG CADDY_VERSION=2.11.7

FROM caddy:${CADDY_VERSION}-builder AS builder
ARG CADDY_DNS_MODULE=github.com/caddy-dns/cloudflare@v0.2.4
RUN xcaddy build ${CADDY_DNS_MODULE:+--with ${CADDY_DNS_MODULE}}

FROM caddy:${CADDY_VERSION}
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
