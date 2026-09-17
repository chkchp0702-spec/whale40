#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whale40.py — 고래 40 트래커 (13f.info + Yahoo Finance 판)

SEC가 GitHub 서버 IP를 차단하므로, SEC를 직접 부르지 않는다.
  보유 종목 : 13f.info  (13F를 정리해 제공, 티커까지 포함)
  주가      : Yahoo Finance
둘 다 GitHub Actions에서 접속 가능함을 사전 테스트로 확인했다.

하는 일
  1. 후보 펀드들의 최근 13F 보유 내역을 모은다.
  2. 상위 N종목을 공시일에 가치비중대로 복제했다고 보고 1년 수익률을 계산한다.
  3. 기관 TOP 20 + 유명인 TOP 20 을 뽑는다. (주가가 매일 변하므로 순위도 매일 변한다)
  4. 그 40곳 중 최근 새로 올라온 13F가 있으면 신규 편입·추가 매수를 뽑아낸다.
  5. 텔레그램으로 보낸다.

실행:  python whale40.py            평소 실행
       python whale40.py --inspect  13f.info 구조 점검만 (문제 생겼을 때)
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import difflib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

# ════════════════════════════════════════════════════════ 설정
TOP_N = 20              # 그룹별 감시 인원
LOOKBACK_DAYS = 365     # 수익률 측정 기간
TOP_HOLDINGS = 20       # 복제할 상위 종목 수
MIN_QUARTERS = 3        # 최소 13F 개수
MIN_ADD_PCT = 20        # 추가 매수로 알릴 최소 증가율(%)
NEW_FILING_DAYS = 2     # 며칠 이내 공시를 "새 것"으로 볼지

# 감시 후보 — 13f.info에 있는 이름으로 적습니다. 자유롭게 지우고 추가하세요.
INSTITUTIONS = [
    "Citadel Advisors", "Millennium Management", "D. E. Shaw", "Two Sigma Investments",
    "AQR Capital Management", "Renaissance Technologies", "Point72 Asset Management",
    "Balyasny Asset Management", "Marshall Wace", "Schonfeld Strategic Advisors",
    "Bridgewater Associates", "Coatue Management", "Lone Pine Capital",
    "Light Street Capital", "Whale Rock Capital Management", "Viking Global Investors",
    "Tiger Global Management", "D1 Capital Partners", "Alyeska Investment Group",
    "Farallon Capital Management", "Davidson Kempner Capital Management",
    "Magnetar Financial", "Pentwater Capital Management", "Baillie Gifford",
    "Dodge & Cox", "Boston Partners", "WCM Investment Management",
    "Sands Capital Management", "Polen Capital Management", "Durable Capital Partners",
    "Egerton Capital", "AKO Capital", "Cantillon Capital Management",
    "Samlyn Capital", "Steadfast Capital Management", "Maverick Capital",
    "Eminence Capital", "Glenview Capital Management", "Luxor Capital Group",
    "Baker Bros. Advisors", "RA Capital Management", "Perceptive Advisors",
    "OrbiMed Advisors", "Avoro Capital Advisors", "Deep Track Capital",
    "EcoR1 Capital", "Cormorant Asset Management", "Rock Springs Capital Management",
    "Redmile Group", "Vivo Capital", "BVF", "Tudor Investment",
    "Moore Capital Management", "Caxton Associates", "HBK Investments",
    "Whitebox Advisors", "Empyrean Capital Partners", "Sculptor Capital",
    "Gotham Asset Management", "Harris Associates", "First Eagle Investment Management",
    "Fundsmith", "Ruane, Cunniff & Goldfarb", "Tweedy, Browne",
    "Southeastern Asset Management", "Ariel Investments", "Horizon Kinetics",
    "Generation Investment Management", "Altimeter Capital Management",
    "Dragoneer Investment Group", "Slate Path Capital", "Valley Forge Capital Management",
    "Valiant Capital Management", "Discovery Capital Management",
    "Lakewood Capital Management", "Gates Capital Management",
    "CAS Investment Partners", "Abdiel Capital Advisors", "Bridger Management",
    "Temasek Holdings", "Oasis Management", "Ancora Advisors",
    "Coliseum Capital Management", "Fisher Asset Management", "Markel Group",
]

# (표시 이름, 13f.info 검색어)
PEOPLE = [
    ("워런 버핏", "Berkshire Hathaway"),
    ("빌 애크먼", "Pershing Square Capital Management"),
    ("스탠리 드러켄밀러", "Duquesne Family Office"),
    ("데이비드 테퍼", "Appaloosa"),
    ("칼 아이칸", "Icahn Capital"),
    ("폴 싱어", "Elliott Investment Management"),
    ("댄 러브", "Third Point"),
    ("세스 클라만", "Baupost Group"),
    ("하워드 막스", "Oaktree Capital Management"),
    ("조지 소로스", "Soros Fund Management"),
    ("넬슨 펠츠", "Trian Fund Management"),
    ("제프 스미스", "Starboard Value"),
    ("메이슨 모핏", "ValueAct Capital"),
    ("스콧 퍼거슨", "Sachem Head Capital Management"),
    ("키스 마이스터", "Corvex Management"),
    ("배리 로젠스타인", "JANA Partners"),
    ("글렌 웰링", "Engaged Capital"),
    ("퀜틴 코피", "Politan Capital Management"),
    ("폴 힐랄", "Mantle Ridge"),
    ("알렉스 데너", "Sarissa Capital Management"),
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
    ("글렌 그린버그", "Brave Warrior Advisors"),
    ("톰 게이너", "Markel Group"),
    ("프렘 왓사", "Fairfax Financial Holdings"),
    ("브루스 버코위츠", "Fairholme Capital Management"),
    ("빌 밀러", "Miller Value Partners"),
    ("리언 쿠퍼먼", "Cooperman Leon"),
    ("마이클 버리", "Scion Asset Management"),
    ("프랑수아 로숑", "Giverny Capital"),
    ("크리스 블룸스트란", "Semper Augustus Investments"),
    ("팻 도시", "Dorsey Asset Management"),
    ("노버트 로우", "Punch Card Management"),
    ("클리퍼드 소신", "CAS Investment Partners"),
    ("브래드 거스트너", "Altimeter Capital Management"),
    ("데이비드 아인혼", "Greenlight Capital"),
    ("머리 스탈", "Horizon Kinetics"),
    ("앨 고어", "Generation Investment Management"),
    ("세스 필딩", "Foxhaven Asset Management"),
    ("리 에인슬리", "Maverick Capital"),
    ("존 오버덱", "Two Sigma Investments"),
]

# ════════════════════════════════════════════════════════ 기반
ROOT = Path(__file__).resolve().parent
DATA, CACHE, REPORT = ROOT / "data", ROOT / "data" / "cache", ROOT / "report"
for p in (DATA, CACHE / "13f", CACHE / "px", REPORT):
    p.mkdir(parents=True, exist_ok=True)

BASE = "https://13f.info"
S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url, tries=3, sleep=0.7, quiet=False, **kw):
    last = ""
    for i in range(tries):
        try:
            r = S.get(url, timeout=45, **kw)
            time.sleep(sleep)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (429, 503):
                time.sleep(5 * (i + 1))
                continue
            break
        except requests.RequestException as e:
            last = f"{type(e).__name__}"
            time.sleep(2 + i)
    if not quiet:
        log(f"  ! 요청 실패 {url} → {last}")
    return None


def jload(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def jsave(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def num(s):
    """'1,234,567' → 1234567.0 / 빈 값은 0"""
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(s)) or 0)
    except ValueError:
        return 0.0


# ═══════════════════════════════════════════ 펀드 이름 → 13f.info 주소
MGR_INDEX = DATA / "managers.json"


def manager_index() -> dict[str, str]:
    """13f.info의 알파벳별 매니저 목록에서 {정규화이름: 경로} 색인을 만든다.
    26쪽이라 첫 실행에만 오래 걸리고, 이후에는 파일에서 읽는다."""
    idx = jload(MGR_INDEX)
    if idx:
        return idx
    idx = {}
    log("13f.info 매니저 목록 수집 중 (26쪽, 최초 1회)…")
    for ch in "abcdefghijklmnopqrstuvwxyz":
        r = get(f"{BASE}/managers/{ch}", quiet=True)
        if not r:
            continue
        # <a href="/manager/0001067983-berkshire-hathaway-inc">Berkshire Hathaway Inc</a>
        for path, name in re.findall(r'href="(/manager/[^"]+)"[^>]*>([^<]{2,120})</a>', r.text):
            idx.setdefault(norm(html.unescape(name)), path)
        log(f"  {ch}: 누적 {len(idx):,}곳")
    jsave(MGR_INDEX, idx)
    return idx


def find_manager(query: str) -> tuple[str, str] | None:
    """검색어에 가장 잘 맞는 매니저 (표시명, 경로). 완전일치 > 접두 > 포함 > 유사도."""
    idx = manager_index()
    if not idx:
        return None
    q = norm(query)
    if q in idx:
        return query, idx[q]
    pref = [(k, v) for k, v in idx.items() if k.startswith(q)]
    if pref:
        k, v = min(pref, key=lambda kv: len(kv[0]))
        return k, v
    cont = [(k, v) for k, v in idx.items() if q in k]
    if cont:
        k, v = min(cont, key=lambda kv: len(kv[0]))
        return k, v
    best, score = None, 0.0
    for k, v in idx.items():
        if abs(len(k) - len(q)) > 14:
            continue
        s = difflib.SequenceMatcher(None, q, k).ratio()
        if s > score:
            best, score = (k, v), s
    return best if score >= 0.82 else None


# ═══════════════════════════════════════════════ 13F 보유 내역 가져오기
def manager_quarters(path: str, limit: int = 6) -> list[dict]:
    """매니저 페이지에서 최근 분기 목록. [{id, quarter, filed}] 최신순."""
    r = get(BASE + path)
    if not r:
        return []
    out, seen = [], set()
    # 표의 각 행: <a href="/13f/000123-xxx">Q2 2026</a> ... 2026-08-14
    for m in re.finditer(r'href="/13f/([^"#?]+)"[^>]*>\s*([^<]{2,40}?)\s*</a>(.{0,400}?)</tr>',
                         r.text, re.S):
        fid, label, tail = m.group(1), html.unescape(m.group(2)).strip(), m.group(3)
        if fid in seen:
            continue
        seen.add(fid)
        d = re.search(r"(20\d\d-\d\d-\d\d)", tail)
        out.append({"id": fid, "quarter": label, "filed": d.group(1) if d else ""})
        if len(out) >= limit:
            break
    return out


def quarter_end(label: str) -> str:
    """'Q2 2026' → '2026-06-30'"""
    m = re.search(r"Q([1-4])\s*(20\d\d)", label or "")
    if not m:
        return ""
    q, y = int(m.group(1)), int(m.group(2))
    return {1: f"{y}-03-31", 2: f"{y}-06-30", 3: f"{y}-09-30", 4: f"{y}-12-31"}[q]


def holdings(fid: str) -> list[dict]:
    """한 분기의 보유 내역. [{sym, issuer, value, shares}]  value 단위는 천 달러."""
    c = CACHE / "13f" / f"{fid}.json"
    hit = jload(c)
    if hit is not None:
        return hit

    # 표 머리글을 먼저 읽어 열 순서를 파악한다 (사이트가 바뀌어도 따라간다)
    page = get(f"{BASE}/13f/{fid}")
    cols = []
    if page:
        thead = re.search(r"<thead.*?</thead>", page.text, re.S)
        if thead:
            cols = [re.sub(r"<[^>]+>", "", h).strip().lower()
                    for h in re.findall(r"<th[^>]*>(.*?)</th>", thead.group(0), re.S)]

    rows = []
    d = get(f"{BASE}/data/13f/{fid}", quiet=True)      # 표를 채우는 JSON
    if d:
        try:
            rows = d.json().get("data", [])
        except ValueError:
            rows = []
    if not rows and page:                              # 예비: HTML 표 직접 파싱
        body = re.search(r"<tbody.*?</tbody>", page.text, re.S)
        if body:
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(0), re.S):
                cells = [html.unescape(re.sub(r"<[^>]+>", "", td)).strip()
                         for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                if cells:
                    rows.append(cells)

    def col(name_options, default=None):
        for i, c_ in enumerate(cols):
            if any(o in c_ for o in name_options):
                return i
        return default

    i_sym = col(["sym", "ticker"], 0)
    i_iss = col(["issuer", "name", "company"], 1)
    i_val = col(["value"], 4)
    i_sh = col(["shares", "principal", "amount"], 6)

    out = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) <= max(i_sym, i_iss, i_val, i_sh):
            continue
        sym = html.unescape(re.sub(r"<[^>]+>", "", str(row[i_sym]))).strip().upper()
        if not sym or not re.fullmatch(r"[A-Z][A-Z.\-]{0,7}", sym):
            continue  # 티커가 없는 줄(옵션·채권 등)은 건너뛴다
        v, sh = num(row[i_val]), num(row[i_sh])
        if v <= 0:
            continue
        h = next((x for x in out if x["sym"] == sym), None)
        if h:
            h["value"] += v
            h["shares"] += sh
        else:
            out.append({"sym": sym,
                        "issuer": html.unescape(re.sub(r"<[^>]+>", "", str(row[i_iss]))).strip(),
                        "value": v, "shares": sh})
    jsave(c, out)
    return out


# ══════════════════════════════════════════════ 주가 (Yahoo Finance)
def yahoo_prices(sym: str) -> dict[str, float]:
    f = CACHE / "px" / f"{sym}.json"
    today = date.today().isoformat()
    b = jload(f)
    if b and b.get("asof") == today:
        return b["px"]
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?range=2y&interval=1d&includeAdjustedClose=true")
    r = get(url, tries=2, sleep=0.35, quiet=True)
    px = {}
    if r:
        try:
            res = r.json()["chart"]["result"][0]
            ts = res["timestamp"]
            q = res["indicators"]
            series = (q.get("adjclose", [{}])[0].get("adjclose")
                      if q.get("adjclose") else None) or q["quote"][0]["close"]
            for t, c in zip(ts, series):
                if c is not None:
                    px[datetime.fromtimestamp(t, timezone.utc).date().isoformat()] = float(c)
        except (KeyError, IndexError, TypeError, ValueError):
            px = {}
    if not px and b:
        px = b["px"]
    jsave(f, {"asof": today, "px": px})
    return px


def px_at(px: dict, day: str):
    ks = [k for k in px if k <= day]
    return px[max(ks)] if ks else None


# ══════════════════════════════════════════════════ 수익률 계산
def snapshots(path: str) -> list[dict]:
    """[{filed, quarter, weights:{sym:w}, names:{sym:issuer}}] 공시일 오름차순."""
    qs = manager_quarters(path, 6)
    if len(qs) < MIN_QUARTERS:
        return []
    cut = (date.today() - timedelta(days=LOOKBACK_DAYS + 140)).isoformat()
    out = []
    for q in qs:
        filed = q["filed"] or quarter_end(q["quarter"])
        if not filed or filed < cut:
            continue
        hs = holdings(q["id"])
        if not hs:
            continue
        top = sorted(hs, key=lambda h: -h["value"])[:TOP_HOLDINGS]
        tot = sum(h["value"] for h in top)
        if tot <= 0:
            continue
        out.append({"filed": filed, "quarter": q["quarter"], "id": q["id"],
                    "weights": {h["sym"]: h["value"] / tot for h in top},
                    "names": {h["sym"]: h["issuer"] for h in top}})
    out.sort(key=lambda x: x["filed"])
    return out


def seg_return(weights, t0, t1, px):
    numer = wsum = 0.0
    for sym, w in weights.items():
        p = px.get(sym)
        if not p:
            continue
        a, b = px_at(p, t0), px_at(p, t1)
        if not a or not b or a <= 0:
            continue
        numer += w * (b / a - 1.0)
        wsum += w
    return None if wsum < 0.5 else numer / wsum


def year_return(snaps, px, start, end):
    """공시일마다 리밸런싱한다고 보고 구간 수익률을 연쇄 곱."""
    if not snaps:
        return None, 0.0
    prior = [s for s in snaps if s["filed"] <= start]
    active = prior[-1] if prior else snaps[0]
    cur, bounds = max(start, active["filed"]), []
    for s in [x for x in snaps if x["filed"] > cur]:
        bounds.append((active, cur, s["filed"]))
        active, cur = s, s["filed"]
    bounds.append((active, cur, end))
    cum, ok, tot = 1.0, 0, 0
    for snap, a, b in bounds:
        if a >= b:
            continue
        tot += 1
        r = seg_return(snap["weights"], a, b, px)
        if r is None:
            continue
        cum *= (1 + r)
        ok += 1
    return (None, 0.0) if not ok else (cum - 1, ok / tot)


def rank_group(entries, label):
    """entries: [(표시명, 검색어)]"""
    end = date.today()
    start = (end - timedelta(days=LOOKBACK_DAYS)).isoformat()
    end = end.isoformat()

    log(f"\n━━━ {label} {len(entries)}곳 ━━━")
    snaps_by, meta, syms = {}, {}, set()
    for disp, query in entries:
        found = find_manager(query)
        if not found:
            log(f"  ✗ {disp}: '{query}' 13f.info에 없음")
            continue
        name, path = found
        if path in snaps_by:
            continue
        s = snapshots(path)
        if not s:
            log(f"  - {disp}: 분기 자료 부족")
            continue
        snaps_by[path] = s
        meta[path] = {"name": disp, "source": name, "path": path}
        for snap in s:
            syms |= set(snap["weights"])
        log(f"  · {disp}: {len(s)}개 분기 (최신 {s[-1]['quarter']})")

    log(f"{label}: 종목 {len(syms)}개 주가 로딩")
    px = {}
    for i, sym in enumerate(sorted(syms), 1):
        px[sym] = yahoo_prices(sym)
        if i % 100 == 0:
            log(f"  주가 {i}/{len(syms)}")

    rows = []
    for path, s in snaps_by.items():
        r, cov = year_return(s, px, start, end)
        if r is None:
            log(f"  - {meta[path]['name']}: 수익률 계산 불가")
            continue
        last = s[-1]
        rows.append({**meta[path], "ret_1y": round(r * 100, 2), "coverage": round(cov, 2),
                     "quarter": last["quarter"], "filed": last["filed"], "fid": last["id"],
                     "top": [last["names"].get(k, k) for k, _ in
                             sorted(last["weights"].items(), key=lambda kv: -kv[1])[:3]]})
    rows.sort(key=lambda x: -x["ret_1y"])
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


# ══════════════════════════════════════════════ 새 공시 감시
def recent_moves(watch):
    """감시 대상 중 최근 며칠 안에 새 13F가 올라온 곳의 신규 편입·추가 매수."""
    cutoff = (date.today() - timedelta(days=NEW_FILING_DAYS)).isoformat()
    seen = set(jload(DATA / "seen.json", []) or [])
    hits, fresh = [], []
    for w in watch:
        if w["filed"] < cutoff or w["fid"] in seen:
            continue
        fresh.append(w["fid"])
        qs = manager_quarters(w["path"], 3)
        prev = next((q for q in qs if q["id"] != w["fid"]), None)
        curr_h = {h["sym"]: h for h in holdings(w["fid"])}
        prev_h = {h["sym"]: h for h in holdings(prev["id"])} if prev else {}
        new, add = [], []
        for sym, h in curr_h.items():
            p = prev_h.get(sym)
            if not p or p["shares"] <= 0:
                new.append(h)
            elif h["shares"] > p["shares"]:
                pct = (h["shares"] / p["shares"] - 1) * 100
                if pct >= MIN_ADD_PCT:
                    add.append({**h, "pct": pct})
        if new or add:
            k = lambda x: -x["value"]
            hits.append({**w, "new": sorted(new, key=k), "added": sorted(add, key=k),
                         "n": len(curr_h), "baseline": bool(prev_h)})
            log(f"  [새 13F] {w['name']} {w['quarter']} 신규 {len(new)} 추가 {len(add)}")
    jsave(DATA / "seen.json", sorted(set(list(seen) + fresh))[-5000:])
    hits.sort(key=lambda h: h["rank"])
    return hits


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


# ════════════════════════════════════════════════════════ 리포트
def money(v):
    """13f.info 금액 단위는 천 달러."""
    d = v * 1000
    return f"${d/1e9:,.2f}B" if d >= 1e9 else (f"${d/1e6:,.1f}M" if d >= 1e6 else f"${d:,.0f}")


def render(inst, ppl, hits, delta):
    today = date.today().isoformat()
    L = [f"# 고래 40 · {today}", "",
         f"1년 수익률 기준 기관 TOP {TOP_N} + 유명인 TOP {TOP_N}", ""]

    L += ["## 🔔 새로 올라온 13F", ""]
    if not hits:
        L += ["최근 새 공시 없음. 13F는 분기마다(2·5·8·11월 중순) 몰려서 올라옵니다.", ""]
    for h in hits:
        L.append(f"### {h['name']} `{h['group']} {h['rank']}위 · 1Y {h['ret_1y']:+.1f}%`")
        L.append(f"{h['quarter']} · {h['n']}종목 · 공시 {h['filed']}")
        if not h["baseline"]:
            L.append("- _직전 분기 자료 없음 → 전량 신규로 표시_")
        for x in h["new"][:12]:
            L.append(f"- ✨ 신규 **{x['sym']}** {x['issuer']} · {x['shares']:,.0f}주 · {money(x['value'])}")
        for x in h["added"][:12]:
            L.append(f"- ➕ 추가 **{x['sym']}** {x['issuer']} · {money(x['value'])} ({x['pct']:+.0f}%)")
        rest = max(0, len(h["new"]) - 12) + max(0, len(h["added"]) - 12)
        if rest:
            L.append(f"- … 외 {rest}건")
        L += [f"[원문](https://13f.info/13f/{h['fid']})", ""]

    moves = [(g, d) for g, d in delta.items() if d["in"] or d["out"]]
    if moves:
        L += [f"## 🔄 TOP {TOP_N} 변동", ""]
        for g, d in moves:
            if d["in"]:
                L.append(f"- {g} 진입: {', '.join(d['in'])}")
            if d["out"]:
                L.append(f"- {g} 이탈: {', '.join(d['out'])}")
        L.append("")

    for rows, gl in ((inst, "기관"), (ppl, "유명인")):
        L += [f"## {gl} TOP {TOP_N}", "", "| # | 이름 | 1년 | 최신 | 상위 보유 |", "|---|---|---|---|---|"]
        for r in rows[:TOP_N]:
            L.append(f"| {r['rank']} | {r['name']} | **{r['ret_1y']:+.1f}%** | "
                     f"{r['quarter']} | {', '.join(r['top'])} |")
        L.append("")

    L += ["---", "",
          f"**수익률 읽는 법.** 13F로 공시된 미국 상장 보유 상위 {TOP_HOLDINGS}종목을 "
          "공시일에 가치비중대로 복제했다고 가정한 값입니다. 실제 펀드 수익률이 아닙니다 — "
          "공매도·해외주식·채권·현금·수수료가 모두 빠져 있습니다.", "",
          "**시차.** 13F는 분기말 후 45일에 공개됩니다. 여기 뜨는 편입은 최대 4개월 전의 매매입니다.", "",
          "출처: 13f.info · Yahoo Finance. 투자 자문이 아닙니다."]
    return "\n".join(L)


# ════════════════════════════════════════════════════════ 텔레그램
TG_LIMIT = 3900


def tg(token, method, **kw):
    try:
        j = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=30, **kw).json()
        if not j.get("ok"):
            log(f"  텔레그램 {method}: {j.get('description')}")
        return j
    except requests.RequestException as e:
        log(f"  텔레그램 {method} 오류: {e}")
        return {"ok": False}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def summary(inst, ppl, hits, delta):
    L = [f"🐋 <b>고래 40 · {date.today().isoformat()}</b>", ""]
    if hits:
        L.append(f"새 13F <b>{len(hits)}건</b>")
        L.append("")
        for h in hits[:6]:
            names = ", ".join(x["sym"] for x in h["new"][:5])
            L.append(f"🟣 <b>{esc(h['name'])}</b> {esc(h['quarter'])}")
            L.append(f"   신규 {len(h['new'])} · 추가 {len(h['added'])}"
                     + (f"\n   {esc(names)}" if names else ""))
        if len(hits) > 6:
            L.append(f"\n… 외 {len(hits)-6}건")
    else:
        L.append("새 13F 없음.")

    moves = [(g, d) for g, d in delta.items() if d["in"] or d["out"]]
    if moves:
        L += ["", "🔄 <b>TOP 20 변동</b>"]
        for g, d in moves:
            if d["in"]:
                L.append(f"  {g} 진입: {esc(', '.join(d['in'][:5]))}")
            if d["out"]:
                L.append(f"  {g} 이탈: {esc(', '.join(d['out'][:5]))}")

    for rows, gl in ((inst, "기관"), (ppl, "유명인")):
        if not rows:
            continue
        L += ["", f"🏆 <b>{gl} TOP 5</b> (1년)"]
        for r in rows[:5]:
            L.append(f"  {r['rank']}. {esc(r['name'])}  <b>{r['ret_1y']:+.1f}%</b>")

    L += ["", "<i>13F 보유 복제 기준 추정치. 실제 펀드 수익률이 아니며 투자 자문이 아닙니다.</i>"]
    return "\n".join(L)


def send_telegram(text, md_path):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        log("텔레그램 설정 없음 — 전송 생략")
        return
    for i in range(0, len(text), TG_LIMIT):
        tg(token, "sendMessage", json={"chat_id": chat, "text": text[i:i + TG_LIMIT],
                                       "parse_mode": "HTML", "disable_web_page_preview": True})
        time.sleep(0.4)
    try:
        with open(md_path, "rb") as fh:
            tg(token, "sendDocument",
               data={"chat_id": chat, "caption": f"전체 리포트 {date.today().isoformat()}"},
               files={"document": (f"whale40-{date.today().isoformat()}.md", fh, "text/markdown")})
    except OSError as e:
        log(f"  첨부 실패: {e}")
    log("텔레그램 전송 완료")


# ════════════════════════════════════════════════════════ 점검 모드
def inspect():
    log("=== 13f.info 구조 점검 ===")
    r = get(f"{BASE}/managers/b")
    log(f"  매니저 목록 페이지: {'OK' if r else '실패'}")
    if r:
        links = re.findall(r'href="(/manager/[^"]+)"[^>]*>([^<]{2,120})</a>', r.text)
        log(f"  추출된 매니저 링크 {len(links)}개")
        for p, n in links[:3]:
            log(f"    {n.strip()}  →  {p}")
    f = find_manager("Berkshire Hathaway")
    log(f"  'Berkshire Hathaway' 매칭: {f}")
    if f:
        qs = manager_quarters(f[1], 3)
        log(f"  분기 {len(qs)}개: {[(q['quarter'], q['filed']) for q in qs]}")
        if qs:
            hs = holdings(qs[0]["id"])
            log(f"  최신 분기 보유 {len(hs)}종목")
            for h in hs[:5]:
                log(f"    {h['sym']:6} {h['issuer'][:28]:28} {h['value']:>14,.0f}천$ {h['shares']:>14,.0f}주")
    px = yahoo_prices("AAPL")
    log(f"  AAPL 주가 {len(px)}일치  최근: {sorted(px)[-1] if px else '없음'}")


# ════════════════════════════════════════════════════════ 실행
def main():
    if "--inspect" in sys.argv:
        inspect()
        return

    inst = rank_group([(n, n) for n in INSTITUTIONS], "기관")
    ppl = rank_group(PEOPLE, "유명인")
    log(f"\n집계: 기관 {len(inst)}/{len(INSTITUTIONS)}곳, 유명인 {len(ppl)}/{len(PEOPLE)}명")
    if not inst and not ppl:
        sys.exit("랭킹을 만들지 못했습니다. `python whale40.py --inspect` 로 구조를 확인하세요.")

    for rows, gl in ((inst, "기관"), (ppl, "유명인")):
        log(f"\n[{gl} TOP 10]")
        for r in rows[:10]:
            log(f"  {r['rank']:>2}. {r['name'][:32]:<32} {r['ret_1y']:>8.2f}%")

    watch = ([{"group": "기관", **r} for r in inst[:TOP_N]] +
             [{"group": "유명인", **r} for r in ppl[:TOP_N]])
    log(f"\n감시 대상 {len(watch)}곳 · 새 13F 확인")
    hits = recent_moves(watch)
    delta = rank_delta(inst, ppl)

    md = render(inst, ppl, hits, delta)
    today = date.today().isoformat()
    (REPORT / f"{today}.md").write_text(md, encoding="utf-8")
    (REPORT / "latest.md").write_text(md, encoding="utf-8")
    jsave(DATA / "ranking.json", {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "institutions": inst, "people": ppl})
    print(md)
    log(f"\n완료 — 새 13F {len(hits)}건 → report/{today}.md")
    send_telegram(summary(inst, ppl, hits, delta), REPORT / f"{today}.md")


if __name__ == "__main__":
    main()
