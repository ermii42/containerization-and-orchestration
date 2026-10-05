#!/usr/bin/env bash
# mydocker.sh — запуск api в изолированных namespace с cgroup-лимитами
set -euo pipefail

APP_DIR="${APP_DIR:-$PWD/pr1-docker/python-app}"
PYTHON_BIN="${PYTHON_BIN:-$PWD/.venv/bin/python}"
CGROUP_DIR="/sys/fs/cgroup/myapp"
VETH_HOST="veth-host"
VETH_CONT="veth-cont"
HOST_IP="192.168.100.1"
CONT_IP="192.168.100.2"
HEALTH_PORT="${HEALTH_PORT:-8000}"

log() { printf '[mydocker] %s\n' "$*"; }

# --- 0. AppArmor unprivileged userns ---
log "sysctl: разрешаем unprivileged userns"
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0 >/dev/null

# --- 1. Создание cgroup v2 и контроллеров ---
log "создаём cgroup $CGROUP_DIR"
sudo mkdir -p "$CGROUP_DIR"

# включаем cpu controller на корневом уровне, если ещё не включён
if ! grep -q cpu /sys/fs/cgroup/cgroup.subtree_control 2>/dev/null; then
  echo "+cpu" | sudo tee /sys/fs/cgroup/cgroup.subtree_control >/dev/null
fi

# включаем cpu controller в нашей cgroup, чтобы cpu.max был доступен
if [ -w "$CGROUP_DIR/cgroup.subtree_control" ]; then
  echo "+cpu" | sudo tee "$CGROUP_DIR/cgroup.subtree_control" >/dev/null || true
fi

# лимиты
echo "50000 100000" | sudo tee "$CGROUP_DIR/cpu.max" >/dev/null
echo 10 | sudo tee "$CGROUP_DIR/pids.max" >/dev/null
log "лимиты: cpu.max=50000/100000 (0.5 CPU), pids.max=10"

# --- 2. Запуск процесса в новых namespace ---
log "запускаем api в новых namespace"
unshare --user --map-root-user --pid --mount --net --uts --ipc --fork --mount-proc \
  setpriv --inh-caps=-all --bounding-set=-all --no-new-privs \
  "$PYTHON_BIN" "$APP_DIR/wrapper.py" &
WRAPPER_PID=$!
log "unshare PID (host): $WRAPPER_PID"

# ждём появления именно python-потомка
PID=""
for i in $(seq 1 100); do
  PID=$(pgrep -P "$WRAPPER_PID" -f "wrapper.py" | head -1 || true)
  [ -n "$PID" ] && break
  # если unshare уже умер — дальше ждать бессмысленно
  kill -0 "$WRAPPER_PID" 2>/dev/null || break
  sleep 0.1
done

if [ -z "$PID" ]; then
  log "FAIL: потомок unshare не найден"
  exit 1
fi
log "целевой PID (host) для cgroup/nsenter: $PID"
log "NSpid для $PID: $(grep NSpid /proc/$PID/status)"

# --- 3. Помещаем процесс в cgroup ---
echo "$PID" | sudo tee "$CGROUP_DIR/cgroup.procs" >/dev/null
log "процесс $PID добавлен в cgroup"

# --- 4. Настройка сети ---
log "чистим старые veth (если остались)"
sudo ip link del "$VETH_HOST" 2>/dev/null || true

log "создаём veth pair"
sudo ip link add "$VETH_HOST" type veth peer name "$VETH_CONT"

log "переносим $VETH_CONT в netns $PID"
sudo ip link set "$VETH_CONT" netns "$PID"

sudo ip addr add "$HOST_IP/24" dev "$VETH_HOST" 2>/dev/null || true
sudo ip link set "$VETH_HOST" up

log "настраиваем сеть внутри namespace"
sudo nsenter -t "$PID" -n ip addr add "$CONT_IP/24" dev "$VETH_CONT" 2>/dev/null || true
sudo nsenter -t "$PID" -n ip link set "$VETH_CONT" up
sudo nsenter -t "$PID" -n ip link set lo up
log "сеть: $HOST_IP <-> $CONT_IP"

# --- 5. Проверка /health ---
log "ждём поднятия сервиса..."
for i in $(seq 1 15); do
  if curl -sf "http://$CONT_IP:$HEALTH_PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

log "api запущен. PID=$PID, health: http://$CONT_IP:$HEALTH_PORT/health"
log "для остановки: sudo kill $WRAPPER_PID && sudo ip link del $VETH_HOST"