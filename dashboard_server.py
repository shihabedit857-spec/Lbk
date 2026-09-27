# -*- coding: utf-8 -*-
"""
FreeFire Level Up Bot - Professional Web Dashboard & Real-Time EXP Tracker
Embedded Async Web Server (aiohttp)
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Any, Optional
from aiohttp import web


# Global bot state shared between Main.py and Web Dashboard
class BotState:
    def __init__(self):
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 200
        self.total_matches = 0
        self.total_gained_exp = 0
        self.start_time = time.time()
        self.account_workers: Dict[str, asyncio.Task] = {}
        self.refresh_callbacks: Dict[str, Any] = {}
        self.account_credentials: Dict[str, Dict[str, Any]] = {}

    def log(self, message: str, level: str = "info", uid: Optional[str] = None):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "uid": uid
        }
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def register_account(self, uid: str, nickname: str, region: str, level: int, exp: int, likes: int = 0):
        uid_str = str(uid)
        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str,
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "BD",
                "level": level or 1,
                "initial_exp": exp,
                "current_exp": exp,
                "gained_exp": 0,
                "likes": likes or 0,
                "status": "ONLINE",
                "matches_played": 0,
                "active_matches": 0,
                "last_match_time": None,
                "last_updated": time.strftime("%H:%M:%S")
            }
        else:
            acc = self.accounts[uid_str]
            if nickname:
                acc["nickname"] = nickname
            if region:
                acc["region"] = region
            if level:
                acc["level"] = level
            acc["current_exp"] = exp
            acc["gained_exp"] = max(0, exp - acc["initial_exp"])
            acc["likes"] = likes
            acc["status"] = "ONLINE"
            acc["last_updated"] = time.strftime("%H:%M:%S")
        self.recalc_totals()

    def update_exp(self, uid: str, current_exp: int, level: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            old_exp = acc["current_exp"]
            acc["current_exp"] = current_exp
            if level is not None and level > 0:
                acc["level"] = level
            acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])
            acc["last_updated"] = time.strftime("%H:%M:%S")
            diff = current_exp - old_exp
            if diff > 0:
                self.log(
                    f"Account {acc['nickname']} ({uid_str}) gained +{diff} EXP! Total Gained: +{acc['gained_exp']}",
                    "success", uid_str)
            self.recalc_totals()

    def update_status(self, uid: str, status: str, active_matches: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if active_matches is not None:
                self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")

    def increment_match(self, uid: str):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            self.accounts[uid_str]["matches_played"] += 1
            self.accounts[uid_str]["last_match_time"] = time.strftime("%H:%M:%S")
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")
            self.log(
                f"Account {self.accounts[uid_str]['nickname']} finished Match #{self.accounts[uid_str]['matches_played']}",
                "info", uid_str)

    def recalc_totals(self):
        self.total_gained_exp = sum(acc.get("gained_exp", 0) for acc in self.accounts.values())


bot_state = BotState()


# ==================== HTTP HANDLERS ====================

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")


async def handle_index(request: web.Request) -> web.Response:
    if os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = "<h1>templates/index.html not found!</h1>"
    return web.Response(text=content, content_type="text/html", charset="utf-8")


async def handle_get_stats(request: web.Request) -> web.Response:
    accounts_data = list(bot_state.accounts.values())
    accounts_data.sort(key=lambda x: x.get("gained_exp", 0), reverse=True)
    return web.json_response({
        "total_accounts": len(bot_state.accounts),
        "total_matches": bot_state.total_matches,
        "total_gained_exp": bot_state.total_gained_exp,
        "accounts": accounts_data,
        "logs": bot_state.logs[-60:],
        "uptime": int(time.time() - bot_state.start_time)
    })


async def handle_add_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        accounts_file = "accounts.json"
        existing = []
        if os.path.exists(accounts_file):
            try:
                with open(accounts_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        if "uid" in data and "password" in data:
            uid = str(data["uid"]).strip()
            pwd = str(data["password"]).strip()
            if not uid or not pwd:
                return web.json_response({"status": "error", "error": "UID and Password are required"})
            existing = [acc for acc in existing if str(acc.get("uid")) != uid]
            existing.append({"uid": uid, "password": pwd})
        elif "token" in data:
            token = str(data["token"]).strip()
            if not token:
                return web.json_response({"status": "error", "error": "Token is required"})
            existing = [acc for acc in existing if acc.get("token") != token]
            existing.append({"token": token})
        else:
            return web.json_response({"status": "error", "error": "Invalid payload"})

        with open(accounts_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

        bot_state.log(f"New account added: {data.get('uid') or 'Token'}", "success")

        if "on_account_added" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"](data))

        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_delete_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()  # গেমের account_id (যেমন 18345779450)

        # 🔥 বের করুন কোন ধরনের অ্যাকাউন্ট (guest নাকি token)
        guest_uid = None
        token_key = None

        cred = bot_state.account_credentials.get(uid)
        if cred:
            if cred.get('auth_type') == 'guest' and cred.get('auth_uid'):
                guest_uid = str(cred['auth_uid'])
            elif cred.get('auth_type') == 'token' and cred.get('auth_token'):
                token_key = f"tok_{cred['auth_token'][:20]}"
        else:
            # যদি uid নিজেই গেস্ট UID হয়
            guest_uid = uid

        # ============ ১. accounts.json থেকে ডিলিট ============
        accounts_file = "accounts.json"
        if os.path.exists(accounts_file):
            try:
                with open(accounts_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)

                new_list = []
                for acc in existing:
                    acc_uid = str(acc.get("uid", "")).strip()
                    acc_token = acc.get("token", "")

                    # Guest UID ম্যাচ
                    if acc_uid and (acc_uid == uid or acc_uid == guest_uid):
                        print(f"[DELETE] accounts.json → removing guest: {acc_uid}")
                        continue

                    # Token ম্যাচ
                    if acc_token and token_key and acc_token[:20] == cred.get('auth_token', '')[:20]:
                        print(f"[DELETE] accounts.json → removing token account")
                        continue

                    new_list.append(acc)

                with open(accounts_file, "w", encoding="utf-8") as f:
                    json.dump(new_list, f, indent=2)
            except Exception as e:
                print(f"[DELETE] accounts.json error: {e}")

        # ============ ২. token_cache.json থেকে ডিলিট ============
        cache_file = "token_cache.json"
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)

                keys_to_delete = []
                for key in list(cache_data.keys()):
                    # Guest UID কী
                    if key == uid or (guest_uid and key == guest_uid):
                        keys_to_delete.append(key)
                        continue

                    # Token কী (tok_xxxx)
                    entry = cache_data[key]
                    if isinstance(entry, dict):
                        # entry এর account_id ম্যাচ
                        if str(entry.get('account_id')) == uid:
                            keys_to_delete.append(key)
                            continue
                        # entry এর auth_uid ম্যাচ
                        if guest_uid and str(entry.get('auth_uid')) == guest_uid:
                            keys_to_delete.append(key)
                            continue
                        # token কী ম্যাচ
                        if token_key and key == token_key:
                            keys_to_delete.append(key)
                            continue

                for k in keys_to_delete:
                    print(f"[DELETE] token_cache.json → removing key: {k}")
                    del cache_data[k]

                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache_data, f, indent=2)

                # 🔥 মেমো ক্যাশ ইনভ্যালিডেট
                try:
                    import main as _m
                    _m._token_cache_memo = {}
                    _m._token_cache_memo_time = 0.0
                except Exception:
                    pass
            except Exception as e:
                print(f"[DELETE] token_cache.json error: {e}")

        # ============ ৩. bot_state থেকে ডিলিট ============
        if uid in bot_state.accounts:
            del bot_state.accounts[uid]
        if guest_uid and guest_uid != uid and guest_uid in bot_state.accounts:
            del bot_state.accounts[guest_uid]

        # ============ ৪. Workers ক্যান্সেল ============
        if uid in bot_state.account_workers:
            bot_state.account_workers[uid].cancel()
            del bot_state.account_workers[uid]
        if guest_uid and guest_uid != uid and guest_uid in bot_state.account_workers:
            bot_state.account_workers[guest_uid].cancel()
            del bot_state.account_workers[guest_uid]
        if token_key and token_key in bot_state.account_workers:
            bot_state.account_workers[token_key].cancel()
            del bot_state.account_workers[token_key]

        # ============ ৫. credentials ডিলিট ============
        if uid in bot_state.account_credentials:
            del bot_state.account_credentials[uid]
        if guest_uid and guest_uid != uid and guest_uid in bot_state.account_credentials:
            del bot_state.account_credentials[guest_uid]
        if token_key and token_key in bot_state.account_credentials:
            del bot_state.account_credentials[token_key]

        bot_state.log(f"Account {uid} removed (guest: {guest_uid}, token: {token_key})", "warning", uid)
        return web.json_response({
            "status": "ok",
            "removed": {
                "account_id": uid,
                "guest_uid": guest_uid,
                "token_key": token_key
            }
        })
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_refresh_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if "on_refresh_account" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_refresh_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def start_web_dashboard(host: str = "0.0.0.0", port: int = None):
    if port is None:
        port = int(os.environ.get("PORT", 5000))

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_get_stats)
    app.router.add_post("/api/account/add", handle_add_account)
    app.router.add_post("/api/account/delete", handle_delete_account)
    app.router.add_post("/api/account/refresh", handle_refresh_account)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    # ⚡ Railway / Local — সঠিক URL প্রিন্ট
    railway_domain = (
        os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or os.environ.get("RAILWAY_STATIC_URL")
        or os.environ.get("RAILWAY_URL")
    )
    if railway_domain:
        if not railway_domain.startswith("http"):
            railway_domain = f"https://{railway_domain}"
        print(f"\033[92m[+] Web Dashboard live at {railway_domain}\033[0m")
    else:
        print(f"\033[92m[+] Web Dashboard running on {host}:{port}\033[0m")