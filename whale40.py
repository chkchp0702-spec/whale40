#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whale40.py — 고래 40 트래커 (단일 파일)

1년 수익률 기준으로 기관 TOP 20 + 유명인 TOP 20 을 매일 다시 뽑고,
그 40곳이 최근 24시간 안에 낸 편입·매수 공시를 리포트로 만든다.

이름만 적으면 CIK(SEC 고유번호)는 스크립트가 EDGAR에서 찾아 data/cik_map.json 에 저장한다.
잘못 찾은 게 있으면 그 파일을 직접 고치면 된다. (한 번 저장되면 다시 검색하지 않음)

실행:  python whale40.py
필요:  환경변수 SEC_USER_AGENT="홍길동 hong@example.com"
선택:  OPENFIGI_API_KEY (CUSIP→티커 변환 속도 10배)
선택:  TELEGRAM_TOKEN + TELEGRAM_CHAT_ID (텔레그램으로 리포트 받기)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import difflib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ════════════════════════════════════════════════════════ 설정
TOP_N = 20                 # 그룹별 감시 인원
LOOKBACK_DAYS = 365        # 수익률 측정 기간
TOP_HOLDINGS = 20          # 복제할 상위 종목 수
ALERT_HOURS = 24           # 몇 시간 내 공시를 새 것으로 볼지
MIN_ADD_PCT = 20           # 추가 매수로 알릴 최소 증가율(%)
MIN_QUARTERS = 3           # 최소 13F 개수

# 감시 후보 — 이름만 적으면 됩니다. 자유롭게 지우고 추가하세요.
INSTITUTIONS = [
    "Citadel Advisors", "Millennium Management", "D E Shaw", "Two Sigma Investments",
    "AQR Capital Management", "Renaissance Technologies", "Point72 Asset Management",
    "Balyasny Asset Management", "Marshall Wace", "Qube Research",
    "Schonfeld Strategic Advisors", "ExodusPoint Capital", "Bridgewater Associates",
    "Coatue Management", "Lone Pine Capital", "Light Street Capital",
    "Whale Rock Capital Management", "Viking Global Investors", "Tiger Global Management",
    "D1 Capital Partners", "Alyeska Investment Group", "Farallon Capital",
    "Davidson Kempner Capital", "Magnetar Financial", "Pentwater Capital",
    "Baillie Gifford", "Dodge & Cox", "Boston Partners", "WCM Investment Management",
    "Sands Capital Management", "Polen Capital Management", "Durable Capital Partners",
    "Egerton Capital", "AKO Capital", "Longview Partners", "Cantillon Capital",
    "Samlyn Capital", "Steadfast Capital", "Maverick Capital", "Eminence Capital",
    "Glenview Capital", "Luxor Capital Group", "Baker Bros Advisors",
    "RA Capital Management", "Perceptive Advisors", "OrbiMed Advisors",
    "Avoro Capital Advisors", "Deep Track Capital", "EcoR1 Capital",
    "Cormorant Asset Management", "Rock Springs Capital", "Redmile Group",
    "Vivo Capital", "BVF Partners", "Tudor Investment", "Moore Capital Management",
    "Caxton Associates", "Rokos Capital Management", "Capital Fund Management",
    "HBK Investments", "Whitebox Advisors", "Empyrean Capital Partners",
    "Sculptor Capital", "Gotham Asset Management", "Harris Associates",
    "First Eagle Investment Management", "Fundsmith", "Ruane Cunniff",
    "Tweedy Browne", "Southeastern Asset Management", "Ariel Investments",
    "Horizon Kinetics", "Generation Investment Management", "Altimeter Capital",
    "Dragoneer Investment Group", "Foxhaven Asset Management", "Slate Path Capital",
    "Valley Forge Capital", "Valiant Capital Management", "Discovery Capital",
    "Lakewood Capital Management", "Gates Capital Management", "CAS Investment Partners",
    "Abdiel Capital Advisors", "Bridger Management", "Temasek Holdings",
    "Oasis Management", "Ancora Advisors", "Coliseum Capital Management",
    "Boxer Capital", "Fisher Asset Management", "Markel Group",
]

# (표시할 이름, EDGAR에서 검색할 회사명)
PEOPLE = [
    ("워런 버핏", "Berkshire Hathaway"),
    ("빌 애크먼", "Pershing Square Capital Management"),
    ("스탠리 드러켄밀러", "Duquesne Family Office"),
    ("데이비드 테퍼", "Appaloosa"),
    ("칼 아이칸", "Icahn Carl"),
    ("폴 싱어", "Elliott Investment Management"),
    ("댄 러브", "Third Point"),
    ("세스 클라만", "Baupost Group"),
    ("하워드 막스", "Oaktree Capital Management"),
    ("조지 소로스", "Soros Fund Management"),
    ("넬슨 펠츠", "Trian Fund Management"),
    ("제프 스미스", "Starboard Value"),
    ("메이슨 모핏", "ValueAct Capital"),
    ("스콧 퍼거슨", "Sachem Head Capital"),
    ("키스 마이스터", "Corvex Management"),
    ("배리 로젠스타인", "JANA Partners"),
    ("글렌 웰링", "Engaged Capital"),
    ("퀜틴 코피", "Politan Capital Management"),
    ("폴 힐랄", "Mantle Ridge"),
    ("알렉스 데너", "Sarissa Capital"),
    ("캐시 우드", "ARK Investment Management"),
    ("빌 게이츠", "Bill & Melinda Gates Foundation Trust"),
    ("리루", "Himalaya Capital Management"),
    ("모니시 파브라이", "Dalal Street"),
    ("크리스 혼", "TCI Fund Management"),
    ("체이스 콜먼", "Tiger Global Management"),
    ("필립 라퐁", "Coatue Management"),
    ("스티븐 맨델", "Lone Pine Capital"),
    ("안드레아스 할보르센", "Viking Global Investors"),
    ("댄 선드하임", "D1 Capital Partners"),
    ("스티브 코언", "Point72 Asset Management"),
    ("켄 그리핀", "Citadel Advisors"),
    ("이지 잉글랜더", "Millennium Management"),
    ("클리프 애스네스", "AQR Capital Management"),
    ("폴 튜더 존스", "Tudor Investment"),
    ("루이스 베이컨", "Moore Capital Management"),
    ("레이 달리오", "Bridgewater Associates"),
    ("조엘 그린블랫", "Gotham Asset Management"),
    ("빌 나이그렌", "Harris Associates"),
    ("척 애크리", "Akre Capital Management"),
    ("데이비드 에이브럼스", "Abrams Capital Management"),
    ("글렌 그린버그", "Brave Warrior"),
    ("톰 루소", "Gardner Russo"),
    ("톰 게이너", "Markel Group"),
    ("프렘 왓사", "Fairfax Financial Holdings"),
    ("브루스 버코위츠", "Fairholme Capital Management"),
    ("빌 밀러", "Miller Value Partners"),
    ("리언 쿠퍼먼", "Cooperman Leon"),
    ("마이클 버리", "Scion Asset Management"),
    ("프랑수아 로숑", "Giverny Capital"),
    ("크리스 블룸스트란", "Semper Augustus"),
    ("팻 도시", "Dorsey Asset Management"),
    ("노버트 로우", "Punch Card Management"),
    ("클리퍼드 소신", "CAS Investment Partners"),
    ("손정의", "SoftBank Group"),
    ("돤융핑", "H&H International Investment"),
    ("브래드 거스트너", "Altimeter Capital"),
    ("데이비드 아인혼", "Greenlight Capital"),
    ("머리 스탈", "Horizon Kinetics"),
    ("앨 고어", "Generation Investment Management"),
]

# ════════════════════════════════════════════════════════ 기반
ROOT = Path(__file__).resolve().parent
DATA, CACHE, REPORT = ROOT / "data", ROOT / "data" / "cache", ROOT / "report"
for p in (DATA, CACHE / "13f", CACHE / "px", REPORT):
    p.mkdir(parents=True, exist_ok=True)

UA = os.environ.get("SEC_USER_AGENT", "").strip()
if "@" not in UA:
    sys.exit("SEC_USER_AGENT 환경변수가 필요합니다. 예) '홍길동 hong@example.com'")

SEC = requests.Session(); SEC.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
WEB = requests.Session(); WEB.headers.update({"User-Agent": "Mozilla/5.0 (whale40 research)"})


def log(*a): print(*a, file=sys.stderr, flush=True)


def get(session, url, tries=4, sleep=0.12, **kw):
    for i in range(tries):
        try:
            r = session.get(url, timeout=40, **kw)
            time.sleep(sleep)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503):
                time.sleep(2 * (i + 1)); continue
            return None
        except requests.RequestException:
            time.sleep(1 + i)
    return None


def jload(p, d=None):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return d


def jsave(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def norm(s): return re.sub(r"[^a-z0-9]", "", s.lower())


# ════════════════════════════════════════════ 이름 → CIK (자동)
CIKMAP = DATA / "cik_map.json"


def resolve_cik(query: str) -> dict | None:
    """EDGAR 회사검색으로 13F 제출자를 찾는다. 결과는 파일에 저장돼 재검색하지 않는다."""
    mp = jload(CIKMAP, {}) or {}
    if query in mp:
        return mp[query] or None
    r = get(SEC, "https://www.sec.gov/cgi-bin/browse-edgar",
            params={"action": "getcompany", "company": query, "type": "13F-HR",
                    "dateb": "", "owner": "include", "count": "40", "output": "atom"})
    hits = []
    if r:
        try:
            root = strip_ns(ET.fromstring(r.content))
            ci = root.find(".//company-info")
            if ci is not None:                                   # 단일 매칭
                hits = [(ci.findtext("conformed-name", ""), ci.findtext("cik", ""))]
            for e in root.iter("entry"):                          # 다중 매칭
                title = e.findtext("title", "")
                m = re.search(r"CIK=(\d+)", e.findtext("id", "") or "")
                if m:
                    hits.append((re.sub(r"\s*\(.*?\)\s*$", "", title), m.group(1)))
        except ET.ParseError:
            pass
    if not hits:
        mp[query] = None; jsave(CIKMAP, mp)
        log(f"  ✗ '{query}' EDGAR에서 못 찾음")
        return None
    q = norm(query)
    hits.sort(key=lambda h: -difflib.SequenceMatcher(None, q, norm(h[0])).ratio())
    name, cik = hits[0]
    score = difflib.SequenceMatcher(None, q, norm(name)).ratio()
    rec = {"cik": int(cik), "edgar_name": name, "score": round(score, 2)}
    mp[query] = rec; jsave(CIKMAP, mp)
    mark = "  " if score >= 0.7 else " ?"
    log(f" {mark} '{query}' → {name} (CIK {int(cik)}, 일치도 {score:.2f})")
    return rec


# ════════════════════════════════════════════════════════ EDGAR
def submissions(cik):
    r = get(SEC, f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    return r.json() if r else None


def filings_of(sub):
    rec = sub.get("filings", {}).get("recent", {})
    keys = ["accessionNumber", "filingDate", "acceptanceDateTime", "form", "primaryDocument", "reportDate"]
    cols = [rec.get(k, []) for k in keys]
    n = min((len(c) for c in cols), default=0)
    return [dict(zip(keys, [c[i] for c in cols])) for i in range(n)]


def adir(cik, acc): return f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
def iurl(cik, acc): return f"{adir(cik, acc)}/{acc}-index.htm"


def files_in(cik, acc):
    r = get(SEC, adir(cik, acc) + "/index.json")
    try: return [i["name"] for i in r.json()["directory"]["item"]]
    except Exception: return []


def parse_13f(cik, acc):
    c = CACHE / "13f" / f"{cik}_{acc}.json"
    hit = jload(c)
    if hit is not None: return hit
    xs = [f for f in files_in(cik, acc) if f.lower().endswith(".xml") and "primary_doc" not in f.lower()]
    if not xs: jsave(c, {}); return {}
    xs.sort(key=lambda f: ("info" not in f.lower(), f))
    r = get(SEC, f"{adir(cik, acc)}/{xs[0]}")
    if not r: return {}
    try: root = strip_ns(ET.fromstring(r.content))
    except ET.ParseError: jsave(c, {}); return {}
    out = {}
    for it in root.iter("infoTable"):
        cusip = (it.findtext("cusip") or "").strip().upper()
        if len(cusip) != 9 or (it.findtext("putCall") or "").strip():
            continue
        try:
            sh = float(it.findtext("shrsOrPrnAmt/sshPrnamt") or 0)
            val = float(it.findtext("value") or 0)
        except ValueError:
            continue
        h = out.setdefault(cusip, {"name": (it.findtext("nameOfIssuer") or "").strip(), "shares": 0.0, "value": 0.0})
        h["shares"] += sh; h["value"] += val
    jsave(c, out); return out


def quarters(cik, limit=6):
    sub = submissions(cik)
    if not sub: return []
    rows = [f for f in filings_of(sub) if f["form"].upper().startswith("13F-HR") and f["reportDate"]]
    best = {}
    for f in sorted(rows, key=lambda x: x["filingDate"]):
        best[f["reportDate"]] = f
    return sorted(best.values(), key=lambda x: x["reportDate"], reverse=True)[:limit]


# ══════════════════════════════════════════ CUSIP → 티커 (OpenFIGI)
FIGI = DATA / "cusip_ticker.json"


def cusip_to_ticker(cusips):
    mp = jload(FIGI, {}) or {}
    todo = [c for c in dict.fromkeys(cusips) if c not in mp]
    if not todo: return mp
    key = os.environ.get("OPENFIGI_API_KEY", "").strip()
    hdr = {"Content-Type": "application/json"}
    batch, pause = (100, 0.3) if key else (10, 2.6)
    if key: hdr["X-OPENFIGI-APIKEY"] = key
    log(f"CUSIP→티커 변환 {len(todo)}건 (배치 {batch}, 키 {'있음' if key else '없음 — 느림'})")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        try:
            r = WEB.post("https://api.openfigi.com/v3/mapping", headers=hdr, timeout=40,
                         json=[{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in chunk])
        except requests.RequestException:
            time.sleep(5); continue
        if r.status_code == 429: time.sleep(20); continue
        if r.status_code != 200:
            for c in chunk: mp[c] = ""
            time.sleep(pause); continue
        for c, res in zip(chunk, r.json()):
            t = ""
            for d in (res.get("data") or []):
                cand = (d.get("ticker") or "").strip().upper()
                if cand and d.get("securityType2") in ("Common Stock", "Depositary Receipt", None, ""):
                    t = cand; break
            mp[c] = t
        jsave(FIGI, mp); time.sleep(pause)
    return mp


# ════════════════════════════════════════════════════ 주가 (Stooq)
def load_prices(tickers, start):
    out, today = {}, datetime.now(timezone.utc).date().isoformat()
    for t in dict.fromkeys(tickers):
        if not t: continue
        f = CACHE / "px" / f"{t}.json"
        b = jload(f)
        if b and b.get("asof") == today:
            out[t] = b["px"]; continue
        sym = t.replace(".", "-").replace("/", "-").lower() + ".us"
        r = get(WEB, f"https://stooq.com/q/d/l/?s={sym}&i=d", tries=2, sleep=0.25)
        px = {}
        if r and r.text.startswith("Date"):
            for line in r.text.strip().splitlines()[1:]:
                p = line.split(",")
                if len(p) < 5 or p[0] < start: continue
                try: px[p[0]] = float(p[4])
                except ValueError: pass
        elif b:
            px = b["px"]
        jsave(f, {"asof": today, "px": px}); out[t] = px
    return out


def px_at(px, day):
    ks = [k for k in px if k <= day]
    return px[max(ks)] if ks else None


# ════════════════════════════════════════════════════ 수익률 계산
def snapshots(cik):
    qs = quarters(cik, 6)
    if len(qs) < MIN_QUARTERS: return []
    cut = (datetime.now(timezone.utc).date() - timedelta(days=LOOKBACK_DAYS + 130)).isoformat()
    out = []
    for q in sorted([x for x in qs if x["filingDate"] >= cut], key=lambda x: x["filingDate"]):
        h = parse_13f(cik, q["accessionNumber"])
        if not h: continue
        top = sorted(h.items(), key=lambda kv: -kv[1]["value"])[:TOP_HOLDINGS]
        tot = sum(v["value"] for _, v in top)
        if tot <= 0: continue
        out.append({"date": q["filingDate"], "period": q["reportDate"],
                    "weights": {c: v["value"] / tot for c, v in top},
                    "names": {c: v["name"] for c, v in top}})
    return out


def seg_return(w, t0, t1, tmap, px):
    num = wsum = 0.0
    for cusip, wt in w.items():
        t = tmap.get(cusip)
        if not t or t not in px: continue
        p0, p1 = px_at(px[t], t0), px_at(px[t], t1)
        if not p0 or not p1 or p0 <= 0: continue
        num += wt * (p1 / p0 - 1.0); wsum += wt
    return None if wsum < 0.5 else num / wsum


def year_return(snaps, tmap, px, start, end):
    """공시일마다 리밸런싱한다고 보고 구간 수익률을 연쇄 곱."""
    if not snaps: return None, 0.0
    prior = [s for s in snaps if s["date"] <= start]
    active = prior[-1] if prior else snaps[0]
    cur, bounds = max(start, active["date"]), []
    for s in [x for x in snaps if x["date"] > cur]:
        bounds.append((active, cur, s["date"])); active, cur = s, s["date"]
    bounds.append((active, cur, end))
    cum, ok, tot = 1.0, 0, 0
    for snap, a, b in bounds:
        if a >= b: continue
        tot += 1
        r = seg_return(snap["weights"], a, b, tmap, px)
        if r is None: continue
        cum *= (1 + r); ok += 1
    return (None, 0.0) if not ok else (cum - 1, ok / tot)


def rank_group(entries, label):
    """entries: [(표시명, 검색어)]"""
    end = datetime.now(timezone.utc).date()
    start = (end - timedelta(days=LOOKBACK_DAYS)).isoformat()
    pxs = (end - timedelta(days=LOOKBACK_DAYS + 200)).isoformat()
    end = end.isoformat()

    log(f"\n━━━ {label} {len(entries)}곳 ━━━")
    snaps_by, cusips, meta = {}, [], {}
    for disp, query in entries:
        rec = resolve_cik(query)
        if not rec: continue
        cik = rec["cik"]
        if cik in snaps_by:
            continue
        s = snapshots(cik)
        if not s:
            log(f"  - {disp}: 13F 부족, 제외"); continue
        snaps_by[cik] = s
        meta[cik] = {"name": disp, "edgar": rec["edgar_name"], "match": rec["score"]}
        cusips += [c for snap in s for c in snap["weights"]]

    tmap = cusip_to_ticker(cusips)
    tickers = sorted({tmap[c] for c in set(cusips) if tmap.get(c)})
    log(f"{label}: 종목 {len(tickers)}개 주가 로딩")
    px = load_prices(tickers, pxs)

    rows = []
    for cik, s in snaps_by.items():
        r, cov = year_return(s, tmap, px, start, end)
        if r is None:
            log(f"  - {meta[cik]['name']}: 수익률 계산 불가"); continue
        last = s[-1]
        rows.append({**meta[cik], "cik": cik, "ret_1y": round(r * 100, 2),
                     "coverage": round(cov, 2), "period": last["period"], "filed": last["date"],
                     "top": [last["names"][c] for c, _ in
                             sorted(last["weights"].items(), key=lambda kv: -kv[1])[:3]]})
    rows.sort(key=lambda x: -x["ret_1y"])
    for i, row in enumerate(rows, 1): row["rank"] = i
    return rows


# ════════════════════════════════════════════════════ 24시간 감시
WATCH_FORMS = {"13F-HR", "13F-HR/A", "4", "4/A", "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}


def diff_13f(cik, acc, period):
    curr = parse_13f(cik, acc)
    if not curr: return None
    prev_q = [q for q in quarters(cik, 6) if q["reportDate"] < period]
    prev = parse_13f(cik, prev_q[0]["accessionNumber"]) if prev_q else {}
    new, add = [], []
    for c, h in curr.items():
        p = prev.get(c)
        if not p or p["shares"] <= 0:
            new.append({**h, "cusip": c})
        elif h["shares"] > p["shares"]:
            pct = (h["shares"] / p["shares"] - 1) * 100
            if pct >= MIN_ADD_PCT: add.append({**h, "cusip": c, "pct": pct})
    k = lambda x: -x["value"]
    return {"new": sorted(new, key=k), "added": sorted(add, key=k),
            "baseline": bool(prev), "n": len(curr)}


def parse_form4(cik, acc):
    xs = [f for f in files_in(cik, acc) if f.lower().endswith(".xml")]
    if not xs: return None
    r = get(SEC, f"{adir(cik, acc)}/{xs[0]}")
    if not r: return None
    try: root = strip_ns(ET.fromstring(r.content))
    except ET.ParseError: return None
    buys = []
    for t in root.iter("nonDerivativeTransaction"):
        if (t.findtext("transactionCoding/transactionCode") or "").strip() != "P": continue
        buys.append({"shares": float(t.findtext("transactionAmounts/transactionShares/value") or 0),
                     "price": float(t.findtext("transactionAmounts/transactionPricePerShare/value") or 0),
                     "date": (t.findtext("transactionDate/value") or "").strip(),
                     "after": float(t.findtext("postTransactionAmounts/sharesOwnedFollowingTransaction/value") or 0)})
    if not buys: return None
    return {"issuer": (root.findtext("issuer/issuerName") or "").strip(),
            "ticker": (root.findtext("issuer/issuerTradingSymbol") or "").strip(), "buys": buys}


def parse_13dg(cik, acc, primary):
    issuer = pct = ""
    r = get(SEC, f"{adir(cik, acc)}/{primary}") if primary else None
    if r:
        try:
            if primary.lower().endswith(".xml"):
                for el in strip_ns(ET.fromstring(r.content)).iter():
                    tag = el.tag.lower()
                    if not issuer and "issuername" in tag and el.text: issuer = el.text.strip()
                    if not pct and "percentofclass" in tag and el.text: pct = el.text.strip()
            else:
                txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.content.decode("utf-8", "ignore")))
                m = re.search(r"\(?Name of Issuer\)?\s*(.{3,80}?)\s*\(?Title of Class", txt, re.I)
                if m: issuer = m.group(1).strip(" .:")
                m = re.search(r"Row\s*\(?11\)?[^0-9]{0,60}([\d.]+)\s*%", txt, re.I) or \
                    re.search(r"Percent of class[^0-9]{0,60}([\d.]+)\s*%", txt, re.I)
                if m: pct = m.group(1) + "%"
        except Exception:
            pass
    return {"issuer": issuer, "pct": pct}


def scan(watch):
    since = datetime.now(timezone.utc) - timedelta(hours=ALERT_HOURS)
    seen = set(jload(DATA / "seen.json", []) or [])
    hits, fresh = [], []
    for w in watch:
        sub = submissions(w["cik"])
        if not sub: continue
        for f in filings_of(sub):
            form = f["form"].upper()
            if form not in WATCH_FORMS: continue
            try:
                acc_dt = datetime.fromisoformat((f["acceptanceDateTime"] or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if acc_dt < since or f["accessionNumber"] in seen: continue
            fresh.append(f["accessionNumber"])
            base = {"group": w["group"], "rank": w["rank"], "name": w["name"], "ret": w["ret_1y"],
                    "form": f["form"], "at": acc_dt.astimezone().strftime("%m-%d %H:%M"),
                    "url": iurl(w["cik"], f["accessionNumber"])}
            log(f"  [{form}] {w['name']}")
            if form.startswith("13F-HR"):
                d = diff_13f(w["cik"], f["accessionNumber"], f["reportDate"])
                if d and (d["new"] or d["added"]):
                    hits.append({**base, "kind": "13F", "period": f["reportDate"], **d})
            elif form.startswith("4"):
                p = parse_form4(w["cik"], f["accessionNumber"])
                if p: hits.append({**base, "kind": "FORM4", **p})
            else:
                hits.append({**base, "kind": "STAKE", **parse_13dg(w["cik"], f["accessionNumber"], f["primaryDocument"])})
    jsave(DATA / "seen.json", sorted(set(list(seen) + fresh))[-20000:])
    order = {"FORM4": 0, "STAKE": 1, "13F": 2}
    hits.sort(key=lambda h: (order[h["kind"]], h["rank"]))
    return hits


# ════════════════════════════════════════════════════════ 리포트
def money(v):
    return f"${v/1e9:,.2f}B" if v >= 1e9 else (f"${v/1e6:,.1f}M" if v >= 1e6 else f"${v:,.0f}")


def render(inst, ppl, hits, delta):
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    L = [f"# 고래 40 · {today}", "",
         f"1년 수익률 기준 기관 TOP {TOP_N} + 유명인 TOP {TOP_N}, 최근 {ALERT_HOURS}시간 공시.", ""]

    L += [f"## 🔔 최근 {ALERT_HOURS}시간 편입·매수", ""]
    if not hits:
        L += ["새 공시 없음.", ""]
    for h in hits:
        head = f"**{h['name']}** `{h['group']} {h['rank']}위 · 1Y {h['ret']:+.1f}%`"
        if h["kind"] == "FORM4":
            L.append(f"### 🟢 {head}"); L.append(f"{h['issuer']} ({h['ticker']})")
            for b in h["buys"]:
                L.append(f"- 매수 {b['shares']:,.0f}주 @ ${b['price']:,.2f} ({b['date']}) → 보유 {b['after']:,.0f}주")
        elif h["kind"] == "STAKE":
            L.append(f"### 🔵 {head}")
            L.append(f"{h['form']} · **{h['issuer'] or '(원문 확인)'}**" + (f" · 지분 {h['pct']}" if h["pct"] else ""))
        else:
            L.append(f"### 🟣 {head}"); L.append(f"13F {h['period']} · {h['n']}종목")
            if not h["baseline"]: L.append("- _직전 분기 자료 없음 → 전량 신규 표시_")
            for x in h["new"][:10]: L.append(f"- ✨ 신규 **{x['name']}** {x['shares']:,.0f}주 · {money(x['value'])}")
            for x in h["added"][:10]: L.append(f"- ➕ 추가 **{x['name']}** {money(x['value'])} ({x['pct']:+.0f}%)")
            rest = max(0, len(h["new"]) - 10) + max(0, len(h["added"]) - 10)
            if rest: L.append(f"- … 외 {rest}건")
        L += [f"[원문]({h['url']}) · {h['at']}", ""]

    moves = [(g, d) for g, d in delta.items() if d["in"] or d["out"]]
    if moves:
        L += [f"## 🔄 TOP {TOP_N} 변동", ""]
        for g, d in moves:
            if d["in"]: L.append(f"- {g} 진입: {', '.join(d['in'])}")
            if d["out"]: L.append(f"- {g} 이탈: {', '.join(d['out'])}")
        L.append("")

    for rows, gl in ((inst, "기관"), (ppl, "유명인")):
        L += [f"## {gl} TOP {TOP_N}", "", "| # | 이름 | 1년 | 최신 13F | 상위 보유 |", "|---|---|---|---|---|"]
        for r in rows[:TOP_N]:
            L.append(f"| {r['rank']} | {r['name']} | **{r['ret_1y']:+.1f}%** | {r['period']} | {', '.join(r['top'])} |")
        L.append("")

    L += ["---", "",
          f"**수익률 읽는 법.** 13F로 공시된 미국 상장 롱 포지션 상위 {TOP_HOLDINGS}개를 "
          "공시일에 가치비중대로 복제했다고 가정한 값입니다. 실제 펀드 수익률이 아닙니다 — "
          "공매도·해외주식·채권·현금·수수료가 모두 빠져 있습니다. 보유 종목이 수천 개인 "
          "퀀트 펀드일수록 실제와 크게 다릅니다.", "",
          "**시차.** Form 4는 거래 후 2영업일, 13D는 5영업일, 13F는 분기말 후 45일. "
          "여기 뜨는 13F 편입은 이미 최대 4개월 전의 매매입니다.", "",
          "투자 자문이 아닙니다."]
    return "\n".join(L)


def rank_delta(inst, ppl):
    prev = jload(DATA / "prev.json", {}) or {}
    out = {}
    for rows, gl, key in ((inst, "기관", "inst"), (ppl, "유명인", "ppl")):
        cur = {r["name"] for r in rows[:TOP_N]}
        old = set(prev.get(key, []))
        out[gl] = {"in": sorted(cur - old) if old else [], "out": sorted(old - cur) if old else []}
    jsave(DATA / "prev.json", {"inst": [r["name"] for r in inst[:TOP_N]],
                               "ppl": [r["name"] for r in ppl[:TOP_N]]})
    return out


# ════════════════════════════════════════════════════════ 텔레그램
TG_LIMIT = 3900          # 텔레그램 한 메시지 최대 4096자. 여유를 둔다.


def tg_api(token, method, **kw):
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=30, **kw)
        j = r.json()
        if not j.get("ok"):
            log(f"  텔레그램 {method} 실패: {j.get('description')}")
        return j
    except requests.RequestException as e:
        log(f"  텔레그램 {method} 오류: {e}")
        return {"ok": False}


def find_chat_id(token):
    """CHAT_ID를 안 넣었으면, 봇에게 온 최근 메시지에서 자동으로 찾는다."""
    j = tg_api(token, "getUpdates", json={"limit": 10})
    for u in reversed(j.get("result", [])):
        msg = u.get("message") or u.get("channel_post") or {}
        cid = (msg.get("chat") or {}).get("id")
        if cid:
            log(f"  CHAT_ID 자동 감지: {cid}  (시크릿에 넣어두면 더 안정적입니다)")
            return str(cid)
    return ""


def tg_escape(s):
    """텔레그램 HTML 모드용 최소 이스케이프."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def summary_text(inst, ppl, hits, delta, today):
    """채팅창에 바로 보이는 요약. 자세한 내용은 첨부 파일로 간다."""
    L = [f"🐋 <b>고래 40 · {today}</b>", ""]
    if not hits:
        L.append("최근 24시간 새 공시 없음.")
    else:
        buys = [h for h in hits if h["kind"] == "FORM4"]
        stakes = [h for h in hits if h["kind"] == "STAKE"]
        f13 = [h for h in hits if h["kind"] == "13F"]
        L.append(f"새 공시 <b>{len(hits)}건</b> "
                 f"(매수 {len(buys)} · 지분 {len(stakes)} · 13F {len(f13)})")
        L.append("")
        for h in buys[:6]:
            tot = sum(b["shares"] for b in h["buys"])
            px_ = h["buys"][0]["price"]
            L.append(f"🟢 <b>{tg_escape(h['name'])}</b> → {tg_escape(h['issuer'])} "
                     f"({tg_escape(h['ticker'])})\n   {tot:,.0f}주 @ ${px_:,.2f}")
        for h in stakes[:6]:
            L.append(f"🔵 <b>{tg_escape(h['name'])}</b> {tg_escape(h['form'])} → "
                     f"{tg_escape(h['issuer'] or '원문 확인')}"
                     + (f" ({tg_escape(h['pct'])})" if h["pct"] else ""))
        for h in f13[:6]:
            names = [x["name"] for x in h["new"][:4]]
            L.append(f"🟣 <b>{tg_escape(h['name'])}</b> 13F {h['period']}\n"
                     f"   신규 {len(h['new'])} · 추가 {len(h['added'])}"
                     + (f"\n   {tg_escape(', '.join(names))}" if names else ""))
        rest = len(hits) - len(buys[:6]) - len(stakes[:6]) - len(f13[:6])
        if rest > 0:
            L.append(f"\n… 외 {rest}건 (첨부 파일 참고)")

    moves = [(g, d) for g, d in delta.items() if d["in"] or d["out"]]
    if moves:
        L.append("")
        L.append("🔄 <b>TOP 20 변동</b>")
        for g, d in moves:
            if d["in"]:
                L.append(f"  {g} 진입: {tg_escape(', '.join(d['in'][:5]))}")
            if d["out"]:
                L.append(f"  {g} 이탈: {tg_escape(', '.join(d['out'][:5]))}")

    for rows, gl in ((inst, "기관"), (ppl, "유명인")):
        if not rows:
            continue
        L.append("")
        L.append(f"🏆 <b>{gl} TOP 5</b> (1년)")
        for r in rows[:5]:
            L.append(f"  {r['rank']}. {tg_escape(r['name'])}  <b>{r['ret_1y']:+.1f}%</b>")

    L.append("")
    L.append("<i>13F 롱 포지션 복제 기준 추정치. 실제 펀드 수익률이 아니며 투자 자문이 아닙니다.</i>")
    return "\n".join(L)


def send_telegram(inst, ppl, hits, delta, md_path, today):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        return
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or find_chat_id(token)
    if not chat:
        log("텔레그램: CHAT_ID를 찾지 못했습니다. 봇에게 아무 메시지나 한 번 보낸 뒤 다시 실행하세요.")
        return

    text = summary_text(inst, ppl, hits, delta, today)
    for i in range(0, len(text), TG_LIMIT):
        chunk = text[i:i + TG_LIMIT]
        tg_api(token, "sendMessage", json={"chat_id": chat, "text": chunk,
                                           "parse_mode": "HTML",
                                           "disable_web_page_preview": True})
        time.sleep(0.4)

    try:  # 전체 리포트는 파일로 첨부
        with open(md_path, "rb") as fh:
            tg_api(token, "sendDocument",
                   data={"chat_id": chat, "caption": f"전체 리포트 {today}"},
                   files={"document": (f"whale40-{today}.md", fh, "text/markdown")})
    except OSError as e:
        log(f"  첨부 실패: {e}")
    log("텔레그램 전송 완료")


# ════════════════════════════════════════════════════════ 실행
def main():
    inst = rank_group([(n, n) for n in INSTITUTIONS], "기관")
    ppl = rank_group(PEOPLE, "유명인")
    if not inst and not ppl:
        sys.exit("랭킹을 만들지 못했습니다. data/cik_map.json 을 확인하세요.")

    log(f"\n[기관 TOP 10]")
    for r in inst[:10]: log(f"  {r['rank']:>2}. {r['name'][:34]:<34} {r['ret_1y']:>8.2f}%")
    log(f"[유명인 TOP 10]")
    for r in ppl[:10]: log(f"  {r['rank']:>2}. {r['name'][:34]:<34} {r['ret_1y']:>8.2f}%")

    watch = ([{"group": "기관", **r} for r in inst[:TOP_N]] +
             [{"group": "유명인", **r} for r in ppl[:TOP_N]])
    log(f"\n감시 대상 {len(watch)}곳 · 최근 {ALERT_HOURS}시간 스캔")
    hits = scan(watch)
    delta = rank_delta(inst, ppl)
    md = render(inst, ppl, hits, delta)

    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    (REPORT / f"{today}.md").write_text(md, encoding="utf-8")
    (REPORT / "latest.md").write_text(md, encoding="utf-8")
    jsave(DATA / "ranking.json", {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "institutions": inst, "people": ppl})
    print(md)
    log(f"\n완료 — 이슈 {len(hits)}건 → report/{today}.md")

    send_telegram(inst, ppl, hits, delta, REPORT / f"{today}.md", today)


if __name__ == "__main__":
    main()
