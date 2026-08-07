#!/usr/bin/env bash
set -euo pipefail
cd /root/VCF
source venv/bin/activate
pkill -f "uvicorn backend.demo1.main:app" 2>/dev/null || true
sleep 2
nohup python -m uvicorn backend.demo1.main:app --host 0.0.0.0 --port 5004 > backend.log 2>&1 &
echo "VCF backend started on port 5004 (PID $!)"
