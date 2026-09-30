# -*- coding: utf-8 -*-
"""DSH 小鲸鱼桌面挂件（Python 版）—— 数据层。

只读取 DSH 已经落地的文件，保证 Python 挂件与 DSH 插件看到的是同一份数据：

  %USERPROFILE%\\.dsh\\.credentials.yaml   DSH 凭据（取 DEEPSEEK_API_KEY）
  %USERPROFILE%\\.dsh\\.dshw-size.json     挂件设置（scale / sound / 音量 / 音效组 …）
  %USERPROFILE%\\.dsh\\.dshw-usage.json    小鲸鱼记账账本（今日已用 + events 逐轮消耗）
  %USERPROFILE%\\.dsh\\.dshw-turn.json     每轮消耗的 seq（判断"是否又聊了一轮"）

余额直接问 DeepSeek 官方接口，不经过任何中转。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BALANCE_URL = "https://api.deepseek.com/user/balance"
USER_AGENT = "dsh-whale-pet-py/1.0 (+https://github.com/MeteorNOX/DeepSeek-Balance-Whale-Widget)"

# 本挂件自己的状态文件（位置/大小/模式），与 DSH 插件的文件互不干扰
STATE_FILE = ".dshw-py-pet.json"


def dsh_home() -> str:
    """DSH 主目录：优先环境变量，否则 ~/.dsh。"""
    env = os.environ.get("DSH_HOME")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".dsh")


def dsh_path(*names: str) -> str:
    return os.path.join(dsh_home(), *names)


def read_json(path: str, default=None):
    """读 JSON；文件不存在/损坏一律回落到默认值（挂件不能因为半个写坏的文件崩掉）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def write_json(path: str, data) -> bool:
    """原子写 JSON（先写 .tmp 再替换），避免断电/并发把文件写坏。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# DSH 凭据（.credentials.yaml）
# 只处理 DSH 实际写出的结构：
#   version: 1
#   refs:
#     DEEPSEEK_API_KEY: "sk-xxxx"
# --------------------------------------------------------------------------
def _unquote(value: str) -> str:
    s = str(value or "").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            return json.loads(s)
        except Exception:
            return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    return s


def read_credentials(path: str | None = None) -> dict:
    """返回 {ref 名: 值}；文件不存在时返回 {}。"""
    path = path or dsh_path(".credentials.yaml")
    refs: dict = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except Exception:
        return refs

    in_refs = False
    for line in lines:
        if line.strip().startswith("#"):
            continue
        if line.rstrip() == "refs:":
            in_refs = True
            continue
        if line and not line[:1].isspace():
            # 到了 refs 之外的顶层键
            in_refs = False
            continue
        if in_refs:
            stripped = line.strip()
            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                if key:
                    refs[key] = _unquote(value)
    return refs


def api_key() -> str | None:
    """DEEPSEEK_API_KEY：环境变量优先，其次 DSH 凭据文件。"""
    env = os.environ.get("DEEPSEEK_API_KEY")
    if env and env.strip():
        return env.strip()
    value = read_credentials().get("DEEPSEEK_API_KEY")
    return value.strip() if value else None


# --------------------------------------------------------------------------
# 余额
# --------------------------------------------------------------------------
def fetch_balance(key: str | None = None, timeout: float = 8.0) -> dict:
    """查询 DeepSeek 余额。

    返回统一结构（永不抛异常）：
      {"ok": True,  "total": 2.19, "currency": "CNY", "available": True, "infos": [...]}
      {"ok": False, "error": "…"}
    """
    key = key or api_key()
    if not key:
        return {"ok": False, "error": "未配置 DEEPSEEK_API_KEY"}

    req = urllib.request.Request(
        BALANCE_URL,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": "HTTP %s" % exc.code}
    except Exception as exc:  # 网络抖动、DNS、超时
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}

    infos = data.get("balance_infos") or []
    if not infos:
        return {"ok": False, "error": "接口未返回 balance_infos"}

    first = infos[0] or {}
    try:
        total = float(first.get("total_balance"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "total_balance 不是数字"}

    return {
        "ok": True,
        "total": total,
        "currency": first.get("currency") or "CNY",
        "available": bool(data.get("is_available", True)),
        "infos": infos,
    }


# --------------------------------------------------------------------------
# 本地账本 / 设置
# --------------------------------------------------------------------------
def read_size() -> dict:
    """挂件设置（DSH 插件写的）。缺省值与 DSH 插件保持一致。"""
    defaults = {
        "scale": 1.4,
        "sound": True,
        "vol": 0.7,
        "soundSet": "duck",
        "usageMode": "ledger",
        "bubbleOn": True,
        "turnCostOn": True,
        "turnCostCloseMs": 3000,
    }
    data = read_json(dsh_path(".dshw-size.json"), {}) or {}
    if not isinstance(data, dict):
        data = {}
    merged = dict(defaults)
    merged.update({k: v for k, v in data.items() if v is not None})
    return merged


def read_usage() -> dict:
    """小鲸鱼记账账本。字段：date / lastBalance / todayUsage / lastCurrency / events[…]"""
    data = read_json(dsh_path(".dshw-usage.json"), {}) or {}
    return data if isinstance(data, dict) else {}


def read_turn() -> dict:
    """每轮消耗 seq（DSH 插件写）。字段通常是 {"seq": n, …}。"""
    data = read_json(dsh_path(".dshw-turn.json"), {}) or {}
    return data if isinstance(data, dict) else {}


def today_usage(usage: dict | None = None) -> float | None:
    """今日已用金额；账本里没有就当 None（显示 --）。"""
    usage = usage if usage is not None else read_usage()
    value = usage.get("todayUsage")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def last_event(usage: dict | None = None) -> dict | None:
    """账本里最后一条逐轮消耗事件（含 model / cost / tokens）。"""
    usage = usage if usage is not None else read_usage()
    events = usage.get("events")
    if isinstance(events, list) and events:
        tail = events[-1]
        return tail if isinstance(tail, dict) else None
    return None


def turn_seq(turn: dict | None = None) -> int:
    turn = turn if turn is not None else read_turn()
    try:
        return int(turn.get("seq") or 0)
    except (TypeError, ValueError):
        return 0


# --------------------------------------------------------------------------
# 本挂件自己的状态
# --------------------------------------------------------------------------
def read_state() -> dict:
    data = read_json(dsh_path(STATE_FILE), {}) or {}
    return data if isinstance(data, dict) else {}


def write_state(patch: dict) -> bool:
    state = read_state()
    state.update(patch)
    return write_json(dsh_path(STATE_FILE), state)


def money(amount: float | None, currency: str = "CNY", dash: str = "--") -> str:
    """金额格式化：¥2.19 / $0.30。"""
    if amount is None:
        return dash
    symbol = {"CNY": "¥", "USD": "$", "EUR": "€"}.get((currency or "CNY").upper(), "")
    return "%s%.2f" % (symbol, amount)
