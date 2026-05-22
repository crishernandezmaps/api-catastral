# api.catastral.cl — Instrucciones para agentes

Este repositorio es la plataforma **api.catastral.cl**.

## PROHIBIDO — CRÍTICO

- **NUNCA** escribir en `/var/www/catastral.cl/`. Esa ruta pertenece a `catastral.cl` (proyecto `catastro/`).
- **NUNCA** hacer rsync del `frontend/dist/` de este proyecto a `/var/www/catastral.cl/frontend/dist/`.
- **NUNCA** modificar `/etc/nginx/sites-available/catastral.cl` ni `/etc/nginx/sites-enabled/catastral.cl`.
- **NUNCA** reiniciar el servicio `catastro-api` (ese es el backend de catastral.cl, no de este proyecto).

El deploy de este proyecto va exclusivamente a su propia ruta en el VPS, no a `/var/www/catastral.cl/`.
