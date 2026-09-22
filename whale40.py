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


# ═══════════════════════════════════════ 종목 한글명 (자주 나오는 것 위주)
KR_NAME = {
 # 빅테크·반도체
 "AAPL":"애플","MSFT":"마이크로소프트","GOOGL":"알파벳 A","GOOG":"알파벳 C",
 "AMZN":"아마존","META":"메타","NVDA":"엔비디아","TSLA":"테슬라","AVGO":"브로드컴",
 "AMD":"AMD","INTC":"인텔","TSM":"TSMC","MU":"마이크론","QCOM":"퀄컴","TXN":"텍사스인스트루먼트",
 "ADI":"아나로그디바이스","LRCX":"램리서치","AMAT":"어플라이드머티리얼즈","KLAC":"KLA",
 "ASML":"ASML","ARM":"ARM","MRVL":"마벨","NXPI":"NXP","ON":"온세미","STX":"씨게이트",
 "WDC":"웨스턴디지털","SNDK":"샌디스크","ALAB":"아스테라랩스","CRDO":"크레도","NBIS":"네비우스",
 "CRWV":"코어위브","SMCI":"슈퍼마이크로","DELL":"델","HPQ":"HP","HPE":"HPE","CSCO":"시스코",
 # 소프트웨어·인터넷
 "ORCL":"오라클","CRM":"세일즈포스","ADBE":"어도비","NOW":"서비스나우","SNOW":"스노우플레이크",
 "PLTR":"팔란티어","INTU":"인튜이트","PANW":"팔로알토","CRWD":"크라우드스트라이크",
 "DDOG":"데이터독","NET":"클라우드플레어","MDB":"몽고DB","ZS":"지스케일러","WDAY":"워크데이",
 "TEAM":"아틀라시안","SHOP":"쇼피파이","SQ":"블록","PYPL":"페이팔","UBER":"우버","LYFT":"리프트",
 "ABNB":"에어비앤비","DASH":"도어대시","BKNG":"부킹홀딩스","EXPE":"익스피디아","U":"유니티",
 "RBLX":"로블록스","SPOT":"스포티파이","NFLX":"넷플릭스","DIS":"디즈니","WBD":"워너브러더스",
 "PARA":"파라마운트","CHTR":"차터","CMCSA":"컴캐스트","TTD":"트레이드데스크","APP":"앱러빈",
 "PINS":"핀터레스트","SNAP":"스냅","RDDT":"레딧","COIN":"코인베이스","HOOD":"로빈후드",
 "MSTR":"마이크로스트래티지","BABA":"알리바바","PDD":"핀둬둬","JD":"징둥","NU":"누홀딩스",
 "MELI":"메르카도리브레","SE":"씨리미티드","GRAB":"그랩","CVNA":"카바나","CARG":"카구루스",
 # 금융
 "BRK.A":"버크셔 A","BRK.B":"버크셔 B","JPM":"JP모건","BAC":"뱅크오브아메리카",
 "WFC":"웰스파고","C":"씨티그룹","GS":"골드만삭스","MS":"모건스탠리","SCHW":"찰스슈왑",
 "BLK":"블랙록","BX":"블랙스톤","KKR":"KKR","APO":"아폴로","ARES":"에어리스","COF":"캐피털원",
 "ALLY":"앨라이","AXP":"아메리칸익스프레스","V":"비자","MA":"마스터카드","FI":"파이서브",
 "GPN":"글로벌페이먼츠","SPGI":"S&P글로벌","MCO":"무디스","ICE":"ICE","CME":"CME",
 "NDAQ":"나스닥","EFX":"에퀴팩스","PGR":"프로그레시브","TRV":"트래블러스","AIG":"AIG",
 "MET":"메트라이프","PRU":"푸르덴셜","OZK":"뱅크OZK","FFH":"페어팩스",
 # 헬스케어·바이오
 "LLY":"일라이릴리","UNH":"유나이티드헬스","JNJ":"존슨앤드존슨","ABBV":"애브비","MRK":"머크",
 "PFE":"화이자","BMY":"BMS","AMGN":"암젠","GILD":"길리어드","VRTX":"버텍스","REGN":"리제네론",
 "BIIB":"바이오젠","MRNA":"모더나","TMO":"써모피셔","DHR":"다나허","ABT":"애보트","BDX":"벡톤디킨슨",
 "SYK":"스트라이커","BSX":"보스턴사이언티픽","MDT":"메드트로닉","ISRG":"인튜이티브서지컬",
 "ZTS":"조에티스","CVS":"CVS","CI":"시그나","ELV":"엘리번스","HUM":"휴매나","MCK":"맥케슨",
 "DVA":"다비타","THC":"테닛헬스케어","ILMN":"일루미나","NTRA":"나테라","GH":"가던트헬스",
 "INSM":"인스메드","MDGL":"마드리갈","RVMD":"레볼루션메디슨","INCY":"인사이트","ASND":"아센디스",
 "UTHR":"유나이티드테라퓨틱스","KRYS":"크리스탈바이오텍","SRRK":"스칼라록","STOK":"스토크",
 "KYMR":"카이메라","IMVT":"이뮤노반트","GPCR":"스트럭처테라퓨틱스","EWTX":"엣지와이즈",
 "RYTM":"리듬","TVTX":"트래비어","CELC":"셀큐이티","PRAX":"프락시스","SPYR":"스파이어",
 "ZYME":"자임웍스","ANAB":"아냅티스바이오","ERAS":"에라스카","TRVI":"트레비","XOMA":"조마",
 "INVA":"이노비바","IRWD":"아이언우드","AMRN":"아마린","GDRX":"굿알엑스","WGS":"진디엑스",
 # 에너지·소재·산업
 "XOM":"엑슨모빌","CVX":"셰브론","COP":"코노코필립스","OXY":"옥시덴탈","PSX":"필립스66",
 "VLO":"발레로","MPC":"마라톤페트롤리엄","SLB":"슐럼버거","HAL":"핼리버튼","DVN":"데본에너지",
 "FANG":"다이아몬드백","EOG":"EOG","RIG":"트랜스오션","NBR":"네이버스","HCC":"워리어멧콜",
 "AMR":"알파메탈러지컬","BTU":"피바디","FCX":"프리포트","NEM":"뉴몬트","GOLD":"배릭골드",
 "AEM":"애그니코이글","EGO":"엘도라도골드","ORLA":"오를라마이닝","TFPM":"트리플플래그",
 "LIN":"린데","APD":"에어프로덕츠","SHW":"셔윈윌리엄스","CAT":"캐터필러","DE":"디어",
 "GE":"GE","HON":"하니웰","RTX":"RTX","LMT":"록히드마틴","BA":"보잉","UNP":"유니온퍼시픽",
 "CSX":"CSX","NSC":"노퍽서던","UPS":"UPS","FDX":"페덱스","DAL":"델타항공","UAL":"유나이티드항공",
 "LUV":"사우스웨스트","AAL":"아메리칸항공","ALK":"알래스카항공","VSTS":"베스티스",
 # 소비재·유통·기타
 "WMT":"월마트","COST":"코스트코","TGT":"타겟","HD":"홈디포","LOW":"로우스","KR":"크로거",
 "DG":"달러제너럴","DLTR":"달러트리","M":"메이시스","TJX":"TJX","NKE":"나이키","SBUX":"스타벅스",
 "MCD":"맥도날드","CMG":"치폴레","DPZ":"도미노피자","YUM":"염브랜즈","KO":"코카콜라",
 "PEP":"펩시코","KDP":"큐리그닥터페퍼","MNST":"몬스터","STZ":"콘스텔레이션","KHC":"크래프트하인즈",
 "MDLZ":"몬델리즈","GIS":"제너럴밀스","PG":"프록터앤드갬블","CL":"콜게이트","KMB":"킴벌리클라크",
 "PM":"필립모리스","MO":"알트리아","EL":"에스티로더","LULU":"룰루레몬","ROST":"로스스토어",
 "ORLY":"오라일리","AZO":"오토존","POOL":"풀코퍼레이션","LEN":"레나","DHI":"DR호튼",
 "PHM":"풀티그룹","LPX":"루이지애나퍼시픽","JOE":"세인트조","CBRE":"CBRE","AMT":"아메리칸타워",
 "PLD":"프로로지스","NYT":"뉴욕타임스","GTN":"그레이미디어","SIRI":"시리우스XM","VRSN":"베리사인",
 "LILA":"리버티라틴아메리카","BATRK":"애틀랜타브레이브스","AON":"에이온","JEF":"제프리스",
 "HEI":"하이코","WEC":"WEC에너지","NEE":"넥스트에라","DUK":"듀크에너지","SO":"서던컴퍼니",
 "T":"AT&T","VZ":"버라이즌","TMUS":"T모바일","EPD":"엔터프라이즈프로덕츠","CORZ":"코어사이언티픽",
 # ETF
 "SPY":"S&P500 ETF","QQQ":"나스닥100 ETF","IWM":"러셀2000 ETF","VOO":"뱅가드S&P500",
 "VTI":"뱅가드전체시장","IVV":"iShares S&P500","GLD":"금 ETF","SLV":"은 ETF",
 "TLT":"미국장기국채","HYG":"하이일드채권","EEM":"신흥국 ETF","XLF":"금융 ETF",
 "XLE":"에너지 ETF","XLK":"기술 ETF","XBI":"바이오 ETF","SMH":"반도체 ETF","ARKK":"ARK혁신",
}


def stock_label(sym: str, issuer: str = "") -> str:
    """'AAPL 애플' / 한글명이 없으면 'XYZ 이슈어명'"""
    kr = KR_NAME.get(sym)
    if kr:
        return f"{sym} {kr}"
    name = re.sub(r"\s+", " ", (issuer or "")).strip()
    name = re.sub(r"\b(INC|CORP|CORPORATION|CO|LTD|LLC|PLC|GROUP|HOLDINGS?|HLDGS?|"
                  r"COMPANY|THE|NEW|DEL|CL A|CL B|COM|A/S|SA|NV|TR|TRUST)\b\.?", "", name,
                  flags=re.I).strip(" ,.-")
    name = " ".join(w.capitalize() if w.isupper() and len(w) > 3 else w
                    for w in name.split())[:22]
    return f"{sym} {name}".strip() if name else sym


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
def manager_quarters(path: str, limit: int = 6, debug: bool = False) -> list[dict]:
    """매니저 페이지에서 최근 분기 목록. [{id, quarter, filed}] 최신순.
    행 길이에 제한을 두지 않는다 — '상위 보유' 칸 때문에 한 행이 매우 길 수 있다."""
    r = get(BASE + path)
    if not r:
        return []
    txt = r.text
    out, seen = [], set()
    # 각 행: <a href="/13f/000123-xxx">Q2 2026</a> … <td>2026-08-14</td> … </tr>
    for m in re.finditer(r'href="(?:https?://13f\.info)?/13f/([^"#?]+)"[^>]*>(.*?)</a>(.*?)</tr>',
                         txt, re.S):
        fid = m.group(1)
        label = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        tail = m.group(3)
        if fid in seen:
            continue
        seen.add(fid)
        d = re.search(r"(20\d\d-\d\d-\d\d)", tail)
        filed = d.group(1) if d else ""
        if not re.search(r"Q[1-4]\s*20\d\d", label):
            # 링크 글자가 분기가 아니면 행 전체에서 분기 표기를 찾는다
            q = re.search(r"Q[1-4]\s*20\d\d", m.group(2) + tail)
            label = q.group(0) if q else label
        out.append({"id": fid, "quarter": label, "filed": filed or quarter_end(label)})
        if len(out) >= limit:
            break
    if debug:
        log(f"    [debug] /13f/ 링크 총 {len(re.findall(r'/13f/', txt))}개, "
            f"행 매칭 {len(out)}개, 페이지 {len(txt):,}자")
        for s in re.findall(r'<a[^>]*href="[^"]*/13f/[^"]*"[^>]*>.{0,60}', txt)[:3]:
            log(f"    [debug] {s[:150]}")
    out = [o for o in out if o["filed"]]
    out.sort(key=lambda x: x["filed"], reverse=True)
    return out[:limit]


def quarter_end(label: str) -> str:
    """'Q2 2026' → '2026-06-30'"""
    m = re.search(r"Q([1-4])\s*(20\d\d)", label or "")
    if not m:
        return ""
    q, y = int(m.group(1)), int(m.group(2))
    return {1: f"{y}-03-31", 2: f"{y}-06-30", 3: f"{y}-09-30", 4: f"{y}-12-31"}[q]


def holdings(fid: str, debug: bool = False) -> list[dict]:
    """한 분기의 보유 내역. [{sym, issuer, value, shares}]  value 단위는 천 달러."""
    cpath = CACHE / "13f" / f"{fid}.json"
    hit = jload(cpath)
    if hit is not None and not debug:
        return hit

    # (1) 표 머리글로 열 순서 파악
    page = get(f"{BASE}/13f/{fid}")
    cols = []
    if page:
        thead = re.search(r"<thead.*?</thead>", page.text, re.S)
        if thead:
            cols = [re.sub(r"<[^>]+>", "", h).strip().lower()
                    for h in re.findall(r"<th[^>]*>(.*?)</th>", thead.group(0), re.S)]
    if debug:
        log(f"    [debug] /13f/{fid} 페이지: "
            f"{'OK ' + format(len(page.text), ',') + '자' if page else '실패'}")
        log(f"    [debug] 표 머리글 {len(cols)}개: {cols}")

    # (2) 표 내용은 별도 주소에서 불러온다. 그 주소를 페이지에서 직접 찾아낸다.
    rows, tried = [], []
    cands = []
    if page:
        # <table data-url="/data/13f/xxx"> 같은 속성
        for m in re.finditer(r'data-[a-z-]*(?:url|source|src|href)\s*=\s*"([^"]+)"', page.text):
            cands.append(m.group(1))
        # 스크립트 안의 "/data/..." 또는 ".json" 경로
        for m in re.finditer(r'["\'](/[A-Za-z0-9_\-/.]*(?:data|\.json)[A-Za-z0-9_\-/.?=&]*)["\']',
                             page.text):
            cands.append(m.group(1))
    # 흔한 패턴을 예비로 추가
    cands += [f"/data/13f/{fid}", f"/13f/{fid}.json", f"/13f/{fid}/data",
              f"/data/13f/{fid}.json"]

    seen_c, ordered = set(), []
    for cand in cands:
        cand = html.unescape(cand)
        if cand in seen_c:
            continue
        seen_c.add(cand)
        if fid in cand or "13f" in cand.lower() or "data" in cand.lower():
            ordered.append(cand)
    if debug:
        log(f"    [debug] 데이터 주소 후보 {len(ordered)}개: {ordered[:6]}")

    for cand in ordered[:8]:
        url = cand if cand.startswith("http") else BASE + (cand if cand.startswith("/") else "/" + cand)
        d = get(url, quiet=True)
        tried.append(f"{cand} → {'응답' if d else '없음'}")
        if not d:
            continue
        try:
            j = d.json()
        except ValueError:
            continue
        if isinstance(j, dict):
            for key in ("data", "rows", "aaData", "results", "holdings"):
                if isinstance(j.get(key), list) and j[key]:
                    rows = j[key]
                    break
        elif isinstance(j, list):
            rows = j
        if rows:
            if debug:
                log(f"    [debug] 데이터 주소 확정: {cand}  ({len(rows)}행)")
            break
    if debug and not rows:
        for t in tried:
            log(f"    [debug] 시도 {t}")

    # (3) 예비: HTML 표 직접 파싱
    if not rows and page:
        body = re.search(r"<tbody.*?</tbody>", page.text, re.S)
        if body:
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(0), re.S):
                cells = [html.unescape(re.sub(r"<[^>]+>", "", td)).strip()
                         for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                if cells:
                    rows.append(cells)
        if debug:
            log(f"    [debug] HTML 표에서 {len(rows)}행 추출")

    if debug and rows:
        log(f"    [debug] 첫 행 원본: {rows[0]}")

    # (4) 열 위치 결정 — 머리글이 있으면 그걸로, 없으면 내용으로 추론
    def col(opts, default=None):
        for i, c_ in enumerate(cols):
            if any(o in c_ for o in opts):
                return i
        return default

    i_sym, i_iss = col(["sym", "ticker"]), col(["issuer", "name", "company"])
    i_val, i_sh = col(["value"]), col(["shares", "principal", "amount", "shrs"])
    if None in (i_sym, i_iss, i_val, i_sh) and rows:
        r0 = [str(x) for x in rows[0]]
        if i_sym is None:
            i_sym = next((i for i, v in enumerate(r0)
                          if re.fullmatch(r"[A-Z][A-Z.\-]{0,7}", re.sub(r"<[^>]+>", "", v).strip())), 0)
        if i_iss is None:
            i_iss = next((i for i, v in enumerate(r0) if i != i_sym and len(v) > 6 and
                          not re.fullmatch(r"[\d,.\s$%]+", v)), 1)
        # 13f.info는 값(Value)이 주식수(Shares)보다 앞에 온다. 큰 수 중 앞선 것을 값으로.
        # CUSIP(037833100)처럼 자릿수만 많은 식별자는 제외한다 — 금액·수량은 천단위 쉼표가 있다.
        def is_amount(v):
            s = str(v).strip()
            if re.fullmatch(r"[0-9A-Z]{9}", s):        # CUSIP 형태
                return False
            return ("," in s or "." in s) and num(s) >= 1000
        nums = [i for i, v in enumerate(r0) if is_amount(v)]
        if not nums:
            nums = [i for i, v in enumerate(r0)
                    if num(v) >= 1000 and not re.fullmatch(r"[0-9A-Z]{9}", str(v).strip())]
        if i_val is None:
            i_val = nums[0] if nums else 4
        if i_sh is None:
            after = [i for i in nums if i > i_val]
            i_sh = after[0] if after else (nums[-1] if len(nums) > 1 else 6)
        if debug:
            log(f"    [debug] 열 추론: sym={i_sym} issuer={i_iss} value={i_val} shares={i_sh}")

    out, skipped = [], 0
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) <= max(i_sym, i_iss, i_val, i_sh):
            skipped += 1
            continue
        sym = html.unescape(re.sub(r"<[^>]+>", "", str(row[i_sym]))).strip().upper()
        if not sym or not re.fullmatch(r"[A-Z][A-Z.\-]{0,7}", sym):
            skipped += 1
            continue
        v, sh = num(row[i_val]), num(row[i_sh])
        if v <= 0:
            skipped += 1
            continue
        h = next((x for x in out if x["sym"] == sym), None)
        if h:
            h["value"] += v
            h["shares"] += sh
        else:
            out.append({"sym": sym,
                        "issuer": html.unescape(re.sub(r"<[^>]+>", "", str(row[i_iss]))).strip(),
                        "value": v, "shares": sh})
    if debug:
        log(f"    [debug] 총 {len(rows)}행 중 {len(out)}종목 채택, {skipped}행 제외")
    jsave(cpath, out)
    return out


# ══════════════════════════════════════════════ 주가 (Yahoo Finance)
YF_UAS = [
    "whale40 research contact@example.com",           # 점검 때 통과했던 형태
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "python-requests/2.31",
]
YF = requests.Session()
YF.headers.update({"Accept": "application/json,text/plain,*/*"})
_yf_ua = {"i": 0}


def yahoo_raw(sym: str, ua: str):
    """(응답, 설명) — 상태코드까지 그대로 돌려준다."""
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d"
        try:
            r = YF.get(url, timeout=40, headers={"User-Agent": ua})
        except requests.RequestException as e:
            continue
        if r.status_code == 200:
            return r, f"{host} 200"
        last = f"{host} HTTP {r.status_code}"
    return None, last if 'last' in dir() else "요청 실패"


def yahoo_prices(sym: str, debug: bool = False) -> dict[str, float]:
    """주가 일별 종가. User-Agent를 바꿔가며 통과하는 것을 찾아 고정한다."""
    f = CACHE / "px" / f"{sym}.json"
    today = date.today().isoformat()
    b = jload(f)
    if b and b.get("asof") == today and not debug:
        return b["px"]

    px, notes = {}, []
    order = YF_UAS[_yf_ua["i"]:] + YF_UAS[:_yf_ua["i"]]
    for ua in order:
        r, note = yahoo_raw(sym, ua)
        notes.append(f"{ua[:18]}… → {note}")
        if not r:
            continue
        try:
            res = (r.json().get("chart") or {}).get("result") or []
            if not res:
                notes.append("result 비어 있음")
                continue
            res = res[0]
            ts = res.get("timestamp") or []
            ind = res.get("indicators") or {}
            series = None
            if ind.get("adjclose"):
                series = ind["adjclose"][0].get("adjclose")
            if not series and ind.get("quote"):
                series = ind["quote"][0].get("close")
            for t, cl in zip(ts, series or []):
                if cl is not None:
                    px[datetime.fromtimestamp(t, timezone.utc).date().isoformat()] = float(cl)
        except (ValueError, KeyError, IndexError, TypeError) as e:
            notes.append(f"해석 실패 {type(e).__name__}")
        if px:
            _yf_ua["i"] = YF_UAS.index(ua)     # 통하는 UA를 다음부터 먼저 쓴다
            break

    yahoo_prices.last_notes = notes
    if not px and b:
        px = b["px"]
    if debug:
        for n in notes:
            log(f"    [debug] {n}")
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
                     "top": [stock_label(k, last["names"].get(k, "")) for k, _ in
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




# ══════════════════════════════════════ 집단 분석 (공동 보유 · 편입/편출)
def fund_quarters(w, n=6):
    """감시 대상 한 곳의 최근 분기별 전체 보유. [(quarter, filed, {sym: h})] 최신순."""
    out = []
    for q in manager_quarters(w["path"], n):
        hs = holdings(q["id"])
        if hs:
            out.append((q["quarter"], q["filed"], {h["sym"]: h for h in hs}))
    return out


def crowd_analysis(watch):
    """40곳의 최신·직전 분기를 비교해 종목별 집단 움직임을 집계한다.
    반환: {sym: {name, holders, new, exit, add, cut, shares, value}}"""
    agg, names = {}, {}
    hist = jload(DATA / "history.json", {}) or {}

    for w in watch:
        qs = fund_quarters(w, 6)
        if not qs:
            continue
        # 분기별 누적 이력 (그래프용)
        for quarter, filed, hs in qs:
            slot = hist.setdefault(quarter, {})
            for sym, h in hs.items():
                s = slot.setdefault(sym, {"h": 0, "sh": 0.0, "v": 0.0, "by": []})
                if w["name"] not in s["by"]:
                    s["by"].append(w["name"])
                    s["h"] = len(s["by"])
                    s["sh"] += h["shares"]
                    s["v"] += h["value"]
                names.setdefault(sym, h["issuer"])

        cur = qs[0][2]
        prev = qs[1][2] if len(qs) > 1 else {}
        for sym, h in cur.items():
            a = agg.setdefault(sym, {"holders": [], "new": [], "exit": [],
                                     "add": [], "cut": [], "shares": 0.0, "value": 0.0})
            a["holders"].append(w["name"])
            a["shares"] += h["shares"]
            a["value"] += h["value"]
            p = prev.get(sym)
            if not p or p["shares"] <= 0:
                if prev:
                    a["new"].append(w["name"])
            elif h["shares"] > p["shares"] * 1.05:
                a["add"].append(w["name"])
            elif h["shares"] < p["shares"] * 0.95:
                a["cut"].append(w["name"])
            names.setdefault(sym, h["issuer"])
        for sym, p in prev.items():
            if sym not in cur:
                a = agg.setdefault(sym, {"holders": [], "new": [], "exit": [],
                                         "add": [], "cut": [], "shares": 0.0, "value": 0.0})
                a["exit"].append(w["name"])
                names.setdefault(sym, p["issuer"])

    jsave(DATA / "history.json", hist)
    for sym, a in agg.items():
        a["name"] = names.get(sym, "")
        a["sym"] = sym
        a["n_hold"] = len(a["holders"])
        a["n_in"] = len(a["new"]) + len(a["add"])      # 편입 = 신규 + 증가
        a["n_out"] = len(a["exit"]) + len(a["cut"])    # 편출 = 전량매도 + 축소
        a["score"] = a["n_in"] - a["n_out"]
    return agg, hist


def top_consensus(agg, n=15):
    """여러 펀드가 함께 들고 있는 종목."""
    rows = [a for a in agg.values() if a["n_hold"] >= 2]
    rows.sort(key=lambda a: (-a["n_hold"], -a["value"]))
    return rows[:n]


def top_flow(agg, n=12, direction="in"):
    """편입이 압도적인 종목 / 편출이 압도적인 종목."""
    rows = [a for a in agg.values() if (a["n_in"] + a["n_out"]) >= 2]
    rows.sort(key=lambda a: (-a["score"], -a["n_hold"]) if direction == "in"
              else (a["score"], -a["n_hold"]))
    return rows[:n]


def series_of(hist, sym, key="h"):
    """이력에서 한 종목의 분기별 값. [(분기, 값)] 시간순."""
    def qkey(q):
        m = re.search(r"Q([1-4])\s*(20\d\d)", q)
        return (int(m.group(2)), int(m.group(1))) if m else (0, 0)
    qs = sorted([q for q in hist if qkey(q) != (0, 0)], key=qkey)
    return [(q, hist[q].get(sym, {}).get(key, 0)) for q in qs]


def trend_rows(agg, hist, n=8):
    """그래프로 보여줄 종목: 최근 분기 사이 보유 펀드 수 변화가 큰 것."""
    out = []
    for a in agg.values():
        s = series_of(hist, a["sym"], "h")
        s = [(q, v) for q, v in s if v > 0]
        if len(s) < 2:
            continue
        change = s[-1][1] - s[0][1]
        out.append({**a, "series": s, "change": change})
    out.sort(key=lambda x: (-abs(x["change"]), -x["n_hold"]))
    return out[:n]


def spark(vals, width=12):
    """숫자 목록을 막대 문자로. 표 안에 넣는 간이 그래프."""
    if not vals:
        return ""
    bars = "▁▂▃▄▅▆▇█"
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return bars[3] * min(len(vals), width)
    return "".join(bars[int((v - lo) / (hi - lo) * (len(bars) - 1))] for v in vals[-width:])




# ════════════════════════════════ 유명인 개인별 상세 (편입·증감·최초편입)
DEEP_QUARTERS = 13          # 최초 편입 시기를 얼마나 거슬러 볼지 (약 3년)
DETAIL_TOP_N = 20           # 개인별 목록에 보여줄 최대 종목 수


def qsort_key(q):
    m = re.search(r"Q([1-4])\s*(20\d\d)", q or "")
    return (int(m.group(2)), int(m.group(1))) if m else (0, 0)


def person_detail(w, deep=False):
    """한 사람의 이번 분기 움직임.
    신규 편입 / 늘린 종목 / 줄인 종목 / (deep이면) 보유 상위 종목의 최초 편입 시기."""
    qs = manager_quarters(w["path"], DEEP_QUARTERS if deep else 2)
    if not qs:
        return None
    cur_q = qs[0]
    cur = {h["sym"]: h for h in holdings(cur_q["id"])}
    if not cur:
        return None
    prev = {h["sym"]: h for h in holdings(qs[1]["id"])} if len(qs) > 1 else {}
    total = sum(h["value"] for h in cur.values()) or 1.0

    new, up, down = [], [], []
    for sym, h in cur.items():
        wt = h["value"] / total * 100
        p = prev.get(sym)
        if not p or p["shares"] <= 0:
            if prev:                      # 직전 분기 자료가 있을 때만 '신규'로 본다
                new.append({**h, "weight": wt})
        elif h["shares"] > p["shares"] * 1.02:
            up.append({**h, "weight": wt, "pct": (h["shares"] / p["shares"] - 1) * 100,
                       "prev_shares": p["shares"]})
        elif h["shares"] < p["shares"] * 0.98:
            down.append({**h, "weight": wt, "pct": (1 - h["shares"] / p["shares"]) * 100,
                         "prev_shares": p["shares"]})
    gone = [{**p, "weight": 0.0, "pct": 100.0, "prev_shares": p["shares"],
             "shares": 0.0, "value": 0.0, "sold_out": True}
            for sym, p in prev.items() if sym not in cur]

    k = lambda x: -x["value"]
    out = {"name": w["name"], "rank": w["rank"], "ret_1y": w["ret_1y"],
           "quarter": cur_q["quarter"], "filed": cur_q["filed"], "fid": cur_q["id"],
           "n": len(cur), "total": total, "has_prev": bool(prev),
           "new": sorted(new, key=k)[:DETAIL_TOP_N],
           "up": sorted(up, key=k)[:DETAIL_TOP_N],
           "down": sorted(down + gone, key=lambda x: -x["prev_shares"])[:DETAIL_TOP_N]}

    if deep:
        # 분기를 과거→현재로 훑으며 각 종목이 처음 등장한 분기를 기록
        first, oldest = {}, None
        for q in sorted(qs, key=lambda x: qsort_key(x["quarter"])):
            hs = holdings(q["id"])
            if not hs:
                continue
            if oldest is None:
                oldest = q["quarter"]
            for h in hs:
                first.setdefault(h["sym"], q["quarter"])
        top = sorted(cur.values(), key=k)[:DETAIL_TOP_N]
        out["holdings"] = [{**h, "weight": h["value"] / total * 100,
                            "since": first.get(h["sym"], "?"),
                            "since_or_before": first.get(h["sym"]) == oldest and oldest is not None}
                           for h in top]
        out["oldest"] = oldest
    return out


def people_details(ppl, detail_n=20, deep_n=10):
    """상위 detail_n명의 움직임, 그중 deep_n명은 최초 편입 시기까지."""
    out = []
    for i, r in enumerate(ppl[:detail_n]):
        d = person_detail(r, deep=(i < deep_n))
        if d:
            out.append(d)
        if (i + 1) % 5 == 0:
            log(f"  개인별 상세 {i + 1}/{min(detail_n, len(ppl))}")
    return out




# ══════════════════════════════════════════ 전일 대비 변화 (색상 표시용)
DAYFILE = DATA / "prevday.json"


def day_state(inst, ppl, agg, details):
    """오늘 상태를 한 덩어리로. 내일 비교 기준이 된다."""
    return {
        "date": date.today().isoformat(),
        "inst": {r["name"]: {"rank": r["rank"], "ret": r["ret_1y"]} for r in inst[:TOP_N]},
        "ppl": {r["name"]: {"rank": r["rank"], "ret": r["ret_1y"]} for r in ppl[:TOP_N]},
        "hold": {s: a["n_hold"] for s, a in agg.items()},
        "score": {s: a["score"] for s, a in agg.items()},
        "detail": {d["name"]: {k: [x["sym"] for x in d.get(k, [])]
                               for k in ("new", "up", "down")} for d in (details or [])},
    }


def load_prevday():
    return jload(DAYFILE, {}) or {}


def rank_mark(prev, group, name, rank):
    """순위 변동 → (표시, 색이름). 색이름은 up/down/new/same."""
    p = (prev.get(group) or {}).get(name)
    if not prev.get(group):
        return "", "same"          # 첫 실행이면 비교 대상 없음
    if p is None:
        return "NEW", "new"
    d = p["rank"] - rank
    if d > 0:
        return f"▲{d}", "up"
    if d < 0:
        return f"▼{-d}", "down"
    return "–", "same"


def ret_mark(prev, group, name, ret):
    """수익률 변동 → (표시, 색이름)."""
    p = (prev.get(group) or {}).get(name)
    if not p:
        return "", "same"
    d = ret - p["ret"]
    if abs(d) < 0.05:
        return "", "same"
    return f"{d:+.1f}p", ("up" if d > 0 else "down")


def num_mark(prev, key, sym, cur):
    """보유 펀드 수·순증감 변동 → (표시, 색이름)."""
    p = (prev.get(key) or {}).get(sym)
    if p is None:
        return ("NEW", "new") if prev.get(key) else ("", "same")
    d = cur - p
    if d == 0:
        return "", "same"
    return f"{d:+d}", ("up" if d > 0 else "down")


def is_fresh(prev, person, kind, sym):
    """개인별 목록에서 어제는 없다가 오늘 새로 생긴 항목인지."""
    if not prev.get("date"):
        return False                      # 첫 실행 — 비교 대상 없음
    d = (prev.get("detail") or {}).get(person)
    if d is None:
        return True                       # 어제 명단에 없던 사람 → 전부 새 움직임
    return sym not in (d.get(kind) or [])


# ════════════════════════════════════════════════════════ 리포트
def money(v):
    """13f.info 금액 단위는 천 달러."""
    d = v * 1000
    return f"${d/1e9:,.2f}B" if d >= 1e9 else (f"${d/1e6:,.1f}M" if d >= 1e6 else f"${d:,.0f}")


def render(inst, ppl, hits, delta, agg, hist, details=None, prev=None):
    prev = prev or {}
    today = date.today().isoformat()
    L = [f"# 고래 40 · {today}", "",
         f"1년 수익률 기준 기관 TOP {TOP_N} + 유명인 TOP {TOP_N}", ""]
    if prev.get("date"):
        L += [f"_전일({prev['date']}) 대비 — ▲ 오름 · ▼ 내림 · ★ 새로 등장 · NEW 신규 진입_", ""]

    L += ["## 🔔 새로 올라온 13F", ""]
    if not hits:
        L += ["최근 새 공시 없음. 13F는 분기마다(2·5·8·11월 중순) 몰려서 올라옵니다.", ""]
    for h in hits:
        L.append(f"### {h['name']} `{h['group']} {h['rank']}위 · 1Y {h['ret_1y']:+.1f}%`")
        L.append(f"{h['quarter']} · {h['n']}종목 · 공시 {h['filed']}")
        if not h["baseline"]:
            L.append("- _직전 분기 자료 없음 → 전량 신규로 표시_")
        for x in h["new"][:12]:
            L.append(f"- ✨ 신규 **{stock_label(x['sym'], x['issuer'])}** · {x['shares']:,.0f}주 · {money(x['value'])}")
        for x in h["added"][:12]:
            L.append(f"- ➕ 추가 **{stock_label(x['sym'], x['issuer'])}** · {money(x['value'])} ({x['pct']:+.0f}%)")
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

    con = top_consensus(agg, 15)
    if con:
        L += ["## 🤝 여러 곳이 함께 보유한 종목", "",
              "| 종목 | 보유 | 전일 | 합계 주식수 | 합계 평가액 | 편입 | 편출 |",
              "|---|---|---|---|---|---|---|"]
        for a in con:
            hm, _ = num_mark(prev, "hold", a["sym"], a["n_hold"])
            L.append(f"| {stock_label(a['sym'], a['name'])} | {a['n_hold']}곳 | {hm or '·'} | "
                     f"{a['shares']:,.0f} | {money(a['value'])} | {a['n_in']} | {a['n_out']} |")
        L.append("")

    for direction, title in (("in", "📈 편입이 몰린 종목"), ("out", "📉 편출이 몰린 종목")):
        rows_f = [r for r in top_flow(agg, 12, direction)
                  if (r["score"] > 0 if direction == "in" else r["score"] < 0)]
        if not rows_f:
            continue
        L += [f"## {title}", "",
              "| 종목 | 편입 | 편출 | 순증감 | 전일 | 보유 | 합계 평가액 |",
              "|---|---|---|---|---|---|---|"]
        for a in rows_f:
            sm, _ = num_mark(prev, "score", a["sym"], a["score"])
            L.append(f"| {stock_label(a['sym'], a['name'])} | {a['n_in']} | {a['n_out']} | "
                     f"**{a['score']:+d}** | {sm or '·'} | {a['n_hold']}곳 | {money(a['value'])} |")
        L.append("")

    tr = trend_rows(agg, hist, 8)
    if tr and len(tr[0]["series"]) >= 2:
        L += ["## 📊 분기별 보유 펀드 수 추이", "",
              "| 종목 | 추이 | 분기별 |", "|---|---|---|"]
        for r in tr:
            L.append(f"| {stock_label(r['sym'], r['name'])} | `{spark([v for _, v in r['series']])}` | "
                     f"{' → '.join(f'{q}:{v}' for q, v in r['series'])} |")
        L.append("")

    for rows, gl, gkey in ((inst, "기관", "inst"), (ppl, "유명인", "ppl")):
        L += [f"## {gl} TOP {TOP_N}", "",
              "| # | 전일 | 이름 | 1년 | 증감 | 상위 보유 |", "|---|---|---|---|---|---|"]
        for r in rows[:TOP_N]:
            rm, _ = rank_mark(prev, gkey, r["name"], r["rank"])
            vm, _ = ret_mark(prev, gkey, r["name"], r["ret_1y"])
            L.append(f"| {r['rank']} | {rm or '·'} | {r['name']} | **{r['ret_1y']:+.1f}%** | "
                     f"{vm or '·'} | {', '.join(r['top'])} |")
        L.append("")

    if details:
        L += ["---", "", "# 👤 유명인 개인별 이번 분기 움직임", ""]
        for d in details:
            L += [f"## {d['rank']}위 {d['name']}  `1Y {d['ret_1y']:+.1f}%`",
                  f"{d['quarter']} · {d['n']}종목 · 총 {money(d['total'])} · 공시 {d['filed']}", ""]
            if not d["has_prev"]:
                L += ["_직전 분기 자료가 없어 증감 비교를 건너뜁니다._", ""]
            if d["new"]:
                L += ["**✨ 신규 편입**", "", "| 종목 | 비중 | 주식수 | 평가액 |", "|---|---|---|---|"]
                for x in d["new"]:
                    st = "★ " if is_fresh(prev, d["name"], "new", x["sym"]) else ""
                    L.append(f"| {st}{stock_label(x['sym'], x['issuer'])} | **{x['weight']:.2f}%** | "
                             f"{x['shares']:,.0f} | {money(x['value'])} |")
                L.append("")
            if d["up"]:
                L += ["**➕ 늘린 종목**", "", "| 종목 | 증가율 | 비중 | 주식수 (직전→현재) |", "|---|---|---|---|"]
                for x in d["up"]:
                    st = "★ " if is_fresh(prev, d["name"], "up", x["sym"]) else ""
                    L.append(f"| {st}{stock_label(x['sym'], x['issuer'])} | **+{x['pct']:.1f}%** | "
                             f"{x['weight']:.2f}% | {x['prev_shares']:,.0f} → {x['shares']:,.0f} |")
                L.append("")
            if d["down"]:
                L += ["**➖ 줄인 종목**", "", "| 종목 | 감소율 | 비중 | 주식수 (직전→현재) |", "|---|---|---|---|"]
                for x in d["down"]:
                    tag = " *(전량매도)*" if x.get("sold_out") else ""
                    st = "★ " if is_fresh(prev, d["name"], "down", x["sym"]) else ""
                    L.append(f"| {st}{stock_label(x['sym'], x['issuer'])}{tag} | **-{x['pct']:.1f}%** | "
                             f"{x['weight']:.2f}% | {x['prev_shares']:,.0f} → {x['shares']:,.0f} |")
                L.append("")
            if d.get("holdings"):
                L += [f"**📌 보유 상위 {len(d['holdings'])}종목 — 최초 편입 시기**", "",
                      "| 종목 | 비중 | 최초 편입 | 평가액 |", "|---|---|---|---|"]
                for x in d["holdings"]:
                    since = x["since"] + ("~" if x["since_or_before"] else "")
                    L.append(f"| {stock_label(x['sym'], x['issuer'])} | **{x['weight']:.2f}%** | "
                             f"{since} | {money(x['value'])} |")
                L += ["", f"_`~` 표시는 조회 범위({d.get('oldest','')}) 이전부터 보유했을 수 있다는 뜻입니다._", ""]

    L += ["---", "",
          f"**수익률 읽는 법.** 13F로 공시된 미국 상장 보유 상위 {TOP_HOLDINGS}종목을 "
          "공시일에 가치비중대로 복제했다고 가정한 값입니다. 실제 펀드 수익률이 아닙니다 — "
          "공매도·해외주식·채권·현금·수수료가 모두 빠져 있습니다.", "",
          "**시차.** 13F는 분기말 후 45일에 공개됩니다. 여기 뜨는 편입은 최대 4개월 전의 매매입니다.", "",
          "출처: 13f.info · Yahoo Finance. 투자 자문이 아닙니다."]
    return "\n".join(L)




# ════════════════════════════════════════════════════════ PDF 리포트
def korean_font_candidates():
    """한글이 나오는 폰트 후보를 우선순위대로. reportlab은 TrueType 외곽선만 지원하므로
    Noto CJK(.ttc, PostScript 외곽선)는 등록에 실패할 수 있어 여러 개를 준비한다."""
    import glob
    out = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquare.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
    ]
    out += sorted(glob.glob("/usr/share/fonts/**/*Nanum*.tt[fc]", recursive=True))
    out += sorted(glob.glob("/usr/share/fonts/**/*Gothic*.tt[fc]", recursive=True))
    out += sorted(glob.glob("/usr/share/fonts/**/*CJK*.tt[fc]", recursive=True))
    seen, uniq = set(), []
    for p in out:
        if p not in seen and os.path.exists(p):
            seen.add(p)
            uniq.append(p)
    return uniq


def register_korean_font():
    """등록에 성공하고 실제로 한글 폭을 잴 수 있는 폰트를 찾아 이름을 돌려준다."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for i, p in enumerate(korean_font_candidates()):
        name = f"KR{i}"
        try:
            if p.lower().endswith(".ttc"):
                pdfmetrics.registerFont(TTFont(name, p, subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont(name, p))
            if pdfmetrics.stringWidth("한글 종목 시험", name, 10) > 0:
                log(f"PDF 폰트: {os.path.basename(p)}")
                return name
        except Exception as e:
            log(f"  폰트 건너뜀 {os.path.basename(p)}: {type(e).__name__}")
    return None


def make_pdf(path, inst, ppl, hits, delta, agg, hist, details=None, prev=None):
    """리포트를 PDF로. 실패하면 None을 돌려주고 나머지 흐름은 계속된다."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                        TableStyle, PageBreak)
        from reportlab.graphics.shapes import Drawing, String
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
    except ImportError:
        log("PDF: reportlab 미설치 — 건너뜀")
        return None

    KRF = register_korean_font()
    if not KRF:
        log("PDF: 쓸 수 있는 한글 폰트가 없어 건너뜀 "
            "(워크플로에 fonts-nanum 설치를 추가하세요)")
        return None

    ACC, MUT, LINE = colors.HexColor("#2d6a4f"), colors.HexColor("#6f6b64"), colors.HexColor("#dcd8cd")
    # 전일 대비: 오름 빨강 / 내림 파랑 / 신규 보라 (한국 증시 관행에 맞춤)
    CLR = {"up": colors.HexColor("#c0392b"), "down": colors.HexColor("#1d6fb8"),
           "new": colors.HexColor("#7b3fa0"), "same": MUT}
    H1 = ParagraphStyle("h1", fontName=KRF, fontSize=17, leading=22, spaceAfter=2)
    SUB = ParagraphStyle("sub", fontName=KRF, fontSize=8.5, leading=12, textColor=MUT, spaceAfter=10)
    H2 = ParagraphStyle("h2", fontName=KRF, fontSize=11.5, leading=16, textColor=ACC,
                        spaceBefore=12, spaceAfter=5)
    BODY = ParagraphStyle("b", fontName=KRF, fontSize=8.5, leading=12.5)
    SMALL = ParagraphStyle("s", fontName=KRF, fontSize=7.5, leading=11, textColor=MUT)

    def tbl(data, widths, align_right=(), paint=()):
        """paint: [(col, row, 색이름)] — 해당 칸 글자색을 바꾼다 (전일 대비 표시용)."""
        t = Table(data, colWidths=widths, repeatRows=1)
        st = [("FONT", (0, 0), (-1, -1), KRF, 8),
              ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("BACKGROUND", (0, 0), (-1, 0), ACC),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 3.5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
              ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f5f0")])]
        for c in align_right:
            st.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
        for c, r, name in paint:
            if name != "same":
                st.append(("TEXTCOLOR", (c, r), (c, r), CLR[name]))
                st.append(("FONT", (c, r), (c, r), KRF, 8))
        t.setStyle(TableStyle(st))
        return t

    prev = prev or {}
    story, today = [], date.today().isoformat()
    story.append(Paragraph(f"고래 40 · {today}", H1))
    story.append(Paragraph(
        f"1년 수익률 기준 기관 TOP {TOP_N} + 유명인 TOP {TOP_N} · 출처 13f.info, Yahoo Finance", SUB))
    if prev.get("date"):
        story.append(Paragraph(
            f'전일({prev["date"]}) 대비 &mdash; '
            f'<font color="#c0392b">빨강 = 오름</font> · '
            f'<font color="#1d6fb8">파랑 = 내림</font> · '
            f'<font color="#7b3fa0">보라 = 새로 등장(★)</font>', SMALL))
        story.append(Spacer(1, 4))

    # 1) 새 13F
    story.append(Paragraph("새로 올라온 13F", H2))
    if not hits:
        story.append(Paragraph("최근 새 공시 없음. 13F는 2·5·8·11월 중순에 몰려 올라옵니다.", BODY))
    for h in hits[:6]:
        story.append(Paragraph(
            f"<b>{h['name']}</b> ({h['group']} {h['rank']}위 · 1Y {h['ret_1y']:+.1f}%) "
            f"— {h['quarter']}, {h['n']}종목", BODY))
        for x in h["new"][:8]:
            story.append(Paragraph(f"　신규 {stock_label(x['sym'], x['issuer'])} · "
                                   f"{x['shares']:,.0f}주 · {money(x['value'])}", SMALL))
        for x in h["added"][:8]:
            story.append(Paragraph(f"　추가 {stock_label(x['sym'], x['issuer'])} · "
                                   f"{money(x['value'])} ({x['pct']:+.0f}%)", SMALL))
        story.append(Spacer(1, 3))

    # 2) 공동 보유
    con = top_consensus(agg, 15)
    if con:
        story.append(Paragraph("여러 곳이 함께 보유한 종목", H2))
        data = [["종목", "보유 펀드", "전일", "합계 주식수", "합계 평가액", "편입", "편출"]]
        paint = []
        for i, a in enumerate(con, start=1):
            hm, hc = num_mark(prev, "hold", a["sym"], a["n_hold"])
            data.append([stock_label(a["sym"], a["name"])[:26], f"{a['n_hold']}곳", hm,
                         f"{a['shares']:,.0f}", money(a["value"]),
                         str(a["n_in"]), str(a["n_out"])])
            paint.append((2, i, hc))
        story.append(tbl(data, [48 * mm, 16 * mm, 12 * mm, 28 * mm, 25 * mm, 13 * mm, 13 * mm],
                         (3, 4, 5, 6), paint))

    # 3) 편입 / 편출 쏠림
    for direction, title in (("in", "편입이 몰린 종목"), ("out", "편출이 몰린 종목")):
        rows = [r for r in top_flow(agg, 12, direction)
                if (r["score"] > 0 if direction == "in" else r["score"] < 0)]
        if not rows:
            continue
        story.append(Paragraph(title, H2))
        data = [["종목", "편입", "편출", "순증감", "전일", "보유", "합계 평가액"]]
        paint = []
        for i, a in enumerate(rows, start=1):
            sm, sc = num_mark(prev, "score", a["sym"], a["score"])
            data.append([stock_label(a["sym"], a["name"])[:26], str(a["n_in"]), str(a["n_out"]),
                         f"{a['score']:+d}", sm, f"{a['n_hold']}곳", money(a["value"])])
            paint += [(3, i, "up" if a["score"] > 0 else "down"), (4, i, sc)]
        story.append(tbl(data, [46 * mm, 13 * mm, 13 * mm, 16 * mm, 13 * mm, 14 * mm, 25 * mm],
                         (1, 2, 3, 4, 5, 6), paint))

    # 4) 분기별 추이 그래프
    tr = trend_rows(agg, hist, 6)
    if tr and len(tr[0]["series"]) >= 2:
        story.append(PageBreak())
        story.append(Paragraph("분기별 보유 펀드 수 추이", H2))
        story.append(Paragraph(
            "감시 대상 40곳 중 해당 종목을 보유한 곳의 수입니다. 분기가 쌓일수록 선이 길어집니다.", SMALL))
        quarters = [q for q, _ in tr[0]["series"]]
        d = Drawing(460, 200)
        ch = HorizontalLineChart()
        ch.x, ch.y, ch.width, ch.height = 35, 30, 400, 150
        ch.data = [[v for _, v in r["series"]] for r in tr]
        ch.categoryAxis.categoryNames = quarters
        ch.categoryAxis.labels.fontName = KRF
        ch.categoryAxis.labels.fontSize = 7
        ch.valueAxis.labels.fontName = KRF
        ch.valueAxis.labels.fontSize = 7
        ch.valueAxis.valueMin = 0
        ch.lines.strokeWidth = 1.6
        palette = ["#2d6a4f", "#b4451f", "#2b6cb0", "#8a5a00", "#6b46c1", "#0f766e"]
        for i in range(len(ch.data)):
            ch.lines[i].strokeColor = colors.HexColor(palette[i % len(palette)])
        d.add(ch)
        story.append(d)
        leg = [["종목", "추이", "분기별 보유 펀드 수"]]
        for i, r in enumerate(tr):
            leg.append([stock_label(r["sym"], r["name"])[:24],
                        spark([v for _, v in r["series"]]),
                        " → ".join(f"{q[:2]}{q[-2:]}:{v}" for q, v in r["series"])])
        story.append(Spacer(1, 6))
        story.append(tbl(leg, [46 * mm, 22 * mm, 92 * mm]))

    # 5) 순위표
    for rows, gl, gkey in ((inst, "기관", "inst"), (ppl, "유명인", "ppl")):
        if not rows:
            continue
        story.append(Paragraph(f"{gl} TOP {TOP_N} · 1년 수익률", H2))
        data = [["#", "전일", "이름", "1년", "증감", "상위 보유"]]
        paint = []
        for i, r in enumerate(rows[:TOP_N], start=1):
            rm, rc = rank_mark(prev, gkey, r["name"], r["rank"])
            vm, vc = ret_mark(prev, gkey, r["name"], r["ret_1y"])
            data.append([str(r["rank"]), rm, r["name"][:24], f"{r['ret_1y']:+.1f}%", vm,
                         ", ".join(r["top"])[:48]])
            paint += [(1, i, rc), (4, i, vc)]
        story.append(tbl(data, [8 * mm, 13 * mm, 40 * mm, 17 * mm, 14 * mm, 68 * mm],
                         (3,), paint))

    if details:
        story.append(PageBreak())
        story.append(Paragraph("유명인 개인별 이번 분기 움직임", H2))
        for d in details:
            story.append(Paragraph(
                f"<b>{d['rank']}위 {d['name']}</b> · 1Y {d['ret_1y']:+.1f}% · "
                f"{d['quarter']} · {d['n']}종목 · 총 {money(d['total'])}", BODY))
            if d["new"]:
                data = [["신규 편입", "비중", "주식수", "평가액"]]
                paint = []
                for i, x in enumerate(d["new"][:12], start=1):
                    fresh = is_fresh(prev, d["name"], "new", x["sym"])
                    data.append([("★ " if fresh else "") + stock_label(x["sym"], x["issuer"])[:22],
                                 f"{x['weight']:.2f}%", f"{x['shares']:,.0f}", money(x["value"])])
                    if fresh:
                        paint.append((0, i, "new"))
                story.append(tbl(data, [58 * mm, 18 * mm, 32 * mm, 28 * mm], (1, 2, 3), paint))
            if d["up"]:
                data = [["늘린 종목", "증가율", "비중", "주식수 직전→현재"]]
                paint = []
                for i, x in enumerate(d["up"][:12], start=1):
                    fresh = is_fresh(prev, d["name"], "up", x["sym"])
                    data.append([("★ " if fresh else "") + stock_label(x["sym"], x["issuer"])[:22],
                                 f"+{x['pct']:.1f}%", f"{x['weight']:.2f}%",
                                 f"{x['prev_shares']:,.0f} → {x['shares']:,.0f}"])
                    paint.append((1, i, "up"))
                    if fresh:
                        paint.append((0, i, "new"))
                story.append(tbl(data, [50 * mm, 20 * mm, 18 * mm, 48 * mm], (1, 2, 3), paint))
            if d["down"]:
                data = [["줄인 종목", "감소율", "비중", "주식수 직전→현재"]]
                paint = []
                for i, x in enumerate(d["down"][:12], start=1):
                    fresh = is_fresh(prev, d["name"], "down", x["sym"])
                    nm = ("★ " if fresh else "") + stock_label(x["sym"], x["issuer"])[:18] + \
                         ("(전량)" if x.get("sold_out") else "")
                    data.append([nm, f"-{x['pct']:.1f}%", f"{x['weight']:.2f}%",
                                 f"{x['prev_shares']:,.0f} → {x['shares']:,.0f}"])
                    paint.append((1, i, "down"))
                    if fresh:
                        paint.append((0, i, "new"))
                story.append(tbl(data, [50 * mm, 20 * mm, 18 * mm, 48 * mm], (1, 2, 3), paint))
            if d.get("holdings"):
                data = [[f"보유 상위 {len(d['holdings'])} — 최초 편입", "비중", "최초 편입", "평가액"]]
                for x in d["holdings"]:
                    data.append([stock_label(x["sym"], x["issuer"])[:24], f"{x['weight']:.2f}%",
                                 x["since"] + ("~" if x["since_or_before"] else ""),
                                 money(x["value"])])
                story.append(tbl(data, [58 * mm, 18 * mm, 30 * mm, 30 * mm], (1, 3)))
                story.append(Paragraph(
                    f"~ 는 조회 범위({d.get('oldest','')}) 이전부터 보유했을 수 있다는 뜻입니다.", SMALL))
            story.append(Spacer(1, 8))

    moves = [(g, dd) for g, dd in delta.items() if dd["in"] or dd["out"]]
    if moves:
        story.append(Paragraph(f"TOP {TOP_N} 변동", H2))
        for g, dd in moves:
            if dd["in"]:
                story.append(Paragraph(f"{g} 진입 — {', '.join(dd['in'])}", BODY))
            if dd["out"]:
                story.append(Paragraph(f"{g} 이탈 — {', '.join(dd['out'])}", BODY))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "수익률은 13F로 공시된 미국 상장 보유 상위 20종목을 공시일에 가치비중대로 복제했다고 "
        "가정한 추정치입니다. 실제 펀드 수익률이 아니며 공매도·해외주식·채권·현금·수수료가 "
        "빠져 있습니다. 13F는 분기말 후 45일에 공개되므로 최대 4개월 전의 매매입니다. "
        "투자 자문이 아닙니다.", SMALL))

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"고래 40 {today}", author="whale40")
    doc.build(story)
    return path




# ══════════════════════════════════════════════ 한 장 요약 (일간 다이제스트)
DIGEST_RANK_MOVE = 2      # 순위가 이만큼 이상 움직이면 '유의미'
DIGEST_RET_MOVE = 1.0     # 1년 수익률이 이만큼(%p) 이상 움직이면 '유의미'
DIGEST_HOLD_MOVE = 1      # 보유 펀드 수가 이만큼 이상 변하면 '유의미'


def digest_items(inst, ppl, agg, details, hits, prev):
    """전일 대비 눈에 띄는 변화만 추린다. 한 장에 담을 분량으로 제한."""
    d = {"rank": [], "ret": [], "hold": [], "flow": [], "fresh": [], "filings": [],
         "first": not bool(prev.get("date")), "prev_date": prev.get("date", "")}

    for rows, gl, gkey in ((inst, "기관", "inst"), (ppl, "유명인", "ppl")):
        for r in rows[:TOP_N]:
            p = (prev.get(gkey) or {}).get(r["name"])
            if p is None:
                if prev.get(gkey):
                    d["rank"].append({"g": gl, "name": r["name"], "rank": r["rank"],
                                      "move": None, "kind": "new", "ret": r["ret_1y"]})
                continue
            mv = p["rank"] - r["rank"]
            if abs(mv) >= DIGEST_RANK_MOVE:
                d["rank"].append({"g": gl, "name": r["name"], "rank": r["rank"],
                                  "move": mv, "kind": "up" if mv > 0 else "down",
                                  "ret": r["ret_1y"]})
            dv = r["ret_1y"] - p["ret"]
            if abs(dv) >= DIGEST_RET_MOVE:
                d["ret"].append({"g": gl, "name": r["name"], "rank": r["rank"],
                                 "diff": dv, "ret": r["ret_1y"]})
    # 이탈한 곳
    for gkey, gl, rows in (("inst", "기관", inst), ("ppl", "유명인", ppl)):
        cur = {r["name"] for r in rows[:TOP_N]}
        for name in (prev.get(gkey) or {}):
            if name not in cur:
                d["rank"].append({"g": gl, "name": name, "rank": None, "move": None,
                                  "kind": "out", "ret": None})

    d["rank"].sort(key=lambda x: (x["kind"] != "new", x["kind"] == "out",
                                  -abs(x["move"] or 99)))
    d["ret"].sort(key=lambda x: -abs(x["diff"]))

    for sym, a in agg.items():
        p = (prev.get("hold") or {}).get(sym)
        if p is None:
            if prev.get("hold") and a["n_hold"] >= 2:
                d["hold"].append({**a, "diff": None, "kind": "new"})
        else:
            df = a["n_hold"] - p
            if abs(df) >= DIGEST_HOLD_MOVE:
                d["hold"].append({**a, "diff": df, "kind": "up" if df > 0 else "down"})
    d["hold"].sort(key=lambda x: (-(abs(x["diff"]) if x["diff"] is not None else 99),
                                  -x["n_hold"]))

    d["flow"] = [a for a in top_flow(agg, 8, "in") if a["score"] >= 2][:6]

    for dd in (details or []):
        for kind, tag in (("new", "신규"), ("up", "증가"), ("down", "감소")):
            for x in dd.get(kind, [])[:6]:
                if is_fresh(prev, dd["name"], kind, x["sym"]):
                    d["fresh"].append({"who": dd["name"], "rank": dd["rank"], "tag": tag,
                                       "sym": x["sym"], "issuer": x["issuer"],
                                       "weight": x.get("weight", 0), "pct": x.get("pct"),
                                       "value": x.get("value", 0)})
    d["fresh"].sort(key=lambda x: (x["rank"], -x["value"]))

    d["filings"] = [{"name": h["name"], "g": h["group"], "rank": h["rank"],
                     "quarter": h["quarter"], "new": len(h["new"]), "added": len(h["added"]),
                     "syms": [x["sym"] for x in h["new"][:4]]} for h in (hits or [])]
    return d


def make_digest_pdf(path, items, prev):
    """A4 한 장짜리 요약. 분량이 넘치면 각 구간을 잘라 한 장에 맞춘다."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
    except ImportError:
        return None
    KRF = register_korean_font()
    if not KRF:
        return None

    ACC, MUT, LINE = colors.HexColor("#2d6a4f"), colors.HexColor("#6f6b64"), colors.HexColor("#dcd8cd")
    CLR = {"up": colors.HexColor("#c0392b"), "down": colors.HexColor("#1d6fb8"),
           "new": colors.HexColor("#7b3fa0"), "out": colors.HexColor("#1d6fb8"), "same": MUT}
    H1 = ParagraphStyle("h1", fontName=KRF, fontSize=15, leading=19)
    SUB = ParagraphStyle("sub", fontName=KRF, fontSize=7.8, leading=11, textColor=MUT, spaceAfter=7)
    H2 = ParagraphStyle("h2", fontName=KRF, fontSize=9.5, leading=13, textColor=ACC,
                        spaceBefore=7, spaceAfter=3)
    BODY = ParagraphStyle("b", fontName=KRF, fontSize=8, leading=11)
    SMALL = ParagraphStyle("s", fontName=KRF, fontSize=6.8, leading=9.5, textColor=MUT)

    def tbl(data, widths, right=(), paint=()):
        t = Table(data, colWidths=widths)
        st = [("FONT", (0, 0), (-1, -1), KRF, 7.4),
              ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("BACKGROUND", (0, 0), (-1, 0), ACC),
              ("TOPPADDING", (0, 0), (-1, -1), 2.2),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
              ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f5f0")])]
        for c in right:
            st.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
        for c, r, k in paint:
            if k != "same":
                st.append(("TEXTCOLOR", (c, r), (c, r), CLR[k]))
        t.setStyle(TableStyle(st))
        return t

    def build(cap):
     S, today = [], date.today().isoformat()
     S.append(Paragraph(f"고래 40 요약 · {today}", H1))
     if items["first"]:
        S.append(Paragraph("첫 실행이라 전일 비교 자료가 없습니다. 내일부터 변화가 표시됩니다.", SUB))
     else:
        S.append(Paragraph(
            f'전일({items["prev_date"]}) 대비 유의미한 변화만 추렸습니다 · '
            f'<font color="#c0392b">빨강 오름</font> '
            f'<font color="#1d6fb8">파랑 내림</font> '
            f'<font color="#7b3fa0">보라 신규</font>', SUB))

     if items["filings"]:
        S.append(Paragraph("새로 올라온 13F", H2))
        data = [["대상", "분기", "신규", "추가", "주요 신규 종목"]]
        for f in items["filings"][:max(2, int(5 * cap))]:
            data.append([f"{f['g']} {f['rank']}위 {f['name']}"[:24], f["quarter"],
                         str(f["new"]), str(f["added"]), ", ".join(f["syms"])[:30]])
        S.append(tbl(data, [50 * mm, 20 * mm, 13 * mm, 13 * mm, 86 * mm], (2, 3)))

     if items["rank"]:
        S.append(Paragraph("순위 변동", H2))
        data = [["구분", "이름", "순위", "변동", "1년"]]
        paint = []
        for i, r in enumerate(items["rank"][:max(3, int(8 * cap))], start=1):
            if r["kind"] == "new":
                mv, rk, rt = "신규 진입", str(r["rank"]), f"{r['ret']:+.1f}%"
            elif r["kind"] == "out":
                mv, rk, rt = "이탈", "–", "–"
            else:
                mv = f"▲{r['move']}" if r["move"] > 0 else f"▼{-r['move']}"
                rk, rt = str(r["rank"]), f"{r['ret']:+.1f}%"
            data.append([r["g"], r["name"][:26], rk, mv, rt])
            paint.append((3, i, r["kind"]))
        S.append(tbl(data, [16 * mm, 62 * mm, 14 * mm, 24 * mm, 20 * mm], (2, 4), paint))

     if items["ret"]:
        S.append(Paragraph("수익률이 크게 움직인 곳", H2))
        data = [["구분", "이름", "1년", "전일 대비"]]
        paint = []
        for i, r in enumerate(items["ret"][:max(2, int(6 * cap))], start=1):
            data.append([r["g"], r["name"][:26], f"{r['ret']:+.1f}%", f"{r['diff']:+.1f}p"])
            paint.append((3, i, "up" if r["diff"] > 0 else "down"))
        S.append(tbl(data, [16 * mm, 62 * mm, 22 * mm, 26 * mm], (2, 3), paint))

     if items["hold"]:
        S.append(Paragraph("보유 펀드 수가 달라진 종목", H2))
        data = [["종목", "보유", "전일 대비", "편입", "편출"]]
        paint = []
        for i, a in enumerate(items["hold"][:max(3, int(7 * cap))], start=1):
            df = "신규 등장" if a["diff"] is None else f"{a['diff']:+d}"
            data.append([stock_label(a["sym"], a["name"])[:28], f"{a['n_hold']}곳", df,
                         str(a["n_in"]), str(a["n_out"])])
            paint.append((2, i, a["kind"]))
        S.append(tbl(data, [62 * mm, 18 * mm, 24 * mm, 14 * mm, 14 * mm], (1, 2, 3, 4), paint))

     if items["flow"]:
        S.append(Paragraph("편입이 몰린 종목", H2))
        data = [["종목", "편입", "편출", "순증감", "보유"]]
        paint = []
        for i, a in enumerate(items["flow"][:max(2, int(6 * cap))], start=1):
            data.append([stock_label(a["sym"], a["name"])[:28], str(a["n_in"]), str(a["n_out"]),
                         f"{a['score']:+d}", f"{a['n_hold']}곳"])
            paint.append((3, i, "up"))
        S.append(tbl(data, [62 * mm, 14 * mm, 14 * mm, 18 * mm, 16 * mm], (1, 2, 3, 4), paint))

     if items["fresh"]:
        S.append(Paragraph("개인별 새로 잡힌 움직임", H2))
        data = [["사람", "구분", "종목", "비중", "변동"]]
        paint = []
        for i, x in enumerate(items["fresh"][:max(3, int(8 * cap))], start=1):
            if x["pct"] is None or x["tag"] == "신규":
                pc = "–"
            else:
                pc = f"{x['pct']:+.0f}%" if x["tag"] == "증가" else f"-{x['pct']:.0f}%"
            data.append([f"{x['rank']}위 {x['who']}"[:18], x["tag"],
                         stock_label(x["sym"], x["issuer"])[:24],
                         f"{x['weight']:.2f}%", pc])
            paint.append((1, i, "new"))
        S.append(tbl(data, [40 * mm, 14 * mm, 56 * mm, 18 * mm, 18 * mm], (3, 4), paint))

     if not any(items[k] for k in ("rank", "ret", "hold", "flow", "fresh", "filings")):
        S.append(Paragraph("전일 대비 눈에 띄는 변화가 없습니다.", BODY))

     S.append(Spacer(1, 5))
     S.append(Paragraph(
        "상세 내용은 함께 보낸 전체 리포트를 보세요. 수익률은 13F 보유 복제 기준 추정치이며 "
        "실제 펀드 수익률이 아닙니다. 투자 자문이 아닙니다.", SMALL))

     return S

    for cap in (1.0, 0.6, 0.4):
        story = build(cap)
        doc = SimpleDocTemplate(str(path), pagesize=A4,
                                leftMargin=12 * mm, rightMargin=12 * mm,
                                topMargin=12 * mm, bottomMargin=10 * mm,
                                title=f'고래 40 요약 {date.today().isoformat()}',
                                author='whale40')
        doc.build(story)
        if getattr(doc, 'page', 1) <= 1:
            break
    return path
