import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import mysql.connector
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ====================== 数据库连接 ======================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",         # 你的Navicat用户名
    "password": "123456",   # 你的密码
    "database": "mlb",      
    "charset": "utf8mb4"
}
# =========================================================

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
NBA_TAG = "mlb"  # 已改为 MLB 标签

# 数据库连接
def get_db():
    return mysql.connector.connect(**DB_CONFIG)

# 插入数据（表名改为 mlb_market_price）
def insert_price_batch(rows):
    db = get_db()
    cursor = db.cursor()
    sql = """
    INSERT INTO mlb_market_price (
        event_title, team1, team2, token1, token2, ts, time_utc, price1, price2
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    cursor.executemany(sql, rows)
    db.commit()
    cursor.close()
    db.close()
    print(f"  → 插入 {len(rows)} 条 MLB 价格数据")

def http_json(url, method="GET", payload=None, retries=5, timeout=120):
    body = None
    headers = {"User-Agent": "Mozilla/5.0"}
    if payload:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise e

def fetch_all_events(start_iso, end_iso):
    events = []
    cursor = None
    while True:
        params = {
            "tag_slug": NBA_TAG,  # 抓取 MLB 赛事
            "start_date_min": start_iso,
            "start_date_max": end_iso,
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor
        url = f"{GAMMA_BASE}/events/keyset?{urllib.parse.urlencode(params)}"
        data = http_json(url)
        new_events = data.get("events", [])
        if not new_events:
            break
        events.extend(new_events)
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return events

def get_moneyline_markets(events):
    markets = []
    for ev in events:
        for mkt in ev.get("markets", []):
            if mkt.get("sportsMarketType") != "moneyline":
                continue
            tokens = json.loads(mkt.get("clobTokenIds", "[]"))
            outcomes = json.loads(mkt.get("outcomes", "[]"))
            if len(tokens) >= 2 and len(outcomes) >= 2:
                markets.append({
                    "event_title": ev.get("title"),
                    "team1": outcomes[0],
                    "team2": outcomes[1],
                    "token1": tokens[0],
                    "token2": tokens[1]
                })
            break
    return markets

# 1分钟级价格
def fetch_price_history(token_id, start_ts, end_ts):
    url = f"{CLOB_BASE}/prices-history?market={token_id}&startTs={start_ts}&endTs={end_ts}&fidelity=1"
    data = http_json(url)
    return data.get("history", [])

def main():
    # 最近3天
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=3)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    start_iso = start_dt.isoformat().replace("+00:00", "Z")
    end_iso = end_dt.isoformat().replace("+00:00", "Z")

    print("抓取 MLB 赛事...")
    events = fetch_all_events(start_iso, end_iso)
    print(f"MLB 赛事数量: {len(events)}")

    print("筛选 MLB 胜负盘...")
    markets = get_moneyline_markets(events)
    print(f"MLB 胜负盘数量: {len(markets)}")

    print("开始抓取 MLB 分钟级价格并入库...")
    for idx, m in enumerate(markets, 1):
        print(f"\n[{idx}/{len(markets)}] {m['event_title']}")

        h1 = fetch_price_history(m["token1"], start_ts, end_ts)
        h2 = fetch_price_history(m["token2"], start_ts, end_ts)

        map1 = {int(p["t"]): p["p"] for p in h1}
        map2 = {int(p["t"]): p["p"] for p in h2}

        all_ts = sorted(set(map1.keys()) | set(map2.keys()))
        batch = []

        for ts in all_ts:
            time_utc = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            p1 = map1.get(ts)
            p2 = map2.get(ts)
            batch.append((
                m["event_title"],
                m["team1"],
                m["team2"],
                m["token1"],
                m["token2"],
                ts,
                time_utc,
                p1,
                p2
            ))

        if batch:
            insert_price_batch(batch)

    print("\n✅ MLB 数据全部完成！可在Navicat查看 mlb_market_price 表")

if __name__ == "__main__":
    main()