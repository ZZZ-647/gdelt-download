#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GDELT A1 批量下载器（GitHub Actions / 海外机器用，直连 GDELT）
================================================================
- 51 国 x 2017-2021 x 2 模式（tone + volume）= 510 次请求
- 每次成功请求间隔 5 秒（遵守 GDELT 限流）
- 429 自动等待 60s x 次数 重试，每文件最多重试 10 次
- 断点续传：已下载的文件自动跳过，重跑即可续传
- 输出到 ./gdelt_downloads/，并生成下载报告
"""
import csv
import os
import sys
import time
import urllib.parse
import urllib.request

COUNTRIES = [
    "angola", "argentina", "armenia", "burundi", "benin", "bulgaria",
    "bolivia", "brazil", "chile", "cameroon", "colombia", "dominicanrepublic",
    "ecuador", "egypt", "fiji", "gabon", "indonesia", "india", "iran", "iraq",
    "israel", "jamaica", "jordan", "kazakhstan", "kenya", "laos", "srilanka",
    "morocco", "mexico", "mongolia", "mozambique", "mauritania", "mauritius",
    "malaysia", "namibia", "niger", "nigeria", "peru", "philippines", "rwanda",
    "senegal", "togo", "thailand", "tajikistan", "tunisia", "turkey", "ukraine",
    "uruguay", "venezuela", "zambia", "zimbabwe",
]

YEARS = ["2017", "2018", "2019", "2020", "2021"]

# (mode参数, 文件标签)
MODES = [
    ("timelinetone", "tone"),
    ("timelinevolinfo", "vol"),
]

QUERY = "(China OR Chinese)"
BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
INTERVAL = 5          # 成功请求间隔（秒）
BACKOFF = 60          # 429 等待基数（秒）
MAX_RETRY = 10        # 每文件最大重试次数
OUT = "gdelt_downloads"
UA = "Mozilla/5.0 (gdelt-batch-download; academic research)"


def fetch(country, mode, year):
    params = {
        "query": f"{QUERY} sourcecountry:{country} -sourcelang:chinese",
        "mode": mode,
        "format": "csv",
        "startdatetime": f"{year}0101000000",
        "enddatetime": f"{year}1231235959",
        "timelinesmooth": "0",
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def health_check():
    """先用最小请求探测 GDELT 是否可用；429 时等待重试，最多 15 分钟。"""
    url = (BASE + "?query=china&mode=artlist&maxrecords=1&timespan=1h")
    for i in range(1, 16):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"[health] OK 状态{r.status}", flush=True)
                return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                w = 60 * i
                print(f"[health] 429 第{i}次，等待{w}s", flush=True)
                time.sleep(w)
            else:
                print(f"[health] HTTP {e.code}", flush=True)
                return False
        except Exception as e:
            print(f"[health] {type(e).__name__}: {e}", flush=True)
            time.sleep(20)
    return False


def download_one(country, mode, year):
    fname = f"GDELT_A1_{country}_{mode}_{year}.csv"
    fpath = os.path.join(OUT, fname)
    if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
        return "skip", fname
    for attempt in range(1, MAX_RETRY + 1):
        try:
            body = fetch(country, mode, year)
            with open(fpath, "wb") as fh:
                fh.write(body)
            return "ok", fname
        except urllib.error.HTTPError as e:
            if e.code == 429:
                w = BACKOFF * attempt
                print(f"    [429] {fname} 等待{w}s (第{attempt}次)", flush=True)
                time.sleep(w)
            else:
                return f"http{e.code}", fname
        except Exception as e:
            print(f"    [err] {fname} {type(e).__name__}: {e}", flush=True)
            time.sleep(10)
            return "error", fname
    return "fail429", fname


def main():
    os.makedirs(OUT, exist_ok=True)
    print(f"国家 {len(COUNTRIES)} x 年份 {len(YEARS)} x 模式 {len(MODES)} = "
          f"{len(COUNTRIES)*len(YEARS)*len(MODES)} 个文件", flush=True)

    if not health_check():
        print("[health] GDELT 探测失败，请稍后重跑（会换一台新机器/新IP）", flush=True)
        sys.exit(1)

    results = []
    total = len(COUNTRIES) * len(YEARS) * len(MODES)
    done = 0
    t0 = time.time()

    for c in COUNTRIES:
        for mode_api, mode_tag in MODES:
            for y in YEARS:
                done += 1
                status, fname = download_one(c, mode_api, y)
                results.append((c, mode_tag, y, status, fname))
                print(f"[{done}/{total}] {status.upper():8s} {fname}", flush=True)
                time.sleep(INTERVAL)

    rep = os.path.join(OUT, "download_report.csv")
    with open(rep, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["country", "mode", "year", "status", "file"])
        w.writerows(results)

    bad = [r for r in results if r[3] not in ("ok", "skip")]
    good = len(results) - len(bad)
    print(f"\n完成：成功 {good} / 共 {len(results)}，失败 {len(bad)} 项，"
          f"用时 {(time.time()-t0)/60:.1f} 分钟", flush=True)
    print(f"报告：{rep}", flush=True)
    if bad:
        print("失败清单：", flush=True)
        for r in bad:
            print("  ", r, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
