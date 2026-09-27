# -*- coding: utf-8 -*-
"""
FreeFire Level Up Bot - Web Dashboard Server
HTML embedded — LAN IP / Railway URL auto-detect + ACCURATE EXP progress
"""

import asyncio
import json
import os
import socket as _sock
import time
from typing import Dict, List, Any, Optional
from aiohttp import web


# ==================== BOT STATE ====================
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
        self.account_states: Dict[str, str] = {}

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

    def register_account(self, uid: str, nickname: str, region: str, level: int, exp: int,
                         likes: int = 0, target_level: int = 0, game_uid: Optional[str] = None):
        uid_str = str(uid)
        game_uid_str = str(game_uid) if game_uid else None

        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str,
                "game_uid": game_uid_str or uid_str,
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "BD",
                "level": level or 1,
                "initial_exp": exp,
                "current_exp": exp,
                "gained_exp": 0,
                "likes": likes or 0,
                "status": "OFFLINE",
                "target_level": int(target_level or 0),
                "matches_played": 0,
                "active_matches": 0,
                "last_match_time": None,
                "last_updated": time.strftime("%H:%M:%S"),
                "completed_at": None
            }
        else:
            acc = self.accounts[uid_str]
            if game_uid_str:
                acc["game_uid"] = game_uid_str
            if nickname:
                acc["nickname"] = nickname
            if region and region != "—":
                acc["region"] = region
            if level and level > 0:
                acc["level"] = level
            if target_level and int(target_level) > 0:
                acc["target_level"] = int(target_level)
            if exp > 0 or acc.get("initial_exp", 0) == 0:
                acc["current_exp"] = exp
                if acc.get("initial_exp", 0) == 0:
                    acc["initial_exp"] = exp
            acc["gained_exp"] = max(0, acc["current_exp"] - acc["initial_exp"])
            acc["likes"] = likes or acc.get("likes", 0)
            acc["last_updated"] = time.strftime("%H:%M:%S")
            if acc.get("status") not in ("IN_MATCH", "ONLINE", "SEARCHING", "COMPLETE", "STOPPED", "CONNECTING"):
                acc["status"] = "OFFLINE"
        self.recalc_totals()

    def set_target_level(self, uid: str, target_level: int):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["target_level"] = int(target_level or 0)

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
                self.log(f"{acc['nickname']} gained +{diff} EXP! Total: +{acc['gained_exp']}",
                         "success", uid_str)
            self.recalc_totals()

    def update_status(self, uid: str, status: str, active_matches: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if active_matches is not None:
                self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")
            if status == "COMPLETE":
                self.accounts[uid_str]["completed_at"] = time.strftime("%H:%M:%S")

    def increment_match(self, uid: str):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            self.accounts[uid_str]["matches_played"] += 1
            self.accounts[uid_str]["last_match_time"] = time.strftime("%H:%M:%S")
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")
        else:
            for k, acc in self.accounts.items():
                if str(acc.get("game_uid")) == uid_str:
                    acc["matches_played"] += 1
                    acc["last_match_time"] = time.strftime("%H:%M:%S")
                    acc["last_updated"] = time.strftime("%H:%M:%S")
                    break

    def is_target_reached(self, uid: str) -> bool:
        uid_str = str(uid)
        if uid_str not in self.accounts:
            for k, acc in self.accounts.items():
                if str(acc.get("game_uid")) == uid_str:
                    target = int(acc.get("target_level") or 0)
                    if target <= 0:
                        return False
                    return int(acc.get("level") or 1) >= target
            return False
        acc = self.accounts[uid_str]
        target = int(acc.get("target_level") or 0)
        if target <= 0:
            return False
        return int(acc.get("level") or 1) >= target

    def recalc_totals(self):
        self.total_gained_exp = sum(acc.get("gained_exp", 0) for acc in self.accounts.values())


bot_state = BotState()


# ==================== EMBEDDED HTML DASHBOARD ====================
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#0d0d0d">
<title>TEAM 84FF | FreeFire Level Up Bot</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
:root{
  --bg-main:#0d0d0d;--bg-card:#161616;--bg-input:#1a1a1a;--bg-modal:#141414;
  --border-light:rgba(255,255,255,.07);
  --grad-primary:linear-gradient(135deg,#ff416c 0%,#ff4b2b 100%);
  --accent:#ff5722;--accent-green:#22c55e;--accent-red:#ef4444;--accent-amber:#f59e0b;--accent-blue:#3b82f6;
  --text-primary:#fff;--text-secondary:#9ca3af;--text-muted:#6b7280;
  --shadow-glow:0 4px 20px rgba(255,75,43,.3);
  --safe-top:env(safe-area-inset-top,0px);--safe-bottom:env(safe-area-inset-bottom,0px);
}
*{box-sizing:border-box;margin:0;padding:0;font-family:'Outfit',sans-serif;-webkit-tap-highlight-color:transparent}
html,body{width:100%;overflow-x:hidden}
body{background-color:var(--bg-main);color:var(--text-primary);min-height:100vh;min-height:100dvh;
 padding:12px;padding-top:calc(12px + var(--safe-top));padding-bottom:calc(12px + var(--safe-bottom));
 font-size:14px;-webkit-font-smoothing:antialiased}
.container{max-width:1440px;margin:0 auto;width:100%}

header{display:flex;flex-direction:column;gap:14px;padding:16px;background:var(--bg-card);
 border:1px solid var(--border-light);border-radius:18px;margin-bottom:12px}
.brand{display:flex;align-items:center;gap:12px}
.logo-box{width:46px;height:46px;min-width:46px;background:var(--grad-primary);border-radius:14px;
 display:flex;align-items:center;justify-content:center;font-size:20px;color:#fff;box-shadow:var(--shadow-glow)}
.brand-text h1{font-size:16px;font-weight:800;line-height:1.2}
.brand-text h1 span{font-weight:400;color:var(--text-secondary);font-size:.75em}
.brand-text p{font-size:11px;color:var(--text-secondary);display:flex;align-items:center;gap:6px;margin-top:4px;flex-wrap:wrap}
.live-tag{display:inline-flex;align-items:center;gap:5px;background:rgba(34,197,94,.1);
 border:1px solid rgba(34,197,94,.2);color:var(--accent-green);padding:3px 9px;border-radius:20px;
 font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px}
.pulse-dot{width:6px;height:6px;background:var(--accent-green);border-radius:50%;animation:blink 1.3s infinite;flex-shrink:0}
@keyframes blink{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.75)}}
.header-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}

.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:12px 16px;
 font-size:13px;font-weight:700;border-radius:12px;border:none;cursor:pointer;user-select:none;
 transition:transform .18s cubic-bezier(.34,1.56,.64,1),opacity .18s,background .18s;
 will-change:transform;white-space:nowrap;font-family:inherit;letter-spacing:.3px}
.btn:active:not(:disabled){transform:scale(.96)}
.btn:disabled{opacity:.4;cursor:not-allowed}
.btn-primary{background:var(--grad-primary);color:#fff;box-shadow:var(--shadow-glow)}
.btn-ghost{background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border-light)}

.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
.stat-card{background:var(--bg-card);border:1px solid var(--border-light);border-radius:16px;
 padding:14px;display:flex;align-items:center;gap:12px}
.stat-icon{width:42px;height:42px;min-width:42px;border-radius:12px;display:flex;align-items:center;
 justify-content:center;font-size:17px;background:rgba(255,75,43,.1);color:var(--accent);
 border:1px solid rgba(255,75,43,.15)}
.stat-content{min-width:0;flex:1}
.stat-content h3{font-size:18px;font-weight:800;letter-spacing:-.4px;line-height:1.2;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stat-content p{font-size:10px;color:var(--text-secondary);font-weight:600;margin-top:3px;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:.5px;text-transform:uppercase}

.card-box{background:var(--bg-card);border:1px solid var(--border-light);border-radius:18px;padding:16px}
.box-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;gap:8px}
.box-title{font-size:14px;font-weight:700;display:flex;align-items:center;gap:10px;color:#fff;
 text-transform:uppercase;letter-spacing:.5px;min-width:0}
.box-title i{color:var(--accent);font-size:15px}
.accounts-list{display:flex;flex-direction:column;gap:14px}

.account-card{background:var(--bg-input);border:1px solid var(--border-light);border-radius:16px;padding:16px;transition:.3s}
.account-card.status-COMPLETE{border-color:rgba(34,197,94,.5);background:rgba(34,197,94,.04)}
.account-card.status-STOPPED{opacity:.75}

.acc-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:14px}
.acc-profile{display:flex;align-items:center;gap:12px;min-width:0;flex:1}
.acc-avatar{width:42px;height:42px;min-width:42px;border-radius:12px;
 background:linear-gradient(135deg,#2a2a2a,#1a1a1a);display:flex;align-items:center;justify-content:center;
 font-weight:700;font-size:15px;color:var(--accent);border:1px solid rgba(255,75,43,.25)}
.acc-info{min-width:0;flex:1}
.acc-info h4{font-size:15px;font-weight:700;color:#fff;display:flex;align-items:center;gap:8px;flex-wrap:wrap;line-height:1.2}
.region-badge{background:rgba(255,255,255,.06);color:var(--text-secondary);padding:2px 8px;
 border-radius:6px;font-size:9px;font-weight:800;letter-spacing:.5px;border:1px solid rgba(255,255,255,.1)}
.acc-info span{font-size:11px;color:var(--text-muted);font-family:'JetBrains Mono',monospace;
 display:block;margin-top:4px;word-break:break-all}
.acc-status{display:inline-flex;align-items:center;gap:6px;font-size:10px;font-weight:700;
 padding:5px 12px;border-radius:20px;white-space:nowrap;flex-shrink:0;letter-spacing:.5px;text-transform:uppercase}
.status-online{background:rgba(34,197,94,.08);color:var(--accent-green);border:1px solid rgba(34,197,94,.2)}
.status-match{background:rgba(255,75,43,.12);color:var(--accent);border:1px solid rgba(255,75,43,.4);animation:pulse-border 1.5s infinite alternate}
.status-stopped{background:rgba(148,163,184,.1);color:#94a3b8;border:1px solid rgba(148,163,184,.25)}
.status-complete{background:rgba(34,197,94,.15);color:var(--accent-green);border:1px solid rgba(34,197,94,.5)}
.status-offline{background:rgba(107,114,128,.1);color:var(--text-muted);border:1px solid rgba(107,114,128,.2)}
.status-searching{background:rgba(59,130,246,.12);color:var(--accent-blue);border:1px solid rgba(59,130,246,.4);animation:pulse-border 1.5s infinite alternate}
.status-connecting{background:rgba(245,158,11,.12);color:var(--accent-amber);border:1px solid rgba(245,158,11,.4);animation:pulse-border 1.5s infinite alternate}
@keyframes pulse-border{0%{border-color:rgba(255,75,43,.3)}100%{border-color:rgba(255,75,43,.8)}}

.exp-box{display:grid;grid-template-columns:1fr 1fr;gap:12px;background:rgba(0,0,0,.25);
 padding:12px 14px;border-radius:12px;margin-bottom:14px;border:1px solid rgba(255,255,255,.04)}
.exp-item{display:flex;flex-direction:column;gap:4px;min-width:0}
.exp-item.full-width{grid-column:span 2}
.exp-label{font-size:9px;color:var(--text-muted);text-transform:uppercase;font-weight:700;letter-spacing:.8px}
.exp-val{font-size:14px;font-weight:700;font-family:'JetBrains Mono',monospace;color:#fff;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-.3px}
.gained-badge{background:rgba(255,75,43,.15);color:var(--accent);padding:4px 12px;
 border-radius:8px;font-size:13px;font-weight:800;display:inline-block;font-family:'JetBrains Mono',monospace;
 border:1px solid rgba(255,75,43,.3);letter-spacing:-.3px}

.level-progress{margin-bottom:12px}
.level-labels{display:flex;justify-content:space-between;font-size:11px;margin-bottom:8px;font-weight:700;gap:8px;flex-wrap:wrap}
.level-labels .lvl{color:var(--accent)}
.level-labels .matches{color:var(--text-secondary)}
.level-labels .exp-info{color:var(--text-muted);font-size:10px;font-family:'JetBrains Mono',monospace}
.progress-bar-bg{height:8px;background:rgba(255,255,255,.06);border-radius:10px;overflow:hidden;position:relative}
.progress-bar-fill{height:100%;background:var(--grad-primary);border-radius:10px;
 transition:width .8s cubic-bezier(.34,1.2,.64,1);box-shadow:0 0 10px rgba(255,75,43,.5);
 position:relative;overflow:hidden}
.progress-bar-fill::after{content:'';position:absolute;top:0;left:0;right:0;bottom:0;
 background:linear-gradient(90deg,transparent,rgba(255,255,255,.3),transparent);
 animation:shimmer 2s infinite}
@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.progress-bar-fill.done{background:linear-gradient(90deg,#22c55e,#16a34a);box-shadow:0 0 10px rgba(34,197,94,.6)}

.complete-banner{background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.35);
 border-radius:12px;padding:12px;margin-bottom:12px;display:flex;align-items:center;gap:10px;color:var(--accent-green)}
.complete-banner i{font-size:20px}
.complete-banner .txt{font-size:13px;font-weight:700;line-height:1.4}

.acc-actions{display:flex;align-items:center;justify-content:space-between;padding-top:12px;
 border-top:1px solid rgba(255,255,255,.05);gap:8px;flex-wrap:wrap}
.acc-actions .last-info{font-size:11px;color:var(--text-muted);flex:1;min-width:0;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.action-btns{display:flex;gap:6px;flex-wrap:wrap}
.action-btn{padding:8px 12px;border-radius:10px;border:1px solid;font-size:11px;font-weight:700;
 cursor:pointer;display:inline-flex;align-items:center;gap:5px;transition:.2s;user-select:none;
 background:transparent;font-family:inherit;letter-spacing:.3px}
.action-btn:active{transform:scale(.94)}
.action-btn.start{color:var(--accent-green);border-color:rgba(34,197,94,.35);background:rgba(34,197,94,.06)}
.action-btn.stop{color:var(--accent-red);border-color:rgba(239,68,68,.35);background:rgba(239,68,68,.06)}
.action-btn.restart{color:var(--accent-amber);border-color:rgba(245,158,11,.35);background:rgba(245,158,11,.06)}
.action-btn.delete{color:#94a3b8;border-color:rgba(148,163,184,.25);background:rgba(148,163,184,.04)}
.action-btn.refresh{color:var(--accent-blue);border-color:rgba(59,130,246,.35);background:rgba(59,130,246,.06)}
.action-btn:disabled{opacity:.35;cursor:not-allowed}

.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.85);backdrop-filter:blur(8px);
 -webkit-backdrop-filter:blur(8px);display:none;align-items:flex-end;justify-content:center;
 z-index:100;padding-bottom:var(--safe-bottom)}
.modal-overlay.active{display:flex}
.modal-card{background:var(--bg-modal);border:1px solid rgba(255,255,255,.08);border-bottom:none;
 border-radius:24px 24px 0 0;width:100%;max-width:480px;padding:24px;
 padding-bottom:calc(24px + var(--safe-bottom));max-height:92vh;overflow-y:auto;
 animation:slideUp .32s cubic-bezier(.34,1.3,.64,1);position:relative}
.modal-card::before{content:'';position:absolute;top:8px;left:50%;transform:translateX(-50%);
 width:40px;height:4px;background:rgba(255,255,255,.15);border-radius:4px}
@keyframes slideUp{from{transform:translateY(100%);opacity:.5}to{transform:translateY(0);opacity:1}}
.modal-header{display:flex;align-items:center;justify-content:space-between;margin-top:12px;margin-bottom:20px;gap:8px}
.modal-header h3{font-size:16px;font-weight:800;display:flex;align-items:center;gap:8px;text-transform:uppercase;letter-spacing:.5px}
.modal-header h3 i{color:var(--accent)}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:11px;font-weight:700;color:var(--text-secondary);
 margin-bottom:8px;text-transform:uppercase;letter-spacing:.8px}
.form-input{width:100%;background:var(--bg-input);border:1px solid var(--border-light);border-radius:12px;
 padding:14px;color:#fff;font-size:14px;outline:none;transition:.2s;font-family:inherit;
 -webkit-appearance:none;appearance:none}
.form-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(255,75,43,.1)}
.form-input::placeholder{color:var(--text-muted)}
select.form-input{background-image:url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3e%3cpolyline points='6 9 12 15 18 9'/%3e%3c/svg%3e");
 background-repeat:no-repeat;background-position:right 14px center;background-size:16px;padding-right:40px}
.hint{font-size:11px;color:var(--text-muted);margin-top:6px;line-height:1.4}
.empty-state{text-align:center;padding:40px 16px;color:var(--text-secondary)}
.empty-state i{font-size:40px;margin-bottom:12px;color:rgba(255,255,255,.1)}

@media(min-width:640px){
  body{padding:16px}
  .stats-grid{grid-template-columns:repeat(4,1fr)}
  header{flex-direction:row;align-items:center;padding:20px 24px}
  .header-actions{grid-template-columns:auto auto}
  .modal-overlay{align-items:center}
  .modal-card{border-radius:24px;padding:28px;margin:16px}
  .modal-card::before{display:none}
}
@media(min-width:1024px){
  body{padding:24px}
  .accounts-list{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
  .stat-content h3{font-size:26px}
}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <div class="logo-box"><i class="fa-solid fa-bolt"></i></div>
      <div class="brand-text">
        <h1>TEAM 84FF <span>| LEVEL UP BOT</span></h1>
        <p><span class="live-tag"><span class="pulse-dot"></span> Online</span>
        <span>Safe Multi-Match Engine</span></p>
      </div>
    </div>
    <div class="header-actions">
      <button class="btn btn-ghost" onclick="fetchStats(true)"><i class="fa-solid fa-rotate"></i> Refresh</button>
      <button class="btn btn-primary" onclick="openAddModal()"><i class="fa-solid fa-plus"></i> Add</button>
    </div>
  </header>

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-icon"><i class="fa-solid fa-users"></i></div>
      <div class="stat-content"><h3 id="stat-total-accounts">0</h3><p>Accounts</p></div></div>
    <div class="stat-card"><div class="stat-icon"><i class="fa-solid fa-angles-up"></i></div>
      <div class="stat-content"><h3 id="stat-total-exp">+0</h3><p>EXP Gained</p></div></div>
    <div class="stat-card"><div class="stat-icon"><i class="fa-solid fa-gamepad"></i></div>
      <div class="stat-content"><h3 id="stat-total-matches">0</h3><p>Matches</p></div></div>
    <div class="stat-card"><div class="stat-icon"><i class="fa-solid fa-shield-halved"></i></div>
      <div class="stat-content"><h3 id="stat-uptime">00:00:00</h3><p>Uptime</p></div></div>
  </div>

  <div class="card-box">
    <div class="box-header">
      <div class="box-title"><i class="fa-solid fa-user-astronaut"></i><span>Accounts Control Center</span></div>
    </div>
    <div class="accounts-list" id="accounts-container">
      <div class="empty-state"><i class="fa-solid fa-circle-notch fa-spin"></i><p>Loading...</p></div>
    </div>
  </div>
</div>

<div class="modal-overlay" id="add-modal" onclick="if(event.target===this)closeAddModal()">
  <div class="modal-card">
    <div class="modal-header">
      <h3><i class="fa-solid fa-user-plus"></i> Add Account</h3>
      <button class="action-btn delete" onclick="closeAddModal()"><i class="fa-solid fa-xmark"></i></button>
    </div>
    <form id="add-acc-form" onsubmit="submitAddAccount(event)">
      <div class="form-group">
        <label>Account Type</label>
        <select class="form-input" id="acc-type" onchange="toggleFormType()">
          <option value="guest">Guest Account (UID + Password)</option>
          <option value="token">Access Token</option>
        </select>
      </div>
      <div id="guest-fields">
        <div class="form-group">
          <label>Guest UID</label>
          <input type="text" class="form-input" id="acc-uid" placeholder="Enter player UID" inputmode="numeric" autocomplete="off">
        </div>
        <div class="form-group">
          <label>Guest Password / Secret</label>
          <input type="text" class="form-input" id="acc-password" placeholder="Enter password" autocomplete="off">
        </div>
      </div>
      <div id="token-fields" style="display:none;">
        <div class="form-group">
          <label>Access Token</label>
          <textarea class="form-input" id="acc-token" rows="3" placeholder="Paste access token" autocomplete="off"></textarea>
        </div>
      </div>
      <div class="form-group">
        <label>🎯 Target Level</label>
        <input type="number" class="form-input" id="acc-target" placeholder="e.g. 20" min="0" max="100" value="0">
        <div class="hint">এই লেভেলে পৌঁছালে অ্যাকাউন্ট AUTO DELETE হবে। 0 দিলে লিমিট নেই।</div>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:24px;">
        <button type="button" class="btn btn-ghost" onclick="closeAddModal()">Cancel</button>
        <button type="submit" class="btn btn-primary"><i class="fa-solid fa-floppy-disk"></i> Save (Not Started)</button>
      </div>
    </form>
  </div>
</div>

<script>
let serverUptimeBase = 0, localStartTime = Date.now();
let pollTimer = null, isFetching = false, lastDataHash = '';

// 🔥 EXACT Free Fire Level EXP Thresholds (OB55)
const LEVELS = {
  1: 0, 2: 48, 3: 202, 4: 544, 5: 1012, 6: 1844, 7: 2792, 8: 3800, 9: 4870,
  10: 6004, 11: 7192, 12: 8448, 13: 9776, 14: 11140, 15: 12566, 16: 14060,
  17: 15610, 18: 17224, 19: 18902, 20: 20632, 21: 22424, 22: 24728, 23: 26192,
  24: 28166, 25: 30200, 26: 32294, 27: 34448, 28: 37804, 29: 41174, 30: 44870,
  31: 48852, 32: 53334, 33: 58566, 34: 64096, 35: 69994, 36: 76460, 37: 83108,
  38: 91128, 39: 99322, 40: 108092, 41: 120144, 42: 133266, 43: 147472, 44: 162760,
  45: 179126, 46: 196572, 47: 215368, 48: 235516, 49: 257010, 50: 279860, 51: 304056,
  52: 348318, 53: 394982, 54: 444044, 55: 495508, 56: 549364, 57: 633756, 58: 721744,
  59: 813336, 60: 908522, 61: 1041438, 62: 1180352, 63: 1325256, 64: 1476184,
  65: 1634300, 66: 1840946, 67: 2056594, 68: 2281242, 69: 2514880, 70: 2757530,
  71: 3059506, 72: 3372284, 73: 3699456, 74: 4041030, 75: 4397020, 76: 4829104,
  77: 5282204, 78: 5756304, 79: 6251404, 80: 6767504, 81: 7381324, 82: 8043154,
  83: 8752952, 84: 9510808, 85: 10316638, 86: 11277190, 87: 12360748, 88: 13360304,
  89: 14482858, 90: 15659418, 91: 17026708, 92: 18453688, 93: 19941280, 94: 21488570,
  95: 23095858, 96: 24763138, 97: 26490138, 98: 28277708, 99: 30124996, 100: 32032284
};

/**
 * Calculate progress percentage using EXACT level thresholds.
 * Returns { pct, currentLevelExp, nextLevelExp, neededExp }
 */
function calcProgress(a, isComplete) {
  if (isComplete) {
    return { pct: 100, curExpBase: 0, nextExpBase: 0, needed: 0 };
  }

  const lvl = a.level || 1;
  const target = a.target_level || 0;
  const currentExp = a.current_exp || 0;

  // EXP baseline for current level and next level
  const curExpBase = LEVELS[lvl] || 0;
  const nextExpBase = LEVELS[lvl + 1] || (curExpBase + 1000);
  const expForThisLevel = Math.max(1, nextExpBase - curExpBase);

  // How much EXP progressed within current level
  const expInLevel = Math.max(0, currentExp - curExpBase);
  const fracInLevel = Math.min(1, expInLevel / expForThisLevel);

  let pct = 0;

  if (target <= 0) {
    // No target: show progress within current level
    pct = fracInLevel * 100;
  } else if (target <= lvl) {
    pct = 100;
  } else {
    // Progress = (levels completed / (target - 1)) + fractional current level
    const levelsCompleted = lvl - 1;
    const totalLevels = target - 1;
    pct = ((levelsCompleted + fracInLevel) / totalLevels) * 100;
  }

  return {
    pct: Math.min(99.5, Math.max(0.5, pct)),
    curExpBase: curExpBase,
    nextExpBase: nextExpBase,
    needed: Math.max(0, nextExpBase - currentExp)
  };
}

function openAddModal(){document.getElementById('add-modal').classList.add('active');document.body.style.overflow='hidden'}
function closeAddModal(){document.getElementById('add-modal').classList.remove('active');document.body.style.overflow=''}
function toggleFormType(){
  const t=document.getElementById('acc-type').value;
  document.getElementById('guest-fields').style.display=t==='guest'?'block':'none';
  document.getElementById('token-fields').style.display=t==='token'?'block':'none';
}

async function submitAddAccount(e){
  e.preventDefault();
  const type=document.getElementById('acc-type').value;
  const target=parseInt(document.getElementById('acc-target').value||'0');
  let payload={target_level:target};
  if(type==='guest'){
    const uid=document.getElementById('acc-uid').value.trim();
    const password=document.getElementById('acc-password').value.trim();
    if(!uid||!password)return alert('Please enter both UID and Password');
    payload.uid=uid; payload.password=password;
  } else {
    const token=document.getElementById('acc-token').value.trim();
    if(!token)return alert('Please enter token');
    payload.token=token;
  }
  try{
    const res=await fetch('/api/account/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await res.json();
    if(data.status==='ok'){
      closeAddModal();
      document.getElementById('add-acc-form').reset();
      fetchStats(true);
      alert('✅ Account saved!\n\n⚡ আসল info লোড হচ্ছে (৫-১০ সেকেন্ড)...\nতারপর ▶ START চাপুন।');
    }else{alert('Error: '+(data.error||'Unknown'))}
  }catch(err){alert('Request failed: '+err)}
}

async function startAccount(uid){
  if(!confirm('Start account '+uid+'?'))return;
  try{
    const res=await fetch('/api/account/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});
    const data=await res.json();
    if(data.status!=='ok')alert('Start failed: '+(data.error||'unknown'));
    fetchStats(true);
  }catch(e){alert('Start failed: '+e)}
}
async function stopAccount(uid){
  if(!confirm('Stop account '+uid+'?'))return;
  try{
    await fetch('/api/account/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});
    fetchStats(true);
  }catch(e){alert('Stop failed: '+e)}
}
async function restartAccount(uid){
  if(!confirm('Restart account '+uid+'?'))return;
  try{
    await fetch('/api/account/restart',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});
    fetchStats(true);
  }catch(e){alert('Restart failed: '+e)}
}
async function deleteAccount(uid){
  if(!confirm('DELETE account '+uid+'?\n\nThis removes from accounts.json + token_cache.json'))return;
  try{
    await fetch('/api/account/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});
    fetchStats(true);
  }catch(e){alert('Delete failed: '+e)}
}
async function refreshAccountInfo(uid){
  try{
    await fetch('/api/account/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});
    fetchStats(true);
  }catch(e){}
}

function renderAccounts(accounts){
  const c=document.getElementById('accounts-container');
  if(!accounts.length){c.innerHTML='<div class="empty-state"><i class="fa-solid fa-ghost"></i><p>No accounts. Click "+ Add".</p></div>';return}
  c.innerHTML=accounts.map(a=>{
    const gained=a.gained_exp||0;
    const status=(a.status||'OFFLINE').toUpperCase();
    const isComplete=status==='COMPLETE';
    const isMatch=status==='IN_MATCH';
    const isSearching=status==='SEARCHING';
    const isStopped=status==='STOPPED';
    const isOnline=status==='ONLINE';
    const isConnecting=status==='CONNECTING';

    let statusCls='status-offline', statusTxt=status;
    if(isComplete){statusCls='status-complete';statusTxt='✓ COMPLETE'}
    else if(isMatch){statusCls='status-match';statusTxt='IN MATCH ('+(a.active_matches||0)+')'}
    else if(isSearching){statusCls='status-searching';statusTxt='SEARCHING'}
    else if(isConnecting){statusCls='status-connecting';statusTxt='CONNECTING'}
    else if(isStopped){statusCls='status-stopped';statusTxt='STOPPED'}
    else if(isOnline){statusCls='status-online';statusTxt='ONLINE'}

    const target=a.target_level||0;
    const lvl=a.level||1;
    const prog = calcProgress(a, isComplete);
    const pct = prog.pct;

    // EXP info within level
    const expWithinLevel = Math.max(0, (a.current_exp||0) - prog.curExpBase);
    const expNeededLevel = prog.needed;
    const expInfoTxt = isComplete ? 'Target reached' : 
      (expWithinLevel.toLocaleString() + ' / ' + expNeededLevel.toLocaleString() + ' to next Lv');

    const canStart=!isMatch&&!isSearching&&!isComplete&&!isOnline&&!isConnecting;
    const canStop=isMatch||isSearching||isOnline||isConnecting;
    const canRestart=(isMatch||isSearching||isOnline||isStopped||isComplete||isConnecting);

    const displayUid = a.game_uid || a.uid;
    const showGuest = a.game_uid && a.game_uid !== a.uid;
    const guestPart = showGuest ? ' <span style="color:#6b7280;font-size:9px;">(guest: '+esc(a.uid)+')</span>' : '';

    return '<div class="account-card '+(isComplete?'status-COMPLETE':'')+' '+(isStopped?'status-STOPPED':'')+'">' +
      '<div class="acc-top">' +
        '<div class="acc-profile">' +
          '<div class="acc-avatar"><i class="fa-solid fa-user"></i></div>' +
          '<div class="acc-info">' +
            '<h4>'+esc(a.nickname||'Player')+' <span class="region-badge">'+esc(a.region||'BD')+'</span></h4>' +
            '<span>UID: '+esc(displayUid)+guestPart+'</span>' +
          '</div>' +
        '</div>' +
        '<div class="acc-status '+statusCls+'">' +
          ((!isComplete&&!isStopped)?'<span class="pulse-dot"></span>':'') +
          '<span>'+statusTxt+'</span>' +
        '</div>' +
      '</div>' +
      (isComplete?'<div class="complete-banner"><i class="fa-solid fa-circle-check"></i><div class="txt">🎉 Target Level '+target+' reached at '+(a.completed_at||'')+'! Account auto-deleted.</div></div>':'') +
      '<div class="exp-box">' +
        '<div class="exp-item"><span class="exp-label">Initial</span><span class="exp-val">'+Number(a.initial_exp||0).toLocaleString()+'</span></div>' +
        '<div class="exp-item"><span class="exp-label">Current</span><span class="exp-val">'+Number(a.current_exp||0).toLocaleString()+'</span></div>' +
        '<div class="exp-item full-width"><span class="exp-label">EXP Gained</span><span class="gained-badge">+'+Number(gained).toLocaleString()+' EXP</span></div>' +
      '</div>' +
      '<div class="level-progress">' +
        '<div class="level-labels">' +
          '<span class="lvl">Level '+lvl+(target>0?' / '+target:'')+'</span>' +
          '<span class="matches">Matches: '+(a.matches_played||0)+'</span>' +
        '</div>' +
        '<div class="level-labels" style="margin-top:-4px;">' +
          '<span class="exp-info">'+expInfoTxt+'</span>' +
          '<span class="exp-info">'+pct.toFixed(1)+'%</span>' +
        '</div>' +
        '<div class="progress-bar-bg" style="margin-top:6px;"><div class="progress-bar-fill '+(isComplete?'done':'')+'" style="width:'+pct.toFixed(1)+'%"></div></div>' +
      '</div>' +
      '<div class="acc-actions">' +
        '<span class="last-info">Last: '+(a.last_match_time||'—')+'</span>' +
        '<div class="action-btns">' +
          (canStart?'<button class="action-btn start" onclick="startAccount(\''+esc(a.uid)+'\')"><i class="fa-solid fa-play"></i> Start</button>':'') +
          (canStop?'<button class="action-btn stop" onclick="stopAccount(\''+esc(a.uid)+'\')"><i class="fa-solid fa-stop"></i> Stop</button>':'') +
          (canRestart?'<button class="action-btn restart" onclick="restartAccount(\''+esc(a.uid)+'\')"><i class="fa-solid fa-rotate-right"></i> Restart</button>':'') +
          '<button class="action-btn refresh" onclick="refreshAccountInfo(\''+esc(a.uid)+'\')"><i class="fa-solid fa-arrows-rotate"></i></button>' +
          '<button class="action-btn delete" onclick="deleteAccount(\''+esc(a.uid)+'\')"><i class="fa-solid fa-trash"></i></button>' +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('');
}

async function fetchStats(force){
  if(force===undefined)force=false;
  if(isFetching&&!force)return; isFetching=true;
  try{
    const res=await fetch('/api/stats',{cache:'no-store'});
    const data=await res.json();
    const hash=JSON.stringify({
      a:data.accounts.map(x=>[x.uid,x.current_exp,x.gained_exp,x.status,x.matches_played,x.level,x.target_level,x.nickname,x.game_uid]),
      m:data.total_matches,e:data.total_gained_exp
    });
    document.getElementById('stat-total-accounts').innerText=data.total_accounts;
    document.getElementById('stat-total-exp').innerText='+'+Number(data.total_gained_exp).toLocaleString();
    document.getElementById('stat-total-matches').innerText=data.total_matches;
    if(data.uptime!==undefined){serverUptimeBase=data.uptime;localStartTime=Date.now()}
    if(force||hash!==lastDataHash){lastDataHash=hash;renderAccounts(data.accounts||[])}
  }catch(e){console.error(e)}
  finally{isFetching=false}
}
function esc(t){if(t==null)return '';return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function updateUptime(){
  const s=serverUptimeBase+Math.floor((Date.now()-localStartTime)/1000);
  const h=String(Math.floor(s/3600)).padStart(2,'0');
  const m=String(Math.floor((s%3600)/60)).padStart(2,'0');
  const ss=String(s%60).padStart(2,'0');
  document.getElementById('stat-uptime').innerText=h+':'+m+':'+ss;
}
const POLL=1000;
function startPolling(){if(pollTimer)clearInterval(pollTimer);pollTimer=setInterval(()=>{if(!document.hidden)fetchStats(false)},POLL)}
document.addEventListener('visibilitychange',()=>{if(document.hidden){if(pollTimer)clearInterval(pollTimer);pollTimer=null}else{fetchStats(true);startPolling()}});
updateUptime();setInterval(updateUptime,1000);fetchStats(true);startPolling();
let lte=0;document.addEventListener('touchend',e=>{const n=Date.now();if(n-lte<=300)e.preventDefault();lte=n},{passive:false});
</script>
</body>
</html>"""


# ==================== HELPER: DETECT PUBLIC / LAN URL ====================
def _detect_public_url(port: int) -> str:
    railway_domain = (
        os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or os.environ.get("RAILWAY_STATIC_URL")
        or os.environ.get("RAILWAY_URL")
    )
    if railway_domain:
        if not railway_domain.startswith("http"):
            railway_domain = f"https://{railway_domain}"
        return railway_domain

    try:
        s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
        finally:
            s.close()
        if lan_ip and lan_ip != "127.0.0.1":
            return f"http://{lan_ip}:{port}"
    except Exception:
        pass

    return ""


# ==================== HTTP HANDLERS ====================

def _load_accounts_file():
    try:
        if os.path.exists("accounts.json"):
            with open("accounts.json", "r", encoding="utf-8-sig") as f:
                c = f.read().strip()
            return json.loads(c) if c else []
    except Exception:
        pass
    return []


def _save_accounts_file(data):
    tmp = "accounts.json.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, "accounts.json")


async def handle_index(request: web.Request) -> web.Response:
    return web.Response(text=DASHBOARD_HTML, content_type="text/html", charset="utf-8")


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


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
        existing = _load_accounts_file()

        if "uid" in data and "password" in data:
            uid = str(data["uid"]).strip()
            pwd = str(data["password"]).strip()
            target = int(data.get("target_level", 0) or 0)
            if not uid or not pwd:
                return web.json_response({"status": "error", "error": "UID and Password required"})
            existing = [a for a in existing if str(a.get("uid")) != uid]
            existing.append({"uid": uid, "password": pwd, "target_level": target})
            bot_state.log(f"New account added: {uid} (target Lv{target})", "success", uid)

            if uid not in bot_state.accounts:
                bot_state.accounts[uid] = {
                    "uid": uid,
                    "game_uid": uid,
                    "nickname": f"Player_{uid[-6:]}" if len(uid) > 6 else f"Player_{uid}",
                    "region": "—",
                    "level": 0,
                    "initial_exp": 0,
                    "current_exp": 0,
                    "gained_exp": 0,
                    "likes": 0,
                    "status": "CONNECTING",
                    "target_level": target,
                    "matches_played": 0,
                    "active_matches": 0,
                    "last_match_time": None,
                    "last_updated": time.strftime("%H:%M:%S"),
                    "completed_at": None
                }
            else:
                bot_state.accounts[uid]["target_level"] = target
                bot_state.accounts[uid]["status"] = "CONNECTING"
        elif "token" in data:
            token = str(data["token"]).strip()
            target = int(data.get("target_level", 0) or 0)
            if not token:
                return web.json_response({"status": "error", "error": "Token required"})
            existing = [a for a in existing if a.get("token") != token]
            existing.append({"token": token, "target_level": target})
            bot_state.log(f"New token account added (target Lv{target})", "success")

            tkey = f"tok_{token[:20]}"
            if tkey not in bot_state.accounts:
                bot_state.accounts[tkey] = {
                    "uid": tkey,
                    "game_uid": tkey,
                    "nickname": f"Token_{token[:6]}",
                    "region": "—",
                    "level": 0,
                    "initial_exp": 0,
                    "current_exp": 0,
                    "gained_exp": 0,
                    "likes": 0,
                    "status": "CONNECTING",
                    "target_level": target,
                    "matches_played": 0,
                    "active_matches": 0,
                    "last_match_time": None,
                    "last_updated": time.strftime("%H:%M:%S"),
                    "completed_at": None
                }
            else:
                bot_state.accounts[tkey]["target_level"] = target
                bot_state.accounts[tkey]["status"] = "CONNECTING"
        else:
            return web.json_response({"status": "error", "error": "Invalid payload"})

        _save_accounts_file(existing)

        if "on_account_added" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"](data))

        return web.json_response({"status": "ok", "auto_started": False})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_start_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if not uid:
            return web.json_response({"status": "error", "error": "uid required"})

        if "on_start_account" not in bot_state.refresh_callbacks:
            return web.json_response({"status": "error", "error": "callback not registered"})

        if uid in bot_state.accounts:
            bot_state.accounts[uid]["status"] = "CONNECTING"
            bot_state.accounts[uid]["last_updated"] = time.strftime("%H:%M:%S")

        result = await bot_state.refresh_callbacks["on_start_account"](uid)
        if result:
            bot_state.account_states[uid] = "running"
            bot_state.log(f"Account {uid} started", "info", uid)
            return web.json_response({"status": "ok"})
        else:
            if uid in bot_state.accounts:
                bot_state.accounts[uid]["status"] = "OFFLINE"
            return web.json_response({"status": "error", "error": "Start failed — check logs"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_stop_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if not uid:
            return web.json_response({"status": "error", "error": "uid required"})

        if "on_stop_account" in bot_state.refresh_callbacks:
            await bot_state.refresh_callbacks["on_stop_account"](uid)
        bot_state.account_states[uid] = "stopped"
        bot_state.update_status(uid, "STOPPED")
        bot_state.log(f"Account {uid} stopped", "warning", uid)
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_restart_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if not uid:
            return web.json_response({"status": "error", "error": "uid required"})

        if "on_stop_account" in bot_state.refresh_callbacks:
            await bot_state.refresh_callbacks["on_stop_account"](uid)
        await asyncio.sleep(1)

        if uid in bot_state.accounts:
            bot_state.accounts[uid]["status"] = "OFFLINE"
            bot_state.accounts[uid]["completed_at"] = None

        if "on_start_account" not in bot_state.refresh_callbacks:
            return web.json_response({"status": "error", "error": "callback not registered"})

        result = await bot_state.refresh_callbacks["on_start_account"](uid)
        if result:
            bot_state.account_states[uid] = "running"
            bot_state.log(f"Account {uid} restarted", "info", uid)
            return web.json_response({"status": "ok"})
        else:
            return web.json_response({"status": "error", "error": "Restart failed"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_delete_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if not uid:
            return web.json_response({"status": "error", "error": "uid required"})

        guest_uid = None
        token_key = None
        game_uid = None

        card = bot_state.accounts.get(uid)
        if card:
            game_uid = card.get("game_uid")

        cred = bot_state.account_credentials.get(uid)
        if cred:
            if cred.get('auth_type') == 'guest' and cred.get('auth_uid'):
                guest_uid = str(cred['auth_uid'])
            elif cred.get('auth_type') == 'token' and cred.get('auth_token'):
                token_key = f"tok_{cred['auth_token'][:20]}"
        else:
            guest_uid = uid

        existing = _load_accounts_file()
        new_list = []
        for acc in existing:
            acc_uid = str(acc.get("uid", "")).strip()
            acc_token = str(acc.get("token", "")).strip()
            acc_game_id = str(acc.get("account_id", "")).strip()

            if acc_uid and (acc_uid == uid or acc_uid == guest_uid):
                continue
            if acc_token and cred and cred.get('auth_token'):
                if acc_token[:20] == cred.get('auth_token', '')[:20]:
                    continue
            if acc_token and f"tok_{acc_token[:20]}" == uid:
                continue
            if game_uid and acc_game_id == game_uid:
                continue
            new_list.append(acc)
        _save_accounts_file(new_list)

        if os.path.exists("token_cache.json"):
            try:
                with open("token_cache.json", "r", encoding="utf-8") as f:
                    c = f.read().strip()
                cache_data = json.loads(c) if c else {}
                keys_to_del = []
                for k in list(cache_data.keys()):
                    if k == uid or k == guest_uid or (token_key and k == token_key):
                        keys_to_del.append(k)
                        continue
                    entry = cache_data[k]
                    if isinstance(entry, dict):
                        if str(entry.get('account_id')) == uid:
                            keys_to_del.append(k)
                        elif game_uid and str(entry.get('account_id')) == game_uid:
                            keys_to_del.append(k)
                        elif guest_uid and str(entry.get('auth_uid')) == guest_uid:
                            keys_to_del.append(k)
                for k in keys_to_del:
                    del cache_data[k]
                tmp = "token_cache.json.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(cache_data, f, indent=2)
                os.replace(tmp, "token_cache.json")
                try:
                    import main as _m
                    _m._token_cache_memo = {}
                    _m._token_cache_memo_time = 0.0
                except Exception:
                    pass
            except Exception as e:
                print(f"[DELETE] token_cache error: {e}")

        bot_state.accounts.pop(uid, None)
        if guest_uid and guest_uid != uid:
            bot_state.accounts.pop(guest_uid, None)
        if game_uid and game_uid != uid:
            bot_state.accounts.pop(game_uid, None)

        if "on_stop_account" in bot_state.refresh_callbacks:
            try:
                await bot_state.refresh_callbacks["on_stop_account"](uid)
            except Exception:
                pass

        for k in [uid, guest_uid, token_key, game_uid]:
            if not k:
                continue
            if k in bot_state.account_workers:
                try:
                    bot_state.account_workers[k].cancel()
                except Exception:
                    pass
                del bot_state.account_workers[k]
            bot_state.account_credentials.pop(k, None)
            bot_state.account_states.pop(k, None)

        bot_state.log(f"Account {uid} removed from all storage", "warning", uid)
        return web.json_response({"status": "ok"})
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
    env_port = os.environ.get("PORT")
    if port is None or env_port:
        port = int(env_port) if env_port else (port or 5000)

    print(f"[BOOT] Binding web dashboard to {host}:{port} (env PORT={env_port})")

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/healthz", handle_health)
    app.router.add_get("/api/stats", handle_get_stats)
    app.router.add_post("/api/account/add", handle_add_account)
    app.router.add_post("/api/account/start", handle_start_account)
    app.router.add_post("/api/account/stop", handle_stop_account)
    app.router.add_post("/api/account/restart", handle_restart_account)
    app.router.add_post("/api/account/delete", handle_delete_account)
    app.router.add_post("/api/account/refresh", handle_refresh_account)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    print(f"\033[92m[+] ✅ Web Dashboard BOUND to {host}:{port}\033[0m")

    public_url = _detect_public_url(port)
    if public_url:
        print(f"\033[92m[+] 🌐 Dashboard URL: {public_url}\033[0m")
    else:
        print(f"\033[92m[+] 📡 Dashboard listening on port {port}\033[0m")