#!/bin/bash
# =============================================================================
# deploy.sh — Despliega API Catastral en el VPS
# Uso: ./scripts/deploy.sh
# =============================================================================

set -euo pipefail

VPS="46.62.214.65"
REMOTE_DIR="/root/api_catastral"
PORT=8003

echo "==> Sincronizando código al VPS..."
rsync -avz --exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='.env' \
    /Users/newmarkchile/Documents/TREMEN/5_PROJECTS/api_catastral/ \
    root@$VPS:$REMOTE_DIR/

echo "==> Instalando dependencias en VPS..."
ssh root@$VPS "
    cd $REMOTE_DIR
    python3 -m venv venv
    venv/bin/pip install -q -r requirements.txt
"

echo "==> Configurando .env en VPS..."
ssh root@$VPS "
    cat > $REMOTE_DIR/.env << 'EOF'
DB_HOST=127.0.0.1
DB_PORT=5435
DB_NAME=catastro
DB_USER=catastro_app
DB_PASSWORD=Catastr0_2026_Tr3m3n
DB_POOL_MIN=5
DB_POOL_MAX=20
EOF
"

echo "==> Deteniendo instancia anterior (si existe)..."
ssh root@$VPS "pkill -f 'uvicorn app.main:app.*$PORT' 2>/dev/null || true"
sleep 1

echo "==> Iniciando servicio en puerto $PORT..."
ssh root@$VPS "
    cd $REMOTE_DIR
    nohup venv/bin/uvicorn app.main:app \
        --host 127.0.0.1 \
        --port $PORT \
        --workers 4 \
        --log-level info \
        > /var/log/api_catastral.log 2>&1 &
    sleep 2
    curl -s http://127.0.0.1:$PORT/health
"

echo ""
echo "==> Verificando nginx config..."
ssh root@$VPS "nginx -t 2>&1"

echo ""
echo "Deployment completado."
echo "API disponible en: http://46.62.214.65:$PORT/docs (interno)"
echo "Configura api.catastral.cl en nginx para acceso público."
