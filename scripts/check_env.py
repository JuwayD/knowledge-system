import os
import subprocess
import sys
from pathlib import Path

checks = []


def check(name: str, cmd: list, version_flag: str = ""):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        ver = result.stdout.strip().split("\n")[0] if result.stdout else "OK"
        checks.append({"name": name, "ok": result.returncode == 0, "detail": ver})
    except (FileNotFoundError, subprocess.TimeoutExpired):
        checks.append({"name": name, "ok": False, "detail": "NOT FOUND"})


def check_python_module(name: str):
    try:
        __import__(name)
        checks.append({"name": f"Python: {name}", "ok": True, "detail": "OK"})
    except ImportError:
        checks.append({"name": f"Python: {name}", "ok": False, "detail": "MISSING"})


print("=== knowledge-system 环境检查 ===\n")

check("Python 3", [sys.executable, "--version"])
check_python_module("yaml")
check_python_module("json")
check("Node.js", ["node", "--version"])
check("Git", ["git", "--version"])

try:
    result = subprocess.run(["npm", "--version"], capture_output=True, text=True, timeout=5, shell=True)
    checks.append({"name": "npm", "ok": result.returncode == 0, "detail": f"v{result.stdout.strip()}"})
except Exception:
    checks.append({"name": "npm", "ok": False, "detail": "NOT FOUND"})

lark_cli = os.environ.get(
    "LARK_CLI_PATH",
    str(Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@larksuite/cli/bin/lark-cli.exe"),
)
if not Path(lark_cli).exists():
    lark_cli = "lark-cli"
check("lark-cli", [lark_cli, "--version"])

data_dir = Path(__file__).resolve().parent.parent / "data"
checks.append(
    {
        "name": "data/ 目录",
        "ok": data_dir.exists(),
        "detail": "OK" if data_dir.exists() else "RUN: python kb.py init",
    }
)

config_path = data_dir / "feishu-config.json"
checks.append(
    {
        "name": "飞书配置",
        "ok": config_path.exists(),
        "detail": "OK" if config_path.exists() else "RUN: python feishu.py setup",
    }
)

passed = 0
failed = 0
for c in checks:
    icon = "OK" if c["ok"] else "MISSING"
    print(f"  [{icon:7}] {c['name']}: {c['detail']}")
    if c["ok"]:
        passed += 1
    else:
        failed += 1

print(f"\n{passed} passed, {failed} missing")

if failed > 0:
    print("\n修复建议：")
    print("  pip install -r requirements.txt    # Python 依赖")
    print("  npm install -g @larksuite/cli      # lark-cli")
    print("  python kb.py init                  # 初始化数据目录")
    print("  python feishu.py setup             # 飞书首次配置")
    sys.exit(1)

print("\n环境完整，可以开始使用。")
