#!/usr/bin/env bash
# 心动实验室 —— 一键启动（macOS / Linux）
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

# Python 版本上限：只支持到 3.13，太新的（3.14+）游戏依赖还没适配、装了会崩
# （和 start.ps1 里的 $MaxPythonMinor 保持一致，改一处两处都要改）。
MAX_PY_MINOR=13

echo
echo "  ============================================"
echo "     心动实验室 —— 启动中"
echo "  ============================================"
echo

# ---------- 1. 检查运行环境 ----------
PYTHON_BIN=""
TOO_NEW_PY=""
for candidate in python3 python; do
  command -v "$candidate" >/dev/null 2>&1 || continue
  # 需要 3.11+（代码用了 StrEnum、X | Y 类型写法等新语法），但也不能太新：依赖只在
  # <=3.$MAX_PY_MINOR 上验证过，更新的会崩。只接受 3.11 ~ 3.$MAX_PY_MINOR 这个区间。
  if "$candidate" -c "import sys; v=(sys.version_info.major, sys.version_info.minor); sys.exit(0 if (3, 11) <= v <= (3, $MAX_PY_MINOR) else 1)" 2>/dev/null; then
    PYTHON_BIN="$candidate"
    break
  fi
  # 不在可用区间；如果是「太新」，记下版本号，下面给一句针对性的提示，而不是让它
  # 进到后面崩在一堆看不懂的 SQLAlchemy 报错里。
  if "$candidate" -c "import sys; v=(sys.version_info.major, sys.version_info.minor); sys.exit(0 if v > (3, $MAX_PY_MINOR) else 1)" 2>/dev/null; then
    TOO_NEW_PY="$("$candidate" -c 'import sys; print("%d.%d" % (sys.version_info.major, sys.version_info.minor))' 2>/dev/null || true)"
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  if [ -n "$TOO_NEW_PY" ]; then
    echo "  [x] 检测到 Python $TOO_NEW_PY，但游戏依赖目前还不支持这个版本。"
    echo
    echo "      请安装 Python 3.11 ~ 3.13 中的任意一个（推荐 3.13）："
    echo "      macOS：  brew install python@3.13"
    echo "      或访问： https://www.python.org/downloads/"
    echo
    exit 1
  fi
  echo "  [x] 没有找到 Python 3.11 ~ 3.13。"
  echo
  echo "      macOS：  brew install python@3.13"
  echo "      Ubuntu： sudo apt install python3 python3-venv"
  echo "      或访问： https://www.python.org/downloads/"
  echo
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "  [x] 没有找到 Node.js。"
  echo
  echo "      请安装 Node.js 20 或更新版本： https://nodejs.org/"
  echo
  exit 1
fi

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 20 ]; then
  echo "  [x] Node.js 版本过低（当前 $(node -v)），需要 20 或更新版本。"
  echo
  exit 1
fi

# ---------- 2. 后端依赖 ----------
VENV_PY="$ROOT/backend/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "  [1/4] 首次运行，正在准备后端环境..."
  echo "        这一步需要 3-5 分钟，只有第一次需要，请耐心等待。"
  echo
  "$PYTHON_BIN" -m venv "$ROOT/backend/.venv"
  "$VENV_PY" -m pip install --upgrade pip --quiet
  # 优先走清华镜像，国内网络快很多；失败自动退回官方源，双保险。
  echo "        正在下载依赖（走清华镜像加速）..."
  if ! "$VENV_PY" -m pip install -r "$ROOT/backend/requirements.txt" --quiet -i https://pypi.tuna.tsinghua.edu.cn/simple/; then
    echo "        镜像源失败，改用官方源重试..."
    "$VENV_PY" -m pip install -r "$ROOT/backend/requirements.txt" --quiet
  fi
else
  echo "  [1/4] 后端环境已就绪"
fi

# ---------- 3. 前端依赖 + 构建 ----------
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "  [2/4] 首次运行，正在准备前端环境（约 1-2 分钟）..."
  # 同样优先走 npmmirror 国内镜像（原淘宝源），失败退回官方源。
  echo "        正在下载依赖（走 npmmirror 国内镜像加速）..."
  if ! (cd "$ROOT/frontend" && npm install --no-audit --no-fund --registry https://registry.npmmirror.com); then
    echo "        镜像源失败，改用官方源重试..."
    (cd "$ROOT/frontend" && npm install --no-audit --no-fund)
  fi
else
  echo "  [2/4] 前端环境已就绪"
fi

# 判断「构建过」要看 BUILD_ID 在不在，不能只看 .next 目录在不在：构建一旦跑起来 .next
# 就被创建了，哪怕中途失败/被打断也在；BUILD_ID 是最后一步才写的，只有它在才说明上次
# 真的构建成功。否则会出现「看着构建过、其实是半成品，npm run start 起不来」的情况。
if [ ! -f "$ROOT/frontend/.next/BUILD_ID" ]; then
  echo "  [3/4] 首次运行，正在构建前端（约 1-3 分钟，只有第一次需要）..."
  (cd "$ROOT/frontend" && npm run build)
else
  echo "  [3/4] 前端已构建"
fi

# ---------- 4. 初始化数据库并启动 ----------
echo "  [4/4] 正在启动服务..."
"$VENV_PY" "$ROOT/backend/scripts/init_db.py"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo
  echo "  正在停止服务..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "  已停止。"
}
# Ctrl+C 或脚本退出时，两个子进程都要跟着关掉，否则端口会一直被占着。
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

(cd "$ROOT/frontend" && npm run start) &
FRONTEND_PID=$!

echo
echo "      正在等待服务就绪..."

# 轮询后端健康检查，最多等 60 秒。就绪前打开浏览器只会看到报错页。
READY=0
for _ in $(seq 1 60); do
  if curl -fs -o /dev/null http://127.0.0.1:8000/api/health 2>/dev/null; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -eq 0 ]; then
  echo "  [x] 后端启动超时，请查看上面的报错信息。"
  exit 1
fi

# 前端 next start 比后端稍慢，同样轮询就绪再打开浏览器，否则会先看到报错页。
for _ in $(seq 1 30); do
  if curl -fs -o /dev/null http://127.0.0.1:3000 2>/dev/null; then
    break
  fi
  sleep 1
done

echo
echo "  ============================================"
echo "     启动完成！"
echo
echo "     游戏地址： http://127.0.0.1:3000"
echo "     首次使用请在网页上填入你的大模型信息"
echo
echo "     停止游戏：在本窗口按 Ctrl+C"
echo "  ============================================"
echo

if command -v open >/dev/null 2>&1; then
  open http://127.0.0.1:3000            # macOS
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://127.0.0.1:3000 >/dev/null 2>&1 || true   # Linux
fi

# 前台等待，让 Ctrl+C 能被 trap 接住
wait
