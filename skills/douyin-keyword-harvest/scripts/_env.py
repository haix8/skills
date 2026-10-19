#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公共前置检查：定位浏览器通道（cdp.py）+ 确认调试浏览器可达。

浏览器通道已**内嵌在 scripts/**，开箱即用，不需要额外安装任何技能。
若用户自己装了市场版 browser-automation-cdp 并想用那一份，用 --cdp-skill 指过去即可。

退出码约定：2 = 找不到浏览器通道；3 = 找到了但调试浏览器不可达。
"""
import subprocess
import sys
from pathlib import Path

BROWSER_SKILL = "browser-automation-cdp"
VENDOR_HINT = (
    "找不到浏览器通道 cdp.py。\n"
    "  → 正常情况下它内嵌在 本技能/scripts/cdp.py，不该缺失；\n"
    "    请检查技能包是否解压完整。\n"
    "  → 若想改用市场版技能，用 --cdp-skill <技能目录> 指定。\n"
)

CDP_HINT = (
    "调试浏览器不可达（CDP 无响应）。本技能只负责驱动浏览器，不代替浏览器本体：\n"
    "  → 启动：python <本技能>/scripts/start_chrome.py\n"
    "  → 然后复核：python <本技能>/scripts/cdp.py status 应返回 CDP_OK\n"
    "  → 若该环境不允许 Chrome 启用自身沙箱（start_chrome.py 打印 READY 但进程随即退出，\n"
    "    日志含 'sandbox initialization failed'），改用手工常驻启动：\n"
    "    chrome --remote-debugging-port=9222 --user-data-dir=<配置目录> \\\n"
    "          --no-first-run --no-sandbox --disable-gpu --disable-dev-shm-usage about:blank\n"
    "    详见 references/browser-automation-cdp.md 的「受限环境启动（沙箱不可用）」一节。\n"
)


def _has_cdp(d):
    return (d / "cdp.py").is_file()


def _candidate_dirs():
    """按优先级列出可能存放 cdp.py 的目录。"""
    here = Path(__file__).resolve().parent      # <本技能>/scripts
    skill_root = here.parent                    # <本技能>
    home = Path.home()
    raw = [
        here,                                       # ① 内嵌副本（默认，最优先）
        home / ".workbuddy" / "skills" / BROWSER_SKILL / "scripts",   # ② 用户装的市场版
        skill_root.parent / BROWSER_SKILL / "scripts",          # ③ 与本技能同级安装
        skill_root / BROWSER_SKILL / "scripts",                 # ④ 被塞进本技能目录
    ]
    seen, out = set(), []
    for c in raw:
        k = str(c).lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def resolve_browser_dir(explicit=None):
    """返回**含 cdp.py 的目录**。解析不了则提示并退出(2)。

    显式指定路径且无效时直接报错，不静默回退 —— 否则路径写错会被掩盖。
    """
    if explicit:
        d = Path(explicit).expanduser()
        for cand in (d, d / "scripts"):        # 容许传技能根目录或 scripts 目录
            if _has_cdp(cand):
                return cand
        print("--cdp-skill 指定的路径无效：%s\n（在该目录或其 scripts/ 下都找不到 cdp.py）\n\n%s"
              % (d, VENDOR_HINT), file=sys.stderr)
        sys.exit(2)

    for d in _candidate_dirs():
        if _has_cdp(d):
            return d

    print(VENDOR_HINT + "  已尝试：%s\n" % " , ".join(str(d) for d in _candidate_dirs()),
          file=sys.stderr)
    sys.exit(2)


def preflight_cdp(browser_dir):
    """确认调试浏览器可达。不可达时给出启动指引并退出(3)。"""
    cdp_py = Path(browser_dir) / "cdp.py"
    cmd = [sys.executable, str(cdp_py), "status"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as exc:
        print("无法执行 cdp.py：%s\n\n%s" % (exc, CDP_HINT), file=sys.stderr)
        sys.exit(3)
    if p.returncode == 0 and "CDP_OK" in p.stdout:
        return True
    print((p.stdout or "").strip() + "\n\n" + CDP_HINT, file=sys.stderr)
    sys.exit(3)


def cdp_cmd(browser_dir, port):
    """拼出调用 cdp.py 的基础命令。"""
    return [sys.executable, str(Path(browser_dir) / "cdp.py"), "--port", str(port)]
