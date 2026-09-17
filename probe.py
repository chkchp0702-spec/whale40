#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe.py — 어느 데이터 소스가 GitHub 서버에서 접속 가능한지 확인만 합니다.
아무것도 만들지 않고, 결과만 출력합니다. 2분이면 끝납니다.
"""
import json, os, sys, time
import requests

UA = os.environ.get("SEC_USER_AGENT", "Whale40 Research contact@example.com")
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
})

TESTS = [
    ("SEC 공시 API (직접)",
     "https://data.sec.gov/submissions/CIK0001067983.json", "BERKSHIRE"),
    ("SEC CIK 명부 (직접)",
     "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt", "BERKSHIRE"),
    ("13f.info 펀드 목록",
     "https://13f.info/managers/b", "Berkshire"),
    ("13f.info 버크셔 페이지",
     "https://13f.info/manager/0001067983-berkshire-hathaway-inc", "Berkshire"),
    ("Dataroma 버핏",
     "https://www.dataroma.com/m/holdings.php?m=BRK", "Berkshire"),
    ("HedgeFollow 버크셔",
     "https://hedgefollow.com/funds/Berkshire+Hathaway", "Berkshire"),
    ("Stooq 주가 (AAPL)",
     "https://stooq.com/q/d/l/?s=aapl.us&i=d", "Date"),
    ("Yahoo Finance 주가 (AAPL)",
     "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1y&interval=1d", "timestamp"),
]

print("=" * 58)
print(" 데이터 소스 접속 테스트 — GitHub 서버에서 실행 중")
print("=" * 58)

ok_list, fail_list = [], []
for name, url, needle in TESTS:
    try:
        r = S.get(url, timeout=30)
        body = r.text[:4000]
        if r.status_code == 200 and needle.lower() in body.lower():
            print(f"  [성공]  {name}")
            print(f"          크기 {len(r.content):,} bytes")
            ok_list.append(name)
        elif r.status_code == 200:
            print(f"  [의심]  {name}  — 200이지만 '{needle}' 없음")
            print(f"          앞부분: {body[:110].strip()!r}")
            fail_list.append(name)
        else:
            print(f"  [실패]  {name}  — HTTP {r.status_code}")
            print(f"          {body[:110].strip()!r}")
            fail_list.append(name)
    except Exception as e:
        print(f"  [오류]  {name}  — {type(e).__name__}: {e}")
        fail_list.append(name)
    time.sleep(1.5)

print("=" * 58)
print(f" 성공 {len(ok_list)}건 / 실패 {len(fail_list)}건")
if ok_list:
    print("\n 사용 가능:")
    for n in ok_list:
        print(f"   · {n}")
print("\n 이 결과를 그대로 알려주시면 됩니다.")
print("=" * 58)
