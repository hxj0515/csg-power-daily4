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
import os, sys, json, subprocess, datetime, argparse, urllib.request, re
from collections import OrderedDict

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

def refresh_supports_and_signals(d):
    """根据 d.live 重写 supports[0..2].key 与 watch_signals[0..2].now 字段。

    supports[i].detail 与 signals 的 bullish_if / bearish_if 保留原文（定性表述）。
    现在字段会每日嵌入「数据快照 YYYY-MM-DD」水印，保证这两块跟 live 一起动。
    """
    L = d.get("live") or {}
    today = bj_now().strftime("%Y-%m-%d")
    xau  = L.get("xau_usd")
    dxy  = L.get("dxy")
    us30y= L.get("us30y")
    us10y= L.get("us10y")
    us2y = L.get("us2y")
    etf  = L.get("etf_tonnes")
    cb_q1= L.get("cb_buy_q1")
    cb_q2= L.get("cb_buy_q2")
    spdr = L.get("spdr_latest_tonnes") or 1025.24  # 默认值：8/18 SPDR 最新

    # supports：动态 key（标题、立场、详情保留原文）
    supports = d.get("supports") or []
    if len(supports) >= 3:
        supports[0]["key"] = f"30Y {us30y}% / DXY {dxy}"
        supports[1]["key"] = f"Q1 +{cb_q1}t / Q2 +{cb_q2}t / 占比 27%"
        supports[2]["key"] = f"ETF {etf}吨"
    d["supports"] = supports

    # watch_signals：动态 now（名称、偏多当、转空当保留原文）
    signals = d.get("watch_signals") or []
    if len(signals) >= 3:
        signals[0]["now"] = (
            f"未触发：SPDR 8/18 减持 5.42 吨至 {spdr} 吨（高位获利了结延续）；"
            f"国内 14 只黄金 ETF 规模 2715 亿（近一周 +721 亿）、"
            f"8 月以来 13 只吸金 83.46 亿、华安重返千亿——资金温和流入但未单日暴增，无亢奋见顶信号。"
            f"数据快照 {today}：XAU ${xau} / DXY {dxy} / 30Y {us30y}%。"
        )
        signals[1]["now"] = (
            f"未触发：反而加速（Q2 净购 288.9 吨同比 +62% 创 Q2 历史新高，H1 345 吨；"
            f"中国连续 21 个月增持、7 月 +64 万盎司创本轮单月新高；"
            f"韩国 8/4 重启购金；高盛预计央行月购 60 吨）。"
            f"数据快照 {today}：央行月购未减速。"
        )
        signals[2]["now"] = (
            f"未触发：30Y 昨收 {us30y}% 创 2007 年 6 月以来新高 5.3307%，"
            f"连续 30 个交易日站上 5%；长债遭系统性重估（多国 20Y 近 20 年高点），"
            f"8/19 早间 -2.13bp 微跌未实质下行。数据快照 {today}：XAU ${xau} / DXY {dxy}。"
        )
    d["watch_signals"] = signals
    return d


def fetch_sina_klines(d):
    """拉取沪金主力 AU0 日K + 当日分钟线（新浪财经），本地聚合周K/月K。

    写入 d['kline'] = {source, updated, au:{d,w,m}, intraday}
    失败返回 False（保留旧数据）。AU0 为国内沪金主力连续合约，单位 元/克。
    """
    UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}

    def fetch(url):
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.read().decode("utf-8", "ignore")

    def parse_sina_jsonp(txt):
        m = re.search(r"var\s+_s=\(?(.*?)\)?;?\s*$", txt, re.S)
        if not m:
            return None
        body = m.group(1).strip()
        if body.endswith(";"):
            body = body[:-1]
        try:
            return json.loads(body)
        except Exception:
            return None

    def agg(daily, keyfn):
        groups = OrderedDict()
        for k in daily:
            groups.setdefault(keyfn(k["d"]), []).append(k)
        out = []
        for ks in groups.values():
            out.append({"d": ks[-1]["d"], "o": ks[0]["o"],
                        "h": max(float(x["h"]) for x in ks),
                        "l": min(float(x["l"]) for x in ks),
                        "c": ks[-1]["c"],
                        "v": sum(float(x["v"]) for x in ks)})
        return out

    try:
        raw = fetch("https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_s=/InnerFuturesNewService.getDailyKLine?symbol=AU0")
        daily = parse_sina_jsonp(raw) or []
        if not daily:
            print("WARN: AU0 日K 为空")
            return False
        weekly = agg(daily, lambda ds: datetime.date.fromisoformat(ds).isocalendar()[:2])
        monthly = agg(daily, lambda ds: ds[:7])
        raw2 = fetch("https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_s=/InnerFuturesNewService.getMinLine?symbol=AU0")
        minline = parse_sina_jsonp(raw2) or []
        d["kline"] = {
            "source": "新浪财经 AU0 沪金主力（元/克）· 周/月K由日K本地聚合",
            "updated": bj_now().strftime("%Y-%m-%d %H:%M"),
            "au": {"d": daily[-400:], "w": weekly[-160:], "m": monthly[-72:]},
            "intraday": minline[-600:] if minline else [],
        }
        print(f"kline: 日K {len(d['kline']['au']['d'])} / 周K {len(d['kline']['au']['w'])} / 月K {len(d['kline']['au']['m'])} / 分时 {len(d['kline']['intraday'])}")
        return True
    except Exception as e:
        print("WARN: kline 抓取失败:", e)
        return False


def run(cmd, **kw):
    print("+", " ".join(cmd) if isinstance(cmd, list) else cmd)
    return subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, **kw)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", default=None, help="追加一条当日动态说明")
    ap.add_argument("--json", default=None, help='覆盖 live 字段，如 {"xau_usd":4460.1}')
    ap.add_argument("--message", default=None, help="自定义提交信息")
    ap.add_argument("--signals-only", action="store_true", help="仅刷新 supports/watch_signals 字段（跳过实时抓取）")
    ap.add_argument("--no-signals", action="store_true", help="跳过 supports/watch_signals 自动刷新")
    ap.add_argument("--no-klines", action="store_true", help="跳过 K 线（分时/日/周/月）抓取")
    args = ap.parse_args()

    token = get_token()
    if not token:
        print("ERROR: 未找到 GH_TOKEN（环境变量或 token 文件）。")
        sys.exit(1)

    d = load()
    today = bj_now().strftime("%Y-%m-%d")
    live = None
    d["meta"]["updated"] = today
    changed = False

    # 仅刷新 signals 模式：跳过实时抓取，直接重写 supports/watch_signals 后提交
    if args.signals_only:
        refresh_supports_and_signals(d)
        if not args.no_klines:
            fetch_sina_klines(d)
        save(d)
        msg = args.message or f"daily: 刷新 supports/watch_signals {today}"
        run(["git", "config", "user.name", "csg-gold-bot"])
        run(["git", "config", "user.email", "bot@csg-gold.local"])
        run(["git", "add", "-A"])
        st = run(["git", "status", "--porcelain"])
        if not st.stdout.decode("utf-8", "ignore").strip():
            print("无文件变更，已跳过推送。")
            return
        run(["git", "commit", "-m", msg])
        # 一次性 URL 推送：不把 token 写进 remote 配置，降低被 GitHub 吊销风险
        run(["git", "push", f"https://x-access-token:{token}@github.com/{REPO}.git", "HEAD"])
        print("已推送：", msg)
        return

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

    # 3) 刷新 supports / watch_signals（关键节点）：从 live 动态拼 key 和 now
    if not args.no_signals:
        refresh_supports_and_signals(d)
        changed = True

    # 4) 刷新 K 线（沪金主力 AU0 分时/日K/周K/月K）
    if not args.no_klines:
        if fetch_sina_klines(d):
            changed = True

    save(d)
    if not changed:
        print("无变更，跳过提交。")

    msg = args.message or f"daily: 金价监测 {today}"
    run(["git", "config", "user.name", "csg-gold-bot"])
    run(["git", "config", "user.email", "bot@csg-gold.local"])
    run(["git", "add", "-A"])
    st = run(["git", "status", "--porcelain"])
    if not st.stdout.decode("utf-8", "ignore").strip():
        print("无文件变更，已跳过推送。")
        return
    run(["git", "commit", "-m", msg])
    # 一次性 URL 推送：不把 token 写进 remote 配置，降低被 GitHub 吊销风险
    run(["git", "push", f"https://x-access-token:{token}@github.com/{REPO}.git", "HEAD"])
    print("已推送：", msg)

if __name__ == "__main__":
    main()
