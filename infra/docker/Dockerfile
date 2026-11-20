# syntax=docker/dockerfile:1
# Imagen On-Premise: Odoo oficial (Community) + módulos Enterprise (clon de github.com/odoo/enterprise,
# contexto «enterprise») + módulos propios del repo. Construir desde la raíz del repo (lo hace
# compose.onprem.yml). La imagen y Enterprise tienen que ser de la misma fecha
# (infra/scripts/fijar-enterprise.sh).
ARG ODOO_BASE_IMAGE=odoo:20.0
FROM ${ODOO_BASE_IMAGE}

USER root
# Enterprise sin la historia de git (el clon pesa ~1 GB con ella)
RUN --mount=type=bind,from=enterprise,source=.,target=/tmp/enterprise \
    mkdir -p /mnt/enterprise-addons \
    && tar -C /tmp/enterprise --exclude=.git -cf - . | tar -C /mnt/enterprise-addons -xf - \
    && chown -R odoo:odoo /mnt/enterprise-addons
# Dependencias Python de los módulos propios, si las hubiera.
# Los módulos propios van en /opt/comercio-addons y NO en /mnt/extra-addons: la imagen oficial declara
# /mnt/extra-addons como VOLUME, y al recrear el contenedor Docker reusaba ese volumen con los
# archivos viejos (04/11: producción corría con los módulos del 28/10 aunque la imagen era nueva).
COPY --chown=odoo:odoo addons/ /opt/comercio-addons/
RUN if [ -f /opt/comercio-addons/requirements.txt ]; then \
        pip3 install --no-cache-dir --break-system-packages -r /opt/comercio-addons/requirements.txt; \
    fi
USER odoo
