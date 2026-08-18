#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csg-power-daily4 金价监测 · 每日更新提交脚本
用法（在 csg-power-daily4 仓库目录内执行）：
    python update_gold.py                      # 尽力抓取实时金价并提交
    python update_gold.py --note "今日新闻摘要..."   # 追加一条当日动态
    python update_gold.py --json '{"xau_usd":4460.1,"dxy":99.5,"us30y":5.2}'  # 直接写入行情
    python update_gold.py --message "自定义提交说明"

行为：
  1. 读取 GitHub Token（优先环境变量 GH_TOKEN，其次 ../csg_token.txt 或 ./csg_token.txt）
  2. 尽力抓取实时金价（gold-api.com 等公开接口；失败则沿用上次快照）
  3. 更新 daily.json 的 live / daily 字段
  4. git add -A 并提交（提交信息含当日北京时间），推送到 origin main

注意：Token 仅用于推送，不会被写入仓库任何文件。
"""
import os, sys, json, subprocess, datetime, argparse, urllib.request

REPO = "hxj0515/csg-power-daily4"
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(REPO_DIR, "daily.json")

GOLD_APIS = [
    "https://api.gold-api.com/price/XAU",
    "https://data-asg.goldprice.org/dbXRates/USD",
]

def get_token():
    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    for p in [os.path.join(REPO_DIR, "..", "csg_token.txt"),
              os.path.join(REPO_DIR, "csg_token.txt")]:
        try:
            if os.path.exists(p):
                return open(p, "r", encoding="utf-8").read().strip()
        except Exception:
            pass
    return None

def bj_now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))

def load():
    with open(DATA, "r", encoding="utf-8") as f:
        return json.load(f)

def save(d):
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def try_fetch_live():
    """尽力抓取 XAU/USD 实时价格，返回 dict 或 None"""
    for url in GOLD_APIS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                j = json.loads(r.read().decode("utf-8", "ignore"))
            if url.startswith("https://api.gold-api.com") and j.get("price"):
                return {"xau_usd": float(j["price"]), "fetched_at": bj_now().strftime("%Y-%m-%d %H:%M"), "source": "gold-api.com"}
            if url.startswith("https://data-asg.goldprice.org") and j.get("items"):
                items = j["items"]
                if items and items[0].get("xauPrice"):
                    return {"xau_usd": float(items[0]["xauPrice"]), "fetched_at": bj_now().strftime("%Y-%m-%d %H:%M"), "source": "goldprice.org"}
        except Exception:
            continue
    return None

def run(cmd, **kw):
    print("+", " ".join(cmd) if isinstance(cmd, list) else cmd)
    return subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, **kw)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", default=None, help="追加一条当日动态说明")
    ap.add_argument("--json", default=None, help='覆盖 live 字段，如 {"xau_usd":4460.1}')
    ap.add_argument("--message", default=None, help="自定义提交信息")
    args = ap.parse_args()

    token = get_token()
    if not token:
        print("ERROR: 未找到 GH_TOKEN（环境变量或 token 文件）。")
        sys.exit(1)

    d = load()
    today = bj_now().strftime("%Y-%m-%d")
    d["meta"]["updated"] = today
    changed = False

    # 1) 实时行情抓取（尽力而为）
    if args.json:
        try:
            patch = json.loads(args.json)
            d["live"].update(patch)
            d["live"]["fetched_at"] = d["live"].get("fetched_at") or bj_now().strftime("%Y-%m-%d %H:%M")
            changed = True
        except Exception as e:
            print("WARN: --json 解析失败:", e)
    else:
        live = try_fetch_live()
        if live:
            d["live"].update(live)
            changed = True
            print("已抓取实时金价:", live["xau_usd"])

    # 2) 追加当日动态
    if args.note or (live and changed):
        entry = {"date": today, "note": args.note or f"每日自动化快照：XAU/USD {d['live'].get('xau_usd')}（来源 {d['live'].get('source')}）。", "items": []}
        if live and changed:
            price = d["live"].get("xau_usd")
            prev = d["live"].get("prev_close")
            chg = (f"（较昨结 {prev} 变化 {((price/prev)-1)*100:+.2f}%）") if (price and prev) else ""
            entry["items"].append({
                "domain": "实时行情",
                "title": f"伦敦金 XAU/USD {price}{chg}",
                "url": "",
                "summary": f"每日自动更新：{d['live'].get('fetched_at')} 快照。美元指数 {d['live'].get('dxy')}，10Y 美债 {d['live'].get('us10y')}%，30Y {d['live'].get('us30y')}%。三信号：ETF/央行/美债收益率状态请对比 daily.json watch_signals。",
            })
        if entry["items"] or args.note:
            # 当日已存在则合并
            if d["daily"] and d["daily"][0]["date"] == today:
                if args.note:
                    d["daily"][0]["note"] = args.note
                d["daily"][0]["items"] = entry["items"] + d["daily"][0]["items"]
            else:
                d["daily"].insert(0, entry)
            changed = True

    save(d)
    if not changed:
        print("无变更，跳过提交。")

    msg = args.message or f"daily: 金价监测 {today}"
    run(["git", "config", "user.name", "csg-gold-bot"])
    run(["git", "config", "user.email", "bot@csg-gold.local"])
    remote = f"https://{token}@github.com/{REPO}.git"
    run(["git", "remote", "set-url", "origin", remote])
    run(["git", "add", "-A"])
    st = run(["git", "status", "--porcelain"])
    if not st.stdout.decode("utf-8", "ignore").strip():
        print("无文件变更，已跳过推送。")
        return
    run(["git", "commit", "-m", msg])
    run(["git", "push", "origin", "HEAD"])
    print("已推送：", msg)

if __name__ == "__main__":
    main()
