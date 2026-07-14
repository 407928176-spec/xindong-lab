"""本地开发：加载 ``backend/.env``；已存在的环境变量不被覆盖（线上以系统注入为准）。"""

from pathlib import Path

from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parents[1]
load_dotenv(_backend_dir / ".env", override=False)
