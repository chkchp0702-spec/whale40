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


def josa(word, pair="이/가"):
    """받침에 따라 조사를 고른다. '버핏가' → '버핏이'."""
    a, b = pair.split("/")
    ch = (word or "").strip()[-1:]
    if not ch:
        return b
    if "가" <= ch <= "힣":
        return a if (ord(ch) - 0xAC00) % 28 else b
    return b if ch in "aeiouAEIOU0123456789" else a


def label_only(sym, issuer=""):
    """'TSM TSMC' 처럼 라벨에서 앞의 티커만 떼어낸 이름 부분."""
    lab = stock_label(sym, issuer)
    return lab[len(sym):].strip() if lab.upper().startswith(sym.upper()) else lab


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

    px, vol, notes = {}, {}, []
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
            vols = (ind.get("quote") or [{}])[0].get("volume") or []
            for i, (t, cl) in enumerate(zip(ts, series or [])):
                if cl is not None:
                    day = datetime.fromtimestamp(t, timezone.utc).date().isoformat()
                    px[day] = float(cl)
                    if i < len(vols) and vols[i] is not None:
                        vol[day] = float(vols[i])
        except (ValueError, KeyError, IndexError, TypeError) as e:
            notes.append(f"해석 실패 {type(e).__name__}")
        if px:
            _yf_ua["i"] = YF_UAS.index(ua)     # 통하는 UA를 다음부터 먼저 쓴다
            break

    yahoo_prices.last_notes = notes
    if not px and b:
        px, vol = b["px"], b.get("vol", {})
    if debug:
        for n in notes:
            log(f"    [debug] {n}")
    jsave(f, {"asof": today, "px": px, "vol": vol})
    return px


def yahoo_volume(sym: str) -> dict[str, float]:
    """일별 거래량. yahoo_prices 와 같은 캐시 파일을 쓴다."""
    f = CACHE / "px" / f"{sym}.json"
    b = jload(f)
    if not b or b.get("asof") != date.today().isoformat():
        yahoo_prices(sym)
        b = jload(f) or {}
    return b.get("vol", {}) or {}


def px_at(px: dict, day: str):
    ks = [k for k in px if k <= day]
    return px[max(ks)] if ks else None




# ═══════════════════════════════════════════════════════ 섹터
SECTOR_FILE = DATA / "sectors.json"
SECTOR_KR = {
    "Technology": "기술", "Healthcare": "헬스케어", "Financial Services": "금융",
    "Consumer Cyclical": "경기소비", "Consumer Defensive": "필수소비", "Communication Services": "통신·미디어",
    "Industrials": "산업재", "Energy": "에너지", "Basic Materials": "소재", "Real Estate": "부동산",
    "Utilities": "유틸리티",
}
SECTOR_DEFAULT = {  # 조회 실패 시 대비용 (자주 등장하는 종목)
    "AAPL": "기술", "MSFT": "기술", "NVDA": "기술", "AMD": "기술", "AVGO": "기술", "TSM": "기술", "KLAC": "기술",
    "MU": "기술", "INTC": "기술", "ORCL": "기술", "CRM": "기술", "ADBE": "기술", "NOW": "기술", "SNOW": "기술",
    "PLTR": "기술", "ARM": "기술", "MRVL": "기술", "ON": "기술", "TXN": "기술", "STM": "기술", "MXL": "기술",
    "ARW": "기술", "SANM": "기술", "ALAB": "기술", "CRDO": "기술", "NBIS": "기술", "CRWV": "기술",
    "GOOGL": "통신·미디어", "GOOG": "통신·미디어", "META": "통신·미디어", "NFLX": "통신·미디어", "RDDT": "통신·미디어",
    "AMZN": "경기소비", "TSLA": "경기소비", "CVNA": "경기소비", "HD": "경기소비", "NKE": "경기소비", "ABNB": "경기소비",
    "LLY": "헬스케어", "UNH": "헬스케어", "JNJ": "헬스케어", "MRK": "헬스케어", "INSM": "헬스케어", "APLS": "헬스케어",
    "BSX": "헬스케어", "RVMD": "헬스케어", "ILMN": "헬스케어", "VRTX": "헬스케어", "REGN": "헬스케어", "TERN": "헬스케어",
    "CNTA": "헬스케어", "MDGL": "헬스케어", "ZYME": "헬스케어", "SRRK": "헬스케어", "GH": "헬스케어",
    "JPM": "금융", "BAC": "금융", "WFC": "금융", "GS": "금융", "MS": "금융", "V": "금융", "MA": "금융", "AXP": "금융",
    "BRK.B": "금융", "BRK.A": "금융", "SCHW": "금융", "COF": "금융", "SPGI": "금융", "CME": "금융",
    "XOM": "에너지", "CVX": "에너지", "OXY": "에너지", "COP": "에너지", "RIG": "에너지", "DVN": "에너지",
    "HCC": "소재", "AMR": "소재", "BTU": "에너지", "FCX": "소재", "NEM": "소재", "GOLD": "소재", "ORLA": "소재",
    "KO": "필수소비", "PEP": "필수소비", "PG": "필수소비", "WMT": "필수소비", "COST": "필수소비", "KHC": "필수소비",
    "CAT": "산업재", "GE": "산업재", "UNP": "산업재", "DAL": "산업재", "UAL": "산업재", "BA": "산업재", "RTX": "산업재",
    "SPY": "ETF", "QQQ": "ETF", "IWM": "ETF", "VOO": "ETF", "GLD": "ETF", "XBI": "ETF", "SMH": "ETF",
}


def sectors_for(syms):
    """{sym: 섹터명}. 야후 검색 API로 채우고 파일에 캐시. 실패하면 기본표, 그래도 없으면 '기타'."""
    cache = jload(SECTOR_FILE, {}) or {}
    todo = [s for s in dict.fromkeys(syms) if s not in cache]
    for i, s in enumerate(todo):
        sec = SECTOR_DEFAULT.get(s, "")
        if not sec:
            try:
                r = YF.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={s}&quotesCount=3&newsCount=0",
                           timeout=20, headers={"User-Agent": YF_UAS[_yf_ua["i"]]})
                if r.status_code == 200:
                    for q in r.json().get("quotes", []):
                        if q.get("symbol", "").upper() == s and q.get("sector"):
                            sec = SECTOR_KR.get(q["sector"], q["sector"])
                            break
            except Exception:
                pass
            time.sleep(0.25)
        cache[s] = sec or "기타"
        if (i + 1) % 25 == 0:
            jsave(SECTOR_FILE, cache)
    jsave(SECTOR_FILE, cache)
    return {s: cache.get(s, "기타") for s in syms}


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
    agg, names, buys = {}, {}, {}
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

        # 펀드 품질 가중치: 수익률 순위가 높을수록 그 펀드의 한 표가 무겁다 (1.0 ~ 2.5)
        qw = 1.0 + 1.5 * max(0.0, 1 - (w.get("rank", TOP_N) - 1) / max(1, TOP_N))

        # 분기별 주식수 변화 → 고래 평균 매입단가 추정용 (오래된 분기부터)
        for i in range(len(qs) - 1, 0, -1):
            q_lab, _, hs_now = qs[i - 1]
            _, _, hs_bef = qs[i]
            qe_day = quarter_end(q_lab)
            for sym, h in hs_now.items():
                before = (hs_bef.get(sym) or {}).get("shares", 0.0)
                d_sh = h["shares"] - before
                if d_sh > 0 and qe_day:
                    buys.setdefault(sym, []).append((q_lab, qe_day, d_sh))

        cur = qs[0][2]
        prev = qs[1][2] if len(qs) > 1 else {}
        fund_total = sum(h["value"] for h in cur.values()) or 1.0
        for sym, h in cur.items():
            a = agg.setdefault(sym, {"holders": [], "new": [], "exit": [],
                                     "add": [], "cut": [], "shares": 0.0, "value": 0.0,
                                     "weights": [], "wscore": 0.0, "new_by": []})
            a["holders"].append(w["name"])
            a["shares"] += h["shares"]
            a["value"] += h["value"]
            a["weights"].append(h["value"] / fund_total * 100)
            p = prev.get(sym)
            if not p or p["shares"] <= 0:
                if prev:
                    a["new"].append(w["name"])
                    a["new_by"].append((w["name"], w.get("rank", 99), w.get("ret_1y", 0.0)))
                    a["wscore"] += qw
            elif h["shares"] > p["shares"] * 1.05:
                a["add"].append(w["name"])
                a["wscore"] += qw * 0.6      # 추가 매수는 신규 편입보다 가볍게
            elif h["shares"] < p["shares"] * 0.95:
                a["cut"].append(w["name"])
                a["wscore"] -= qw * 0.6
            names.setdefault(sym, h["issuer"])
        for sym, p in prev.items():
            if sym not in cur:
                a = agg.setdefault(sym, {"holders": [], "new": [], "exit": [],
                                         "add": [], "cut": [], "shares": 0.0, "value": 0.0,
                                         "weights": [], "wscore": 0.0, "new_by": []})
                a["exit"].append(w["name"])
                a["wscore"] -= qw
                names.setdefault(sym, p["issuer"])

    jsave(DATA / "history.json", hist)
    for sym, a in agg.items():
        a["name"] = names.get(sym, "")
        a["sym"] = sym
        a["n_hold"] = len(a["holders"])
        a["n_in"] = len(a["new"]) + len(a["add"])      # 편입 = 신규 + 증가
        a["n_out"] = len(a["exit"]) + len(a["cut"])    # 편출 = 전량매도 + 축소
        a["score"] = a["n_in"] - a["n_out"]
        ws = a.get("weights") or []
        a["avg_w"] = sum(ws) / len(ws) if ws else 0.0            # 보유 펀드 내 평균 비중(%)
        a["conviction"] = round(sum(ws), 1)                     # 비중 합 = 확신도 점수
        a["wscore"] = round(a.get("wscore", 0.0), 1)            # 수익률 가중 순증감
        a["cluster"] = len(a["new"])                            # 같은 분기 동시 신규 편입 수
        nb = sorted(a.get("new_by") or [], key=lambda x: x[1])
        a["cluster_top"] = [n for n, _, _ in nb[:3]]            # 그중 성적 좋은 곳
        a["cluster_ret"] = (sum(r for _, _, r in nb) / len(nb)) if nb else 0.0
    add_cost_basis(agg, buys)
    add_exit_velocity(agg, hist)
    return agg, hist


def add_cost_basis(agg, buys):
    """분기별 순매수 주식수 × 그 분기 평균가 → 고래들의 가중평균 매입단가 추정."""
    for sym, lots in buys.items():
        a = agg.get(sym)
        if not a:
            continue
        px = yahoo_prices(sym)
        if len(px) < 30:
            continue
        cost = shares = 0.0
        qs_used = set()
        for q_lab, qe_day, d_sh in lots:
            # 그 분기(끝나는 날 기준 직전 90일)의 평균 종가
            lo = (date.fromisoformat(qe_day) - timedelta(days=90)).isoformat()
            vals = [v for k, v in px.items() if lo <= k <= qe_day]
            if not vals:
                continue
            avg = sum(vals) / len(vals)
            cost += avg * d_sh
            shares += d_sh
            qs_used.add(q_lab)
        if shares > 0:
            a["cost_basis"] = cost / shares
            a["cost_quarters"] = len(qs_used)


def add_exit_velocity(agg, hist):
    """보유 펀드 수가 몇 분기 연속 줄었나 / 늘었나. 1분기짜리 잡음과 추세를 구분."""
    for sym, a in agg.items():
        s = [v for _, v in series_of(hist, sym, "h")]
        s = [v for v in s if v > 0]
        a["streak"] = 0
        if len(s) < 3:
            continue
        run = 0
        for i in range(len(s) - 1, 0, -1):
            d = s[i] - s[i - 1]
            if d < 0 and run <= 0:
                run -= 1
            elif d > 0 and run >= 0:
                run += 1
            else:
                break
        a["streak"] = run


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






# ═══════════════════════════════════════ 실전 분석 (사분면 · 매수가 · 컨빅션 · 급등 · 섹터 · 인덱스)
def latest_quarter_end(agg_watch_quarter):
    """'Q2 2026' → 2026-06-30"""
    return quarter_end(agg_watch_quarter) or ""


def price_context(agg, quarter_label, min_hold=3):
    """종목별 가격 맥락: 1년 수익률, 분기말(고래 보유 시점) 대비 현재, 전일 등락, 거래량 배율."""
    qe = latest_quarter_end(quarter_label)
    start_1y = (date.today() - timedelta(days=365)).isoformat()
    out = {}
    syms = [s for s, a in agg.items() if a["n_hold"] >= min_hold or a["n_in"] >= 3 or a["n_out"] >= 3]
    for i, sym in enumerate(syms):
        px = yahoo_prices(sym)
        if len(px) < 30:
            continue
        days = sorted(px)
        last, prev_d = days[-1], days[-2]
        cur = px[last]
        p1y = px_at(px, start_1y)
        pqe = px_at(px, qe) if qe else None
        vol = yahoo_volume(sym)
        vdays = sorted(k for k in vol if k <= last)
        v_last = vol.get(last, 0)
        v_avg = (sum(vol[k] for k in vdays[-21:-1]) / max(1, len(vdays[-21:-1]))) if len(vdays) > 5 else 0
        out[sym] = {
            "last": cur, "date": last,
            "ret_1y": (cur / p1y - 1) * 100 if p1y else None,
            "vs_qe": (cur / pqe - 1) * 100 if pqe else None,       # 분기말 가격 대비
            "ret_1d": (cur / px[prev_d] - 1) * 100 if px.get(prev_d) else None,
            "vol_ratio": (v_last / v_avg) if v_avg else None,
        }
        if (i + 1) % 100 == 0:
            log(f"  가격 맥락 {i + 1}/{len(syms)}")
    return out, qe


def quadrant(agg, pc):
    """사분면 분류. 편입 순증감 × 1년 주가."""
    Q = {"contra": [], "chase": [], "flee": [], "profit": []}
    for sym, a in agg.items():
        c = pc.get(sym)
        if not c or c["ret_1y"] is None or abs(a["score"]) < 2:
            continue
        row = {**a, **c}
        if a["score"] > 0:
            Q["contra" if c["ret_1y"] < 0 else "chase"].append(row)
        else:
            Q["flee" if c["ret_1y"] < 0 else "profit"].append(row)
    for k in Q:
        Q[k].sort(key=lambda r: (-abs(r["score"]), -r["n_hold"]))
    return Q


def discount_list(agg, pc, n=10):
    """고래 보유 시점(분기말) 대비 지금 더 싼 종목 — 편입 우세인 것만."""
    rows = [{**a, **pc[s]} for s, a in agg.items()
            if s in pc and pc[s]["vs_qe"] is not None and a["score"] >= 2 and a["n_hold"] >= 3]
    rows.sort(key=lambda r: r["vs_qe"])
    return rows[:n]


def conviction_list(agg, n=10):
    rows = [a for a in agg.values() if a["n_hold"] >= 3]
    rows.sort(key=lambda a: -a["conviction"])
    return rows[:n]


def movers(agg, pc, n=10):
    """전일 의미 있는 움직임: |등락| 3% 이상 또는 거래량 20일 평균의 2배 이상. 고래 보유 3곳 이상."""
    rows = []
    for sym, a in agg.items():
        c = pc.get(sym)
        if not c or a["n_hold"] < 3 or c["ret_1d"] is None:
            continue
        big_move = abs(c["ret_1d"]) >= 3.0
        big_vol = (c["vol_ratio"] or 0) >= 2.0
        if big_move or big_vol:
            rows.append({**a, **c, "why": ("등락" if big_move else "") + ("·" if big_move and big_vol else "")
                         + ("거래량" if big_vol else "")})
    rows.sort(key=lambda r: -(abs(r["ret_1d"]) + 2 * max(0, (r["vol_ratio"] or 0) - 1)))
    return rows[:n]


def sector_flow(agg, pc, top=9):
    """섹터별 편입/편출 순증감 합계와 대표 종목."""
    syms = [s for s, a in agg.items() if a["n_in"] + a["n_out"] >= 2]
    sec = sectors_for(syms)
    S = {}
    for s in syms:
        k = sec.get(s, "기타")
        d = S.setdefault(k, {"sector": k, "in": 0, "out": 0, "score": 0, "n": 0, "syms": []})
        d["in"] += agg[s]["n_in"]; d["out"] += agg[s]["n_out"]; d["score"] += agg[s]["score"]; d["n"] += 1
        d["syms"].append((agg[s]["score"], s))
    rows = sorted(S.values(), key=lambda d: -d["score"])
    for d in rows:
        d["syms"] = [s for _, s in sorted(d["syms"], reverse=True)[:3]]
    return rows[:top]


INDEX_FILE = DATA / "index.json"


def whale_index(agg, pc):
    """컨빅션 상위 10종목 동일비중 가상 포트. 매일 값을 기록하고 SPY와 비교한다."""
    picks = [a["sym"] for a in conviction_list(agg, 10)]
    spy = yahoo_prices("SPY")
    if not picks or not spy:
        return None
    days = sorted(spy)
    start_1y = (date.today() - timedelta(days=365)).isoformat()
    def basket_ret(a_day, b_day):
        rs = []
        for s in picks:
            px = yahoo_prices(s)
            p0, p1 = px_at(px, a_day), px_at(px, b_day)
            if p0 and p1:
                rs.append(p1 / p0 - 1)
        return (sum(rs) / len(rs) * 100) if rs else None
    last, prev_d = days[-1], days[-2]
    r1d = basket_ret(prev_d, last)
    r1y = basket_ret(start_1y, last)
    s1d = (spy[last] / spy[prev_d] - 1) * 100
    s1y = (spy[last] / px_at(spy, start_1y) - 1) * 100 if px_at(spy, start_1y) else None
    hist = jload(INDEX_FILE, {}) or {}
    hist[date.today().isoformat()] = {"r1d": r1d, "r1y": r1y, "s1d": s1d, "s1y": s1y, "picks": picks}
    jsave(INDEX_FILE, dict(sorted(hist.items())[-400:]))
    return {"picks": picks, "r1d": r1d, "r1y": r1y, "s1d": s1d, "s1y": s1y, "as_of": last, "hist": hist}




# ═══════════════════════════════ SEC EDGAR 실시간 공시 (Form 4 · 13D/G)
# 13F는 분기말 후 45일에 나온다. 그 공백을 메우는 자료:
#   Form 4  — 임원·10% 이상 주주의 매매, 거래 후 2영업일 내
#   13D/13G — 5% 이상 지분 취득·변동, 5영업일 내
SEC_UA = os.environ.get("SEC_USER_AGENT", "whale40 research whale40@example.com")
SEC = requests.Session()
SEC.headers.update({"User-Agent": SEC_UA, "Accept-Encoding": "gzip, deflate",
                    "Host": "www.sec.gov"})
CIKFILE = DATA / "ciks.json"
EDGAR_DAYS = 5            # 며칠치 공시를 훑을지
_sec_last = {"t": 0.0}


def sec_get(url, timeout=40):
    """SEC는 초당 10건 제한. 간격을 지키며 가져온다."""
    gap = time.time() - _sec_last["t"]
    if gap < 0.15:
        time.sleep(0.15 - gap)
    _sec_last["t"] = time.time()
    try:
        r = SEC.get(url, timeout=timeout, headers={"Host": "www.sec.gov"})
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def cik_map(watch):
    """감시 대상 이름 → CIK. SEC 회사명 목록을 한 번 받아 캐시한다."""
    cache = jload(CIKFILE, {}) or {}
    todo = [w for w in watch if w["name"] not in cache]
    if not todo:
        return {n: c for n, c in cache.items() if c}
    r = sec_get("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt", timeout=120)
    if not r:
        log("  CIK 목록을 받지 못해 EDGAR 감시를 건너뜁니다")
        return {n: c for n, c in cache.items() if c}
    table = []
    for line in r.text.splitlines():
        p = line.rstrip(":").rsplit(":", 1)
        if len(p) == 2 and p[1].isdigit():
            table.append((norm(p[0]), p[1].lstrip("0")))
    log(f"  SEC 회사명 {len(table):,}개 로드")
    for w in todo:
        # 13f.info 표시명을 SEC 등록명에 맞춰본다: 완전일치 → 접두일치
        key = norm(re.sub(r"\b(LP|LLC|INC|LTD|CO|CORP|GROUP|ADVISORS?|MANAGEMENT|CAPITAL)\b\.?", "",
                          w.get("sec_name") or w["name"], flags=re.I)).strip()
        full = norm(w.get("sec_name") or w["name"])
        hit = next((c for n, c in table if n == full), None)
        if not hit and len(key) >= 5:
            cands = [(n, c) for n, c in table if n.startswith(key)]
            if len(cands) == 1 or (cands and len(cands) <= 4):
                hit = sorted(cands, key=lambda x: len(x[0]))[0][1]
        cache[w["name"]] = hit or ""
    jsave(CIKFILE, cache)
    found = sum(1 for v in cache.values() if v)
    log(f"  CIK 확인 {found}/{len(cache)}곳")
    return {n: c for n, c in cache.items() if c}


def daily_index_rows(days=EDGAR_DAYS):
    """최근 며칠간 EDGAR 일별 색인. [(form, cik, 회사명, 접수일, 문서경로)]"""
    rows, got, d, tries = [], 0, date.today(), 0
    while got < days and tries < 16:
        tries += 1
        if d.weekday() < 5:
            q = (d.month - 1) // 3 + 1
            r = sec_get(f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{q}/"
                        f"form.{d.strftime('%Y%m%d')}.idx")
            if r:
                got += 1
                for line in r.text.splitlines():
                    parts = re.split(r"\s{2,}", line.strip())
                    if len(parts) >= 5 and parts[-1].startswith("edgar/data/"):
                        form, name, cik, filed = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
                        if cik.isdigit() and (form == "4" or form.upper().startswith("SC 13")):
                            rows.append((form, cik.lstrip("0"), name, filed, parts[-1]))
        d -= timedelta(days=1)
    return rows


def parse_form4(path):
    """Form 4 문서에서 매수 거래만 뽑는다. [{sym, issuer, shares, price, when}]"""
    base = "https://www.sec.gov/Archives/" + path.rsplit("/", 1)[0]
    acc = path.rsplit("/", 1)[-1].replace(".txt", "").replace("-", "")
    r = sec_get(f"{base}/{acc}/") or sec_get("https://www.sec.gov/Archives/" + path)
    if not r:
        return []
    xml = None
    if "<ownershipDocument" in r.text:
        xml = r.text
    else:
        m = re.findall(r'href="([^"]+\.xml)"', r.text, re.I)
        for u in m:
            rr = sec_get("https://www.sec.gov" + u if u.startswith("/") else f"{base}/{acc}/{u}")
            if rr and "<ownershipDocument" in rr.text:
                xml = rr.text
                break
    if not xml:
        return []
    def tag(s, t):
        m = re.search(rf"<{t}>\s*(?:<value>)?\s*([^<]+)", s)
        return m.group(1).strip() if m else ""
    sym = tag(xml, "issuerTradingSymbol").upper()
    issuer = tag(xml, "issuerName")
    out = []
    for blk in re.findall(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>", xml, re.S):
        if tag(blk, "transactionAcquiredDisposedCode") != "A":
            continue
        code = tag(blk, "transactionCode")
        if code not in ("P", "A"):       # P=공개시장 매수, A=수여
            continue
        sh = num(tag(blk, "transactionShares"))
        pr = num(tag(blk, "transactionPricePerShare"))
        if sh and sh > 0:
            out.append({"sym": sym, "issuer": issuer, "shares": sh, "price": pr,
                        "when": tag(blk, "transactionDate"), "code": code})
    return out


def parse_sc13(path):
    """13D/13G에서 대상 회사와 지분율."""
    r = sec_get("https://www.sec.gov/Archives/" + path)
    if not r:
        return None
    t = r.text[:200000]
    sub = re.search(r"SUBJECT COMPANY:.*?COMPANY CONFORMED NAME:\s*(.+)", t, re.S)
    pct = None
    for pat in (r"(?:PERCENT OF CLASS|Percent of [Cc]lass)[\s\S]{0,160}?(\d{1,2}(?:\.\d+)?)\s*%",
                r"<percentOfClass>\s*(?:<value>)?\s*(\d{1,2}(?:\.\d+)?)"):
        m = re.search(pat, t)
        if m:
            pct = float(m.group(1))
            break
    sym = re.search(r"\(Title of Class[^)]*\)|TRADING SYMBOL:\s*([A-Z.]{1,6})", t)
    return {"issuer": (sub.group(1).strip().splitlines()[0] if sub else ""),
            "pct": pct,
            "sym": (sym.group(1) if sym and sym.group(1) else "")}


def edgar_live(watch, days=EDGAR_DAYS):
    """감시 대상 40곳이 최근 며칠 안에 낸 Form 4 매수 · 13D/G. 13F의 45일 공백을 메운다."""
    seen = set(jload(DATA / "seen_edgar.json", []) or [])
    try:
        ciks = cik_map(watch)
    except Exception as e:
        log(f"  CIK 조회 실패, EDGAR 건너뜀: {type(e).__name__}: {e}")
        return []
    if not ciks:
        return []
    by_cik = {c: w for w in watch for n, c in ciks.items() if n == w["name"]}
    try:
        rows = daily_index_rows(days)
    except Exception as e:
        log(f"  EDGAR 색인 실패: {type(e).__name__}: {e}")
        return []
    log(f"  EDGAR 최근 {days}영업일 공시 {len(rows):,}건 확인")
    out, fresh = [], []
    for form, cik, cname, filed, path in rows:
        w = by_cik.get(cik)
        if not w or path in seen:
            continue
        f = form.upper()
        try:
            if f == "4":
                for t in parse_form4(path):
                    if t["code"] == "P" or t["shares"] * (t["price"] or 0) > 1e6:
                        out.append({"kind": "Form 4", "who": w["name"], "group": w["group"],
                                    "rank": w.get("rank", 99), "filed": filed, **t})
            elif f.startswith("SC 13"):
                d = parse_sc13(path)
                if d and d["issuer"]:
                    out.append({"kind": f.replace("SC ", ""), "who": w["name"], "group": w["group"],
                                "rank": w.get("rank", 99), "filed": filed,
                                "sym": d["sym"], "issuer": d["issuer"], "pct": d["pct"],
                                "shares": 0, "price": 0, "when": filed})
        except Exception:
            continue
        fresh.append(path)
    jsave(DATA / "seen_edgar.json", sorted(set(list(seen) + fresh))[-8000:])
    out.sort(key=lambda x: (x["filed"], -0), reverse=True)
    log(f"  실시간 신호 {len(out)}건 (Form 4 매수 · 13D/G)")
    return out[:30]


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






# ══════════════════════════════════ 검증 · 일정 · 파생 목록
EARN_FILE = DATA / "earnings.json"


def earnings_soon(syms, days=9):
    """며칠 안에 실적 발표가 있는 종목. 야후 quote API, 실패하면 조용히 빈 값."""
    cache = jload(EARN_FILE, {}) or {}
    stamp = cache.get("_asof")
    if stamp != date.today().isoformat():
        cache = {"_asof": date.today().isoformat()}
        syms_u = list(dict.fromkeys(syms))
        for i in range(0, len(syms_u), 40):
            batch = ",".join(syms_u[i:i + 40])
            try:
                r = YF.get(f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={batch}",
                           timeout=25, headers={"User-Agent": YF_UAS[_yf_ua["i"]]})
                if r.status_code != 200:
                    continue
                for q in ((r.json().get("quoteResponse") or {}).get("result") or []):
                    ts = q.get("earningsTimestampStart") or q.get("earningsTimestamp")
                    if q.get("symbol") and ts:
                        cache[q["symbol"]] = datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
            except (requests.RequestException, ValueError, KeyError, TypeError):
                continue
            time.sleep(0.2)
        jsave(EARN_FILE, cache)
    today = date.today()
    lim = (today + timedelta(days=days)).isoformat()
    out = {}
    for s in syms:
        d = cache.get(s)
        if d and today.isoformat() <= d <= lim:
            out[s] = d
    return out


def earnings_rows(agg, pc, n=10):
    """고래가 많이 든 종목 중 이번 주 실적 발표. 행동 시점이 잡힌다."""
    cands = [a for a in agg.values() if a["n_hold"] >= 3]
    cal = earnings_soon([a["sym"] for a in cands])
    rows = []
    for a in cands:
        d = cal.get(a["sym"])
        if not d:
            continue
        c = pc.get(a["sym"], {})
        rows.append({**a, **c, "earn": d,
                     "dday": (date.fromisoformat(d) - date.today()).days})
    rows.sort(key=lambda r: (r["dday"], -r["n_hold"]))
    return rows[:n]


def cluster_rows(agg, pc, min_n=3, n=10):
    """같은 분기에 여러 곳이 '동시에 신규' 편입한 종목. 합의가 막 생기는 지점."""
    rows = [{**a, **pc.get(a["sym"], {})} for a in agg.values() if a.get("cluster", 0) >= min_n]
    rows.sort(key=lambda r: (-r["cluster"], -r.get("wscore", 0)))
    return rows[:n]


def cost_rows(agg, pc, n=10):
    """고래 추정 평단 대비 현재가. 음수면 고래보다 싸게 살 수 있다."""
    rows = []
    for a in agg.values():
        c = pc.get(a["sym"])
        if not c or not a.get("cost_basis") or a["n_hold"] < 3:
            continue
        gap = (c["last"] / a["cost_basis"] - 1) * 100
        rows.append({**a, **c, "gap": gap})
    rows.sort(key=lambda r: r["gap"])
    return rows[:n]


def warning_rows(agg, pc, n=10):
    """보유 중이라면 경고: 연속 이탈 추세 + 가중 순증감 음수."""
    rows = []
    for a in agg.values():
        if a.get("streak", 0) <= -2 and a.get("wscore", 0) < 0:
            rows.append({**a, **pc.get(a["sym"], {})})
    rows.sort(key=lambda r: (r["streak"], r.get("wscore", 0)))
    return rows[:n]


BACKTEST_FILE = DATA / "backtest.json"


def backtest(agg, hist, lag_q=2):
    """과거 분기에 각 구역이던 종목들이 그 뒤 실제로 어떻게 됐나.
    보유 펀드 수 변화로 매집/이탈을, 직전 6개월 주가로 상승/하락을 나눈 뒤
    그 분기말부터 지금까지의 수익률을 구역별로 평균낸다."""
    qs = sorted({q for q in hist}, key=qsort_key)
    if len(qs) < lag_q + 2:
        return None
    base_q = qs[-(lag_q + 1)]           # 평가 기준 분기 (lag_q 분기 전)
    prev_q = qs[-(lag_q + 2)]
    qe = quarter_end(base_q)
    if not qe:
        return None
    buckets = {"contra": [], "chase": [], "flee": [], "profit": []}
    for sym in hist.get(base_q, {}):
        now_h = hist[base_q].get(sym, {}).get("h", 0)
        old_h = hist.get(prev_q, {}).get(sym, {}).get("h", 0)
        d = now_h - old_h
        if abs(d) < 2 or now_h < 3:
            continue
        px = yahoo_prices(sym)
        if len(px) < 60:
            continue
        p_then = px_at(px, qe)
        days = sorted(px)
        p_before = px_at(px, (date.fromisoformat(qe) - timedelta(days=182)).isoformat())
        if not p_before and days[0] < qe:
            p_before = px[days[0]]          # 6개월치가 없으면 가진 것 중 가장 오래된 값
        p_now = px[days[-1]]
        if not p_then or not p_before or p_then <= 0:
            continue
        past = (p_then / p_before - 1) * 100
        fwd = (p_now / p_then - 1) * 100
        k = ("contra" if past < 0 else "chase") if d > 0 else ("flee" if past < 0 else "profit")
        buckets[k].append((sym, fwd))
    spy = yahoo_prices("SPY")
    bench = None
    if spy:
        a_, b_ = px_at(spy, qe), spy[sorted(spy)[-1]]
        if a_ and b_:
            bench = (b_ / a_ - 1) * 100
    out = {"quarter": base_q, "from": qe, "bench": bench, "zones": {}}
    for k, v in buckets.items():
        if v:
            avg = sum(x for _, x in v) / len(v)
            win = sum(1 for _, x in v if x > (bench or 0)) / len(v) * 100
            best = max(v, key=lambda x: x[1])
            out["zones"][k] = {"n": len(v), "avg": avg, "win": win, "best": best[0], "best_r": best[1]}
    jsave(BACKTEST_FILE, out)
    return out if out["zones"] else None


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


DAYDIR = DATA / "days"


def save_daystate(state):
    """오늘 상태를 날짜별 파일로 저장. 같은 날 다시 돌리면 덮어쓴다."""
    DAYDIR.mkdir(parents=True, exist_ok=True)
    jsave(DAYDIR / f"{state['date']}.json", state)
    # 60일 넘은 것은 정리
    keep = sorted(p for p in DAYDIR.glob("*.json"))
    for p in keep[:-60]:
        p.unlink()


def load_prevday():
    """오늘보다 이전 날짜 중 가장 최근 상태. 같은 날 재실행해도 어제와 비교된다."""
    today = date.today().isoformat()
    if DAYDIR.exists():
        cands = sorted(p.stem for p in DAYDIR.glob("*.json") if p.stem < today)
        if cands:
            return jload(DAYDIR / f"{cands[-1]}.json", {}) or {}
    old = jload(DAYFILE, {}) or {}          # 예전 방식 파일과의 호환
    return old if old.get("date", "") < today else {}


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



# ══════════════════════════════════════════ 한 장 대시보드 (차트 중심)
def next_13f_deadline(today=None):
    """다음 13F 마감일과 남은 일수. (분기말 후 45일: 2/14, 5/15, 8/14, 11/14 전후)"""
    today = today or date.today()
    cands = []
    for y in (today.year, today.year + 1):
        for m, d in ((2, 14), (5, 15), (8, 14), (11, 14)):
            cands.append(date(y, m, d))
    nxt = min(c for c in cands if c >= today)
    return nxt, (nxt - today).days


def headlines(inst, ppl, agg, items, hits, prev):
    """오늘 리포트에서 사람이 읽을 만한 한 줄 요약들을 뽑는다."""
    H = []
    con = top_consensus(agg, 3)
    if con:
        a = con[0]
        H.append(f"감시 40곳 중 <b>{a['n_hold']}곳</b>이 <b>{stock_label(a['sym'], a['name'])}</b> 보유 — 가장 넓게 퍼진 종목")
    flow = [r for r in top_flow(agg, 3, "in") if r["score"] > 0]
    if flow:
        a = flow[0]
        H.append(f"이번 분기 가장 강한 쏠림: <b>{stock_label(a['sym'], a['name'])}</b> 편입 {a['n_in']}곳 · 편출 {a['n_out']}곳")
    out = [r for r in top_flow(agg, 3, "out") if r["score"] < 0]
    if out:
        a = out[0]
        H.append(f"가장 많이 빠져나간 종목: <b>{stock_label(a['sym'], a['name'])}</b> 편출 {a['n_out']}곳")
    if inst:
        H.append(f"기관 1위 <b>{inst[0]['name']}</b> 1년 {inst[0]['ret_1y']:+.1f}% · "
                 f"TOP {TOP_N} 평균 {sum(r['ret_1y'] for r in inst[:TOP_N]) / min(TOP_N, len(inst)):+.1f}%")
    if ppl:
        H.append(f"유명인 1위 <b>{ppl[0]['name']}</b> 1년 {ppl[0]['ret_1y']:+.1f}% · "
                 f"TOP {TOP_N} 평균 {sum(r['ret_1y'] for r in ppl[:TOP_N]) / min(TOP_N, len(ppl)):+.1f}%")
    if items["rank"]:
        ups = [r for r in items["rank"] if r["kind"] == "up"]
        news = [r for r in items["rank"] if r["kind"] == "new"]
        if news:
            H.append(f"TOP {TOP_N} 신규 진입: <b>{', '.join(r['name'] for r in news[:3])}</b>")
        if ups:
            r = ups[0]
            H.append(f"전일 대비 가장 크게 오른 순위: <b>{r['name']}</b> ▲{r['move']}")
    if hits:
        H.append(f"새 13F 공시 <b>{len(hits)}건</b> — {', '.join(h['name'] for h in hits[:3])}")
    nxt, days = next_13f_deadline()
    H.append(f"다음 13F 마감 <b>{nxt.month}월 {nxt.day}일</b> · {days}일 뒤 — 그때 편입·편출이 대량 갱신됩니다")
    return H[:5]


def make_dashboard_pdf(path, inst, ppl, agg, hist, details, hits, items, prev):
    """A4 한 장. 차트 6개 + 헤드라인. 변화가 없는 날에도 볼 것이 있게."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.graphics.shapes import Drawing, String, Rect, Line, PolyLine
        from reportlab.graphics.charts.barcharts import HorizontalBarChart
        from reportlab.graphics.charts.piecharts import Pie
    except ImportError:
        return None
    KRF = register_korean_font()
    if not KRF:
        return None

    ACC = colors.HexColor("#2d6a4f"); MUT = colors.HexColor("#6f6b64")
    LINE = colors.HexColor("#dcd8cd"); PAPER = colors.HexColor("#f7f5f0")
    UP, DOWN, NEW = colors.HexColor("#c0392b"), colors.HexColor("#1d6fb8"), colors.HexColor("#7b3fa0")
    PAL = [colors.HexColor(c) for c in
           ("#2d6a4f", "#b4451f", "#2b6cb0", "#8a5a00", "#6b46c1", "#0f766e", "#9d174d", "#4d7c0f")]

    H1 = ParagraphStyle("h1", fontName=KRF, fontSize=16, leading=19)
    SUB = ParagraphStyle("sub", fontName=KRF, fontSize=7.6, leading=10.5, textColor=MUT)
    H2 = ParagraphStyle("h2", fontName=KRF, fontSize=8.8, leading=11, textColor=ACC)
    BUL = ParagraphStyle("bul", fontName=KRF, fontSize=7.9, leading=11.2, leftIndent=8, bulletIndent=0)
    SM = ParagraphStyle("sm", fontName=KRF, fontSize=6.6, leading=9, textColor=MUT)

    W = 190 * mm     # 내용 폭
    COL = 93 * mm    # 2단 폭

    def title(txt):
        return Paragraph(txt, H2)

    # ── 차트 1·2: 순위 TOP 10 수익률 가로 막대 (전일 대비 색) ──
    def rank_chart(rows, gkey):
        rows = rows[:10]
        d = Drawing(COL, 54 * mm)
        if not rows:
            return d
        ch = HorizontalBarChart()
        ch.x, ch.y, ch.width, ch.height = 40 * mm, 4 * mm, 44 * mm, 47 * mm
        vals = [r["ret_1y"] for r in rows][::-1]
        ch.data = [vals]
        ch.categoryAxis.categoryNames = [f"{r['rank']}. {r['name'][:13]}" for r in rows][::-1]
        ch.categoryAxis.labels.fontName = KRF
        ch.categoryAxis.labels.fontSize = 6.2
        ch.categoryAxis.labels.dx = -2
        ch.categoryAxis.strokeColor = LINE
        ch.valueAxis.labels.fontName = KRF
        ch.valueAxis.labels.fontSize = 5.8
        ch.valueAxis.valueMin = min(0, min(vals)) if vals else 0
        ch.valueAxis.labelTextFormat = "%d%%"
        ch.valueAxis.strokeColor = LINE
        ch.valueAxis.gridStrokeColor = PAPER
        ch.valueAxis.visibleGrid = True
        ch.bars.strokeWidth = 0
        ch.barWidth = 6
        for i, r in enumerate(rows[::-1]):
            _, kind = rank_mark(prev, gkey, r["name"], r["rank"])
            ch.bars[(0, i)].fillColor = {"up": UP, "down": DOWN, "new": NEW}.get(kind, ACC)
        d.add(ch)
        # 값 라벨
        for i, r in enumerate(rows[::-1]):
            y = ch.y + (i + 0.5) * (ch.height / len(rows))
            frac = (r["ret_1y"] - ch.valueAxis.valueMin) / max(1e-9, (max(vals) - ch.valueAxis.valueMin))
            x = ch.x + frac * ch.width + 1.5 * mm
            d.add(String(min(x, ch.x + ch.width - 8 * mm), y - 1.8, f"{r['ret_1y']:+.0f}%",
                         fontName=KRF, fontSize=5.8, fillColor=MUT))
        return d

    # ── 차트 3: 공동 보유 TOP 10 ──
    def consensus_chart(con):
        con = con[:10]
        d = Drawing(COL, 50 * mm)
        if not con:
            return d
        ch = HorizontalBarChart()
        ch.x, ch.y, ch.width, ch.height = 40 * mm, 4 * mm, 46 * mm, 43 * mm
        vals = [a["n_hold"] for a in con][::-1]
        ch.data = [vals]
        ch.categoryAxis.categoryNames = [stock_label(a["sym"], a["name"])[:16] for a in con][::-1]
        ch.categoryAxis.labels.fontName = KRF
        ch.categoryAxis.labels.fontSize = 6.2
        ch.categoryAxis.labels.dx = -2
        ch.categoryAxis.strokeColor = LINE
        ch.valueAxis.labels.fontName = KRF
        ch.valueAxis.labels.fontSize = 5.8
        ch.valueAxis.valueMin = 0
        ch.valueAxis.valueMax = max(vals) + 2
        ch.valueAxis.strokeColor = LINE
        ch.valueAxis.gridStrokeColor = PAPER
        ch.valueAxis.visibleGrid = True
        ch.bars.strokeWidth = 0
        ch.barWidth = 6
        for i, a in enumerate(con[::-1]):
            _, kind = num_mark(prev, "hold", a["sym"], a["n_hold"])
            ch.bars[(0, i)].fillColor = {"up": UP, "down": DOWN, "new": NEW}.get(kind, ACC)
        d.add(ch)
        for i, a in enumerate(con[::-1]):
            y = ch.y + (i + 0.5) * (ch.height / len(con))
            x = ch.x + (a["n_hold"] / ch.valueAxis.valueMax) * ch.width + 1.5 * mm
            d.add(String(x, y - 1.8, f"{a['n_hold']}곳", fontName=KRF, fontSize=5.8, fillColor=MUT))
        return d

    # ── 차트 4: 편입/편출 순증감 (양쪽으로 벌어지는 막대) ──
    def flow_chart(agg):
        ins = [a for a in top_flow(agg, 6, "in") if a["score"] > 0]
        outs = [a for a in top_flow(agg, 4, "out") if a["score"] < 0]
        rows = ins + outs[::-1]
        d = Drawing(COL, 50 * mm)
        if not rows:
            d.add(String(4 * mm, 24 * mm, "편입·편출 쏠림 없음", fontName=KRF, fontSize=7, fillColor=MUT))
            return d
        n = len(rows)
        top, bottom = 46 * mm, 4 * mm
        rowh = (top - bottom) / n
        cx = 46 * mm
        half = 38 * mm
        mx = max(abs(a["score"]) for a in rows) or 1
        d.add(Line(cx, bottom, cx, top, strokeColor=LINE, strokeWidth=0.6))
        for i, a in enumerate(rows):
            y = top - (i + 0.5) * rowh
            w = abs(a["score"]) / mx * half
            col = UP if a["score"] > 0 else DOWN
            x0 = cx if a["score"] > 0 else cx - w
            d.add(Rect(x0, y - rowh * 0.32, w, rowh * 0.64, fillColor=col, strokeWidth=0))
            lab = stock_label(a["sym"], a["name"])[:15]
            if a["score"] > 0:
                d.add(String(cx - 2 * mm, y - 1.8, lab, fontName=KRF, fontSize=6, textAnchor="end"))
                d.add(String(cx + w + 1.5 * mm, y - 1.8, f"+{a['score']}", fontName=KRF, fontSize=6, fillColor=col))
            else:
                d.add(String(cx + 2 * mm, y - 1.8, lab, fontName=KRF, fontSize=6))
                d.add(String(cx - w - 1.5 * mm, y - 1.8, f"{a['score']}", fontName=KRF, fontSize=6,
                             fillColor=col, textAnchor="end"))
        d.add(String(cx - half, top + 1.5 * mm, "← 편출 우세", fontName=KRF, fontSize=5.8, fillColor=DOWN))
        d.add(String(cx + half, top + 1.5 * mm, "편입 우세 →", fontName=KRF, fontSize=5.8, fillColor=UP, textAnchor="end"))
        return d

    # ── 차트 5: 1위 유명인 포트 파이 ──
    def pie_chart(dd):
        d = Drawing(COL, 48 * mm)
        if not dd or not dd.get("holdings"):
            return d
        hs = dd["holdings"][:7]
        other = max(0.0, 100 - sum(h["weight"] for h in hs))
        vals = [h["weight"] for h in hs] + ([other] if other > 0.5 else [])
        labs = [stock_label(h["sym"], h["issuer"])[:14] for h in hs] + (["기타"] if other > 0.5 else [])
        p = Pie()
        p.x, p.y, p.width, p.height = 3 * mm, 4 * mm, 40 * mm, 40 * mm
        p.data = vals
        p.labels = None
        p.slices.strokeWidth = 0.6
        p.slices.strokeColor = colors.white
        for i in range(len(vals)):
            p.slices[i].fillColor = PAL[i % len(PAL)] if labs[i] != "기타" else LINE
        d.add(p)
        # 범례
        y = 43 * mm
        for i, (l, v) in enumerate(zip(labs, vals)):
            d.add(Rect(52 * mm, y - 1.2, 3 * mm, 3 * mm,
                       fillColor=PAL[i % len(PAL)] if l != "기타" else LINE, strokeWidth=0))
            d.add(String(56.5 * mm, y - 1, f"{l}  {v:.1f}%", fontName=KRF, fontSize=6.2))
            y -= 5.4 * mm
        return d

    # ── 차트 6: 최다 편입 종목 3개의 1년 주가 ──
    def price_lines(agg):
        picks = [a for a in top_flow(agg, 3, "in") if a["score"] > 0][:3] or top_consensus(agg, 3)
        d = Drawing(COL, 48 * mm)
        if not picks:
            return d
        n = len(picks)
        h_each = 45 * mm / n
        start = (date.today() - timedelta(days=365)).isoformat()
        for i, a in enumerate(picks):
            px = yahoo_prices(a["sym"])
            ser = sorted((k, v) for k, v in px.items() if k >= start)
            y0 = 47 * mm - (i + 1) * h_each + 3 * mm
            hh = h_each - 8 * mm
            x0, ww = 30 * mm, 60 * mm
            d.add(String(2 * mm, y0 + hh / 2, stock_label(a["sym"], a["name"])[:13], fontName=KRF, fontSize=6.6))
            if len(ser) < 5:
                d.add(String(x0, y0 + hh / 2, "주가 자료 없음", fontName=KRF, fontSize=6, fillColor=MUT))
                continue
            vals = [v for _, v in ser]
            lo, hi = min(vals), max(vals)
            rng = (hi - lo) or 1
            pts = []
            for j, v in enumerate(vals):
                pts += [x0 + j / (len(vals) - 1) * ww, y0 + (v - lo) / rng * hh]
            chg = (vals[-1] / vals[0] - 1) * 100
            col = UP if chg >= 0 else DOWN
            d.add(PolyLine(pts, strokeColor=col, strokeWidth=1.1))
            d.add(String(x0 + ww + 2 * mm, y0 + hh / 2 + 2, f"{chg:+.0f}%", fontName=KRF, fontSize=7, fillColor=col))
            d.add(String(x0 + ww + 2 * mm, y0 + hh / 2 - 6, f"편입 {a['n_in']}곳", fontName=KRF, fontSize=5.6, fillColor=MUT))
            d.add(Line(x0, y0 - 1.5, x0 + ww, y0 - 1.5, strokeColor=LINE, strokeWidth=0.4))
        return d

    # ── 차트 7: 분기별 보유 펀드 수 추이 (변화 큰 종목) ──
    def trend_chart(agg, hist):
        tr = trend_rows(agg, hist, 5)
        d = Drawing(COL, 50 * mm)
        if not tr or len(tr[0]["series"]) < 2:
            d.add(String(4 * mm, 24 * mm, "분기 이력이 2개 이상 쌓이면 표시됩니다", fontName=KRF, fontSize=6.6, fillColor=MUT))
            return d
        qs = [q for q, _ in tr[0]["series"]]
        x0, y0, ww, hh = 8 * mm, 8 * mm, 52 * mm, 36 * mm
        mx = max(v for r in tr for _, v in r["series"]) or 1
        for g in range(5):
            gy = y0 + hh * g / 4
            d.add(Line(x0, gy, x0 + ww, gy, strokeColor=PAPER, strokeWidth=0.5))
            d.add(String(x0 - 1.5 * mm, gy - 1.5, f"{int(mx * g / 4)}", fontName=KRF, fontSize=5.4,
                         fillColor=MUT, textAnchor="end"))
        for j, q in enumerate(qs):
            x = x0 + (j / max(1, len(qs) - 1)) * ww
            d.add(String(x, y0 - 4.5 * mm, q.replace(" 20", " '"), fontName=KRF, fontSize=5.4,
                         fillColor=MUT, textAnchor="middle"))
        for i, r in enumerate(tr):
            col = PAL[i % len(PAL)]
            pts = []
            for j, (_, v) in enumerate(r["series"]):
                pts += [x0 + (j / max(1, len(qs) - 1)) * ww, y0 + v / mx * hh]
            d.add(PolyLine(pts, strokeColor=col, strokeWidth=1.3))
            ly = 46 * mm - i * 5.2 * mm
            d.add(Rect(64 * mm, ly - 1, 2.6 * mm, 2.6 * mm, fillColor=col, strokeWidth=0))
            d.add(String(67.5 * mm, ly - 0.6, f"{stock_label(r['sym'], r['name'])[:11]} {r['change']:+d}",
                         fontName=KRF, fontSize=5.9))
        return d

    # ── 표 8: 오늘 달라진 것 ──
    def change_table(items):
        rows = []
        for r in items["rank"][:4]:
            if r["kind"] == "new":
                rows.append(("순위", f"{r['g']} {r['name']}", "신규 진입", NEW))
            elif r["kind"] == "out":
                rows.append(("순위", f"{r['g']} {r['name']}", "이탈", DOWN))
            else:
                rows.append(("순위", f"{r['g']} {r['name']}", f"{'▲' if r['move'] > 0 else '▼'}{abs(r['move'])}",
                             UP if r["move"] > 0 else DOWN))
        for r in items["ret"][:3]:
            rows.append(("수익률", f"{r['g']} {r['name']}", f"{r['diff']:+.1f}p", UP if r["diff"] > 0 else DOWN))
        for a in items["hold"][:3]:
            v = "신규" if a["diff"] is None else f"{a['diff']:+d}곳"
            rows.append(("보유수", stock_label(a["sym"], a["name"])[:18], v,
                         NEW if a["diff"] is None else (UP if a["diff"] > 0 else DOWN)))
        for x in items["fresh"][:3]:
            rows.append(("개인", f"{x['who']} {x['tag']}", stock_label(x["sym"], x["issuer"])[:14], NEW))
        rows = rows[:12]
        if not rows:
            msg = "첫 실행 — 내일부터 표시" if items["first"] else "전일 대비 눈에 띄는 변화 없음"
            t = Table([[Paragraph(msg, SM)]], colWidths=[COL])
            return t
        data = [["구분", "대상", "변화"]] + [[a, b, c] for a, b, c, _ in rows]
        t = Table(data, colWidths=[14 * mm, 56 * mm, 20 * mm], rowHeights=[4.2 * mm] * len(data))
        st = [("FONT", (0, 0), (-1, -1), KRF, 6.2), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("BACKGROUND", (0, 0), (-1, 0), ACC), ("TOPPADDING", (0, 0), (-1, -1), 0.6),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6), ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
              ("ALIGN", (2, 0), (2, -1), "RIGHT")]
        for i, (_, _, _, col) in enumerate(rows, start=1):
            st.append(("TEXTCOLOR", (2, i), (2, i), col))
        t.setStyle(TableStyle(st))
        return t

    # ── 조립 ──
    S = []
    today = date.today().isoformat()
    S.append(Paragraph(f"고래 40 · {today}", H1))
    legend = ('<font color="#c0392b">■ 오름</font>  <font color="#1d6fb8">■ 내림</font>  '
              '<font color="#7b3fa0">■ 신규</font>  ■ 변동없음')
    S.append(Paragraph(f"1년 수익률 기준 기관·유명인 TOP {TOP_N} 감시 대시보드 · "
                       + (f"전일({prev['date']}) 대비 " if prev.get("date") else "") + legend, SUB))
    S.append(Spacer(1, 3))

    S.append(title("오늘의 한 줄"))
    for h in headlines(inst, ppl, agg, items, hits, prev):
        S.append(Paragraph(h, BUL, bulletText="·"))
    S.append(Spacer(1, 4))

    def two(a_title, a_draw, b_title, b_draw):
        t = Table([[title(a_title), title(b_title)], [a_draw, b_draw]],
                  colWidths=[COL + 2 * mm, COL + 2 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 1),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        return t

    S.append(two(f"기관 TOP 10 · 1년 수익률", rank_chart(inst, "inst"),
                 f"유명인 TOP 10 · 1년 수익률", rank_chart(ppl, "ppl")))
    S.append(Spacer(1, 3))
    S.append(two("여러 곳이 함께 보유 (보유 펀드 수)", consensus_chart(top_consensus(agg, 10)),
                 "이번 분기 편입·편출 쏠림 (순증감)", flow_chart(agg)))
    S.append(Spacer(1, 3))
    top_person = (details or [None])[0]
    pt = f"유명인 1위 {top_person['name']} 포트 구성" if top_person else "유명인 1위 포트 구성"
    S.append(two(pt, pie_chart(top_person), "가장 많이 편입된 종목 · 1년 주가", price_lines(agg)))
    S.append(Spacer(1, 3))
    S.append(two("분기별 보유 펀드 수 추이 (변화 큰 종목)", trend_chart(agg, hist),
                 "오늘 달라진 것", change_table(items)))

    S.append(Spacer(1, 3))
    S.append(Paragraph(
        "수익률은 13F 보유 상위 20종목을 공시일에 복제했다고 가정한 추정치이며 실제 펀드 수익률이 아닙니다. "
        "13F는 분기말 후 45일에 공개됩니다. 출처 13f.info · Yahoo Finance. 투자 자문이 아닙니다.", SM))

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=9 * mm, bottomMargin=7 * mm,
                            title=f"고래 40 대시보드 {today}", author="whale40")
    doc.build(S)
    return path






# ═══════════════════════════════════════════ 모바일 리포트 (HTML)
# A4 PDF는 폰에서 확대해야 읽힌다. 세로로 긴 한 장으로 다시 짠다.
# 색은 '행동'에 고정: 초록=관심, 주황=주의, 회색=회피, 남색=매도검토.
# 주가 숫자만 국내 관행대로 빨강=상승, 파랑=하락.
ZONE = {
    "contra": ("역행 매수", "고래는 사고 시장은 팔았다", "관심", "act-go"),
    "chase": ("추격 매수", "고래도 이미 오른 뒤 탔다", "주의", "act-warn"),
    "flee": ("동반 이탈", "내리는데 고래도 팔았다", "회피", "act-stop"),
    "profit": ("차익 실현", "오른 뒤 고래가 나갔다", "매도 검토", "act-exit"),
}


def _h(s):
    return html.escape(str(s if s is not None else ""))


def _pc(v, nd=1, dash="—"):
    return dash if v is None else f"{v:+.{nd}f}%"


def _cls(v):
    return "" if v is None else ("up" if v > 0 else ("down" if v < 0 else ""))


def hero_pick(Q, mov, clus, cost, warn, idx):
    """오늘 딱 하나. 역행 매수 + 전일 신호 + 동시 편입이 겹치는 종목을 최우선으로."""
    score = {}
    def bump(sym, pts, why):
        d = score.setdefault(sym, {"pts": 0, "why": []})
        d["pts"] += pts
        d["why"].append(why)
    for r in Q["contra"][:6]:
        bump(r["sym"], 4 + min(4, abs(r["score"])), f"고래 {r['n_in']}곳이 사는데 1년 {r['ret_1y']:+.0f}%")
    for r in clus[:5]:
        bump(r["sym"], 3 + r["cluster"], f"이번 분기 {r['cluster']}곳이 동시에 신규 편입")
    for r in mov[:5]:
        bump(r["sym"], 3, f"어제 {r['ret_1d']:+.1f}%" + (f", 거래량 {r['vol_ratio']:.1f}배" if r.get("vol_ratio") else ""))
    for r in cost[:5]:
        if r["gap"] < 0:
            bump(r["sym"], 3, f"고래 평단보다 {abs(r['gap']):.0f}% 싸다")
    for r in warn[:4]:
        bump(r["sym"], 3, f"{abs(r['streak'])}분기 연속 이탈")
    if not score:
        return None
    sym = max(score, key=lambda s: score[s]["pts"])
    pool = {r["sym"]: (k, r) for k in Q for r in Q[k]}
    pool.update({r["sym"]: (pool.get(r["sym"], ("", r))[0], r) for r in clus + mov + cost + warn})
    zone, row = pool.get(sym, ("", None))
    if not row:
        return None
    neg = any("이탈" in x for x in score[sym]["why"])
    return {"sym": sym, "name": row.get("name", ""), "zone": zone or ("flee" if neg else "contra"),
            "why": score[sym]["why"][:3], "row": row}


def make_mobile_html(path, inst, ppl, agg, hist, details, items, prev, pc, Q, disc, conv,
                     mov, secs, idx, live, clus, cost, warn, earn, bt):
    today = date.today().isoformat()
    wd = "월화수목금토일"[date.today().weekday()]
    nxt, dday = next_13f_deadline()
    hero = hero_pick(Q, mov, clus, cost, warn, idx)

    def card_rows(rows, cols, empty="해당 없음"):
        """모바일용 카드형 목록. 각 줄이 종목 하나."""
        if not rows:
            return f'<p class="empty">{_h(empty)}</p>'
        out = []
        for r in rows:
            head = f'<b>{_h(r["sym"])}</b> <span class="nm">{_h(label_only(r["sym"], r.get("name", "")))}</span>'
            bits = "".join(f'<span class="kv"><i>{_h(lab)}</i><em class="{cl}">{val}</em></span>'
                           for lab, val, cl in cols(r))
            out.append(f'<div class="row"><div class="rh">{head}</div><div class="kvs">{bits}</div></div>')
        return "".join(out)

    def sect(sid, title, hint, body, tone=""):
        return (f'<section id="{sid}" class="sec {tone}"><h2>{_h(title)}</h2>'
                f'<p class="hint">{_h(hint)}</p>{body}</section>')

    # ── 오늘 이것 하나 ──
    if hero:
        z = ZONE.get(hero["zone"], ZONE["contra"])
        r = hero["row"]
        facts = []
        if r.get("ret_1y") is not None:
            facts.append(("1년 주가", _pc(r["ret_1y"], 0), _cls(r["ret_1y"])))
        if r.get("n_hold"):
            facts.append(("보유 고래", f'{r["n_hold"]}곳', ""))
        if r.get("score") is not None:
            facts.append(("편입 순증감", f'{r["score"]:+d}', ""))
        if r.get("wscore"):
            facts.append(("가중 순증감", f'{r["wscore"]:+.1f}', ""))
        if r.get("cost_basis"):
            facts.append(("고래 평단", f'${r["cost_basis"]:,.0f}', ""))
        if r.get("last"):
            facts.append(("현재가", f'${r["last"]:,.2f}', ""))
        hero_html = (
            f'<div class="hero {z[3]}"><div class="tag">오늘 이것 하나 · {_h(z[0])} · {_h(z[2])}</div>'
            f'<div class="sym">{_h(stock_label(hero["sym"], hero["name"]))}</div>'
            f'<ul class="why">' + "".join(f"<li>{_h(w)}</li>" for w in hero["why"]) + "</ul>"
            f'<div class="facts">' + "".join(
                f'<span><i>{_h(a)}</i><em class="{c}">{_h(b)}</em></span>' for a, b, c in facts) + "</div>"
            f'<p class="zwhy">{_h(z[1])}</p></div>')
    else:
        hero_html = '<div class="hero"><div class="sym">오늘은 두드러진 신호가 없습니다</div></div>'

    # ── KPI: 행동으로 이어지는 것만 ──
    kpis = []
    if idx and idx["r1y"] is not None:
        gap = (idx["r1y"] or 0) - (idx["s1y"] or 0)
        kpis.append(("고래 인덱스 1년", f'{idx["r1y"]:+.1f}%', f'S&P500 {idx["s1y"]:+.1f}% ({gap:+.1f}p)', _cls(idx["r1y"])))
        kpis.append(("어제", f'{idx["r1d"]:+.2f}%', f'S&P500 {idx["s1d"]:+.2f}%', _cls(idx["r1d"])))
    kpis.append(("실시간 신호", f'{len(live)}건', "Form 4 매수 · 13D/G · 최근 5영업일", "hot" if live else ""))
    kpis.append(("다음 13F 마감", f'D-{dday}', f'{nxt.month}/{nxt.day} · 대량 갱신', ""))
    kpi_html = "".join(f'<div class="kpi"><i>{_h(a)}</i><b class="{c}">{_h(b)}</b><u>{_h(s)}</u></div>'
                       for a, b, s, c in kpis)

    # ── 실시간 신호 (13F 45일 공백을 메우는 자료) ──
    live_html = ""
    if live:
        ls = []
        for x in live[:14]:
            lab = stock_label(x.get("sym", ""), x.get("issuer", "")) or x.get("issuer", "")
            if x["kind"] == "Form 4":
                amt = f'{x["shares"]:,.0f}주' + (f' @ ${x["price"]:,.2f}' if x.get("price") else "")
                det = f'매수 {amt}'
            else:
                det = f'지분 {x["pct"]:.1f}%' if x.get("pct") else "지분 신고"
            ls.append(f'<div class="row live"><div class="rh"><span class="badge">{_h(x["kind"])}</span> '
                      f'<b>{_h(lab)}</b></div><div class="sub">{_h(x["who"])} · {_h(det)} · {_h(x["when"] or x["filed"])}</div></div>')
        live_html = "".join(ls)
    else:
        live_html = ('<p class="empty">최근 5영업일 안에 감시 대상이 낸 Form 4 매수·13D/G가 없습니다. '
                     '13F만 있는 날은 여기가 비는 것이 정상입니다.</p>')

    # ── 사분면을 표가 아니라 4장의 카드로 ──
    zcards = []
    for k in ("contra", "chase", "profit", "flee"):
        rows = Q.get(k, [])[:5]
        t, d, act, cl = ZONE[k]
        inner = "".join(
            f'<li><b>{_h(r["sym"])}</b> <span class="nm">{_h(label_only(r["sym"], r["name"])[:14])}</span>'
            f'<em class="{_cls(r["ret_1y"])}">{_pc(r["ret_1y"], 0)}</em>'
            f'<span class="sc">{r["score"]:+d}</span></li>' for r in rows)
        zcards.append(f'<div class="zone {cl}"><div class="zt">{_h(t)}<span>{_h(act)}</span></div>'
                      f'<p class="zd">{_h(d)}</p><ul class="zl">{inner or "<li class=e>해당 없음</li>"}</ul></div>')
    zone_html = f'<div class="zones">{"".join(zcards)}</div>'

    # ── 백테스트 ──
    bt_html = ""
    if bt:
        cells = []
        for k in ("contra", "chase", "profit", "flee"):
            v = bt["zones"].get(k)
            if not v:
                continue
            t, _, act, cl = ZONE[k]
            cells.append(f'<div class="bt {cl}"><i>{_h(t)}</i><b class="{_cls(v["avg"])}">{v["avg"]:+.1f}%</b>'
                         f'<u>{v["n"]}종목 · 지수 대비 승률 {v["win"]:.0f}%</u></div>')
        bench = f'같은 기간 S&P500 {bt["bench"]:+.1f}%' if bt.get("bench") is not None else ""
        bt_html = (f'<div class="bts">{"".join(cells)}</div>'
                   f'<p class="note">{_h(bt["quarter"])} 기준으로 구역을 나눈 뒤 지금까지의 수익률. {_h(bench)}</p>')

    body = [
        f'<header><div class="ttl">고래 40</div>'
        f'<div class="date">{date.today().strftime("%Y년 %m월 %d일")} ({wd})</div></header>',
        f'<div class="kpis">{kpi_html}</div>',
        hero_html,
        sect("live", "실시간 신호", "Form 4 매수와 13D/G는 거래 2~5영업일 뒤에 나옵니다. 13F의 45일 공백을 메우는 자료입니다.", live_html),
        sect("zone", "고래 vs 시장", "가로로 스크롤하지 말고 네 칸만 보세요. 초록이 관심, 주황이 주의입니다.", zone_html),
        sect("cluster", "동시 편입", "같은 분기에 여러 곳이 한꺼번에 신규로 담은 종목. 합의가 막 생기는 지점입니다.",
             card_rows(clus[:8], lambda r: [("동시 신규", f'{r["cluster"]}곳', ""), ("보유", f'{r["n_hold"]}곳', ""),
                                            ("가중 순증감", f'{r.get("wscore", 0):+.1f}', ""),
                                            ("1년", _pc(r.get("ret_1y"), 0), _cls(r.get("ret_1y")))],
                       "3곳 이상이 동시에 신규 편입한 종목이 없습니다.")),
        sect("cost", "고래 평단 대비 현재가", "분기별 순매수 주식수 × 그 분기 평균가로 추정한 매입단가. 음수면 고래보다 싸게 삽니다.",
             card_rows(cost[:8], lambda r: [("괴리", f'{r["gap"]:+.1f}%', _cls(r["gap"])),
                                            ("고래 평단", f'${r["cost_basis"]:,.2f}', ""),
                                            ("현재가", f'${r["last"]:,.2f}', ""),
                                            ("보유", f'{r["n_hold"]}곳', "")])),
        sect("mov", "전일 신호", "고래 3곳 이상 보유 종목 중 어제 3% 이상 움직였거나 거래량이 20일 평균의 2배를 넘은 것.",
             card_rows(mov[:8], lambda r: [("등락", _pc(r.get("ret_1d")), _cls(r.get("ret_1d"))),
                                           ("거래량", f'{r["vol_ratio"]:.1f}배' if r.get("vol_ratio") else "—", ""),
                                           ("보유", f'{r["n_hold"]}곳', ""),
                                           ("순증감", f'{r["score"]:+d}', "")],
                       "어제는 조건에 맞는 종목이 없었습니다.")),
        sect("warn", "보유 중이면 점검", "2분기 이상 연속으로 보유 펀드가 줄고, 성적 좋은 곳이 먼저 빠지는 종목.",
             card_rows(warn[:8], lambda r: [("연속 이탈", f'{abs(r["streak"])}분기', "down"),
                                            ("가중 순증감", f'{r.get("wscore", 0):+.1f}', "down"),
                                            ("보유", f'{r["n_hold"]}곳', ""),
                                            ("1년", _pc(r.get("ret_1y"), 0), _cls(r.get("ret_1y")))],
                       "연속 이탈 추세인 종목이 없습니다."), "tone-stop"),
        sect("earn", "곧 실적 발표", "고래가 3곳 이상 든 종목 중 열흘 안에 실적이 잡힌 것. 행동 시점이 여기 걸립니다.",
             card_rows(earn[:8], lambda r: [("발표", f'D-{r["dday"]}', "hot" if r["dday"] <= 2 else ""),
                                            ("날짜", r["earn"], ""), ("보유", f'{r["n_hold"]}곳', ""),
                                            ("순증감", f'{r["score"]:+d}', "")],
                       "열흘 안에 실적이 잡힌 종목이 없습니다.")),
        sect("bt", "이 방법이 먹혔나", "과거 분기에 각 구역이던 종목들이 그 뒤 실제로 어떻게 됐는지. 분기마다 표본이 쌓입니다.",
             bt_html or '<p class="empty">분기 이력이 4개 이상 쌓이면 계산됩니다.</p>'),
        sect("conv", "컨빅션", "보유 펀드들의 포트 내 비중 합. 20곳이 0.5%씩 든 것과 6곳이 12%씩 든 것을 구분합니다.",
             card_rows([{**a, **pc.get(a["sym"], {})} for a in conv[:8]],
                       lambda r: [("점수", f'{r["conviction"]:.0f}', ""), ("보유", f'{r["n_hold"]}곳', ""),
                                  ("평균비중", f'{r["avg_w"]:.1f}%', ""),
                                  ("1년", _pc(r.get("ret_1y"), 0), _cls(r.get("ret_1y")))])),
        sect("sector", "섹터별 자금 흐름", "섹터 안 종목들의 편입 순증감 합. 고래 돈이 어디로 가는지.",
             '<div class="bars">' + "".join(
                 f'<div class="bar"><i>{_h(s["sector"])}</i>'
                 f'<div class="track"><span class="{"pos" if s["score"] > 0 else "neg"}" '
                 f'style="width:{min(100, abs(s["score"]) / max(1, max(abs(x["score"]) for x in secs)) * 100):.0f}%"></span></div>'
                 f'<em class="{_cls(s["score"])}">{s["score"]:+d}</em></div>' for s in secs[:8]) + "</div>"
             if secs else '<p class="empty">자료 없음</p>'),
        sect("rank", "성적 상위", "13F 보유를 복제한 1년 수익률 추정치입니다. 실제 펀드 수익률이 아닙니다.",
             '<div class="two">' + "".join(
                 f'<div><h3>{_h(t)}</h3><ol class="rk">' + "".join(
                     f'<li><span>{_h(r["name"][:18])}</span><em class="{_cls(r["ret_1y"])}">{r["ret_1y"]:+.0f}%</em></li>'
                     for r in rows[:8]) + "</ol></div>"
                 for t, rows in (("기관", inst), ("유명인", ppl))) + "</div>"),
        '<footer>고래 평단·수익률·비중은 13F 공시에서 추정한 값이며 실제 체결가가 아닙니다. '
        '13F는 분기말 후 45일에 공개됩니다. 고래 인덱스는 컨빅션 상위 10종목 동일비중 가상 포트로 거래비용을 반영하지 않습니다.<br>'
        '출처 13f.info · SEC EDGAR · Yahoo Finance · 투자 자문이 아닙니다.</footer>',
    ]

    css = """
:root{--bg:#f7f6f2;--card:#fff;--ink:#171614;--mut:#6c6862;--line:#e3dfd6;
--go:#1f7a4d;--warn:#c2740a;--stop:#8a8580;--exit:#2b5f9e;--up:#c0392b;--down:#1d6fb8;--hot:#b3312a}
*{box-sizing:border-box;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-size:16px;line-height:1.55;
font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif}
.wrap{max-width:560px;margin:0 auto;padding:0 14px 40px}
header{padding:20px 0 12px}
.ttl{font-size:26px;font-weight:800;letter-spacing:-.5px}
.date{color:var(--mut);font-size:14px;margin-top:2px}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.kpi i{display:block;font-style:normal;font-size:12px;color:var(--mut)}
.kpi b{display:block;font-size:21px;font-weight:700;letter-spacing:-.5px;margin:1px 0}
.kpi u{display:block;text-decoration:none;font-size:11.5px;color:var(--mut);line-height:1.35}
.hero{background:var(--card);border:1px solid var(--line);border-left:6px solid var(--go);
border-radius:14px;padding:16px;margin-bottom:22px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.hero.act-warn{border-left-color:var(--warn)}.hero.act-stop{border-left-color:var(--stop)}
.hero.act-exit{border-left-color:var(--exit)}
.hero .tag{font-size:12px;font-weight:700;color:var(--go);letter-spacing:.2px}
.hero.act-warn .tag{color:var(--warn)}.hero.act-stop .tag{color:var(--stop)}.hero.act-exit .tag{color:var(--exit)}
.hero .sym{font-size:23px;font-weight:800;margin:3px 0 8px;letter-spacing:-.5px}
.hero .why{margin:0 0 10px;padding-left:18px}
.hero .why li{margin:3px 0;font-size:14.5px}
.hero .facts{display:flex;flex-wrap:wrap;gap:6px}
.hero .facts span{background:var(--bg);border-radius:8px;padding:5px 9px;font-size:12.5px}
.hero .facts i{font-style:normal;color:var(--mut);margin-right:5px}
.hero .facts em{font-style:normal;font-weight:700}
.zwhy{margin:10px 0 0;font-size:12.5px;color:var(--mut)}
.sec{margin:0 0 22px}
.sec h2{font-size:17px;margin:0;padding-left:9px;border-left:4px solid var(--go);font-weight:750}
.sec.tone-stop h2{border-left-color:var(--hot)}
.hint{color:var(--mut);font-size:12.5px;margin:5px 0 9px;padding-left:13px}
.row{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:10px 12px;margin-bottom:6px}
.rh{font-size:15.5px;font-weight:700}
.rh .nm{font-weight:400;color:var(--mut);font-size:13px;margin-left:4px}
.kvs{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:5px}
.kv i{font-style:normal;color:var(--mut);font-size:11.5px;margin-right:4px}
.kv em{font-style:normal;font-weight:700;font-size:13.5px}
.sub{color:var(--mut);font-size:12.5px;margin-top:3px}
.badge{background:var(--hot);color:#fff;border-radius:5px;padding:2px 6px;font-size:11px;font-weight:700;margin-right:5px}
.up,em.up{color:var(--up)}.down,em.down{color:var(--down)}.hot,b.hot{color:var(--hot)}
.empty{color:var(--mut);font-size:13px;background:var(--card);border:1px dashed var(--line);
border-radius:11px;padding:12px;margin:0}
.zones{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.zone{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--go);border-radius:11px;padding:10px}
.zone.act-warn{border-top-color:var(--warn)}.zone.act-stop{border-top-color:var(--stop)}
.zone.act-exit{border-top-color:var(--exit)}
.zt{font-size:13.5px;font-weight:750}
.zt span{float:right;font-size:11px;font-weight:700;color:var(--go)}
.act-warn .zt span{color:var(--warn)}.act-stop .zt span{color:var(--stop)}.act-exit .zt span{color:var(--exit)}
.zd{font-size:11.5px;color:var(--mut);margin:2px 0 7px}
.zl{list-style:none;margin:0;padding:0}
.zl li{display:flex;align-items:baseline;gap:4px;font-size:12.5px;padding:3px 0;border-top:1px solid var(--line)}
.zl li:first-child{border-top:0}
.zl .nm{color:var(--mut);flex:1;overflow:hidden;white-space:nowrap}
.zl em{font-style:normal;font-weight:700}
.zl .sc{color:var(--mut);font-size:11px;min-width:22px;text-align:right}
.zl li.e{color:var(--mut)}
.bts{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.bt{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--go);border-radius:11px;padding:9px 11px}
.bt.act-warn{border-left-color:var(--warn)}.bt.act-stop{border-left-color:var(--stop)}.bt.act-exit{border-left-color:var(--exit)}
.bt i{font-style:normal;font-size:12px;color:var(--mut);display:block}
.bt b{font-size:19px;font-weight:750}
.bt u{display:block;text-decoration:none;font-size:11px;color:var(--mut)}
.note{font-size:12px;color:var(--mut);margin:8px 0 0}
.bars{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:10px 12px}
.bar{display:flex;align-items:center;gap:8px;padding:3px 0}
.bar i{font-style:normal;font-size:12.5px;width:78px;flex:none}
.track{flex:1;height:9px;background:var(--bg);border-radius:5px;overflow:hidden}
.track span{display:block;height:100%}
.track .pos{background:var(--up)}.track .neg{background:var(--down)}
.bar em{font-style:normal;font-weight:700;font-size:12.5px;width:34px;text-align:right}
.two{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.two h3{font-size:13px;margin:0 0 5px;color:var(--mut);font-weight:600}
.rk{list-style:none;counter-reset:r;margin:0;padding:0;background:var(--card);
border:1px solid var(--line);border-radius:11px;padding:8px 10px}
.rk li{counter-increment:r;display:flex;gap:5px;font-size:12.5px;padding:3px 0}
.rk li:before{content:counter(r) ".";color:var(--mut);min-width:15px}
.rk span{flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.rk em{font-style:normal;font-weight:700}
footer{color:var(--mut);font-size:11.5px;line-height:1.6;border-top:1px solid var(--line);padding-top:14px;margin-top:26px}
@media(prefers-color-scheme:dark){:root{--bg:#141412;--card:#1e1d1a;--ink:#eceae5;--mut:#9a958c;--line:#33312c;
--go:#4aa97a;--warn:#d99331;--stop:#8a8580;--exit:#5b92cf;--up:#e06a5e;--down:#5fa3e0;--hot:#e0685c}}
"""
    doc = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
           f'<title>고래 40 · {today}</title><style>{css}</style></head>'
           f'<body><div class="wrap">{"".join(body)}</div></body></html>')
    Path(path).write_text(doc, encoding="utf-8")
    return path


# ══════════════════════════════════════════ 대시보드 v2 (2쪽 · 실전형)
def build_headlines_v2(inst, ppl, agg, Q, disc, mov, idx, hits, sec_rows):
    H = []
    if Q["contra"]:
        r = Q["contra"][0]
        H.append(f"<b>역행 매수</b> — {stock_label(r['sym'], r['name'])}: 고래 {r['n_in']}곳이 샀는데 1년 {r['ret_1y']:+.0f}%. "
                 f"시장과 반대로 가는 확신")
    if Q["chase"]:
        r = Q["chase"][0]
        H.append(f"<b>추격 주의</b> — {stock_label(r['sym'], r['name'])}: 편입 {r['n_in']}곳이지만 이미 1년 {r['ret_1y']:+.0f}%. "
                 f"고래보다 훨씬 높은 값에 사게 됩니다")
    if Q["flee"]:
        r = Q["flee"][0]
        H.append(f"<b>동반 이탈</b> — {stock_label(r['sym'], r['name'])}: 편출 {r['n_out']}곳 · 1년 {r['ret_1y']:+.0f}%. "
                 f"보유 중이면 재점검")
    if mov:
        r = mov[0]
        H.append(f"<b>전일 신호</b> — {stock_label(r['sym'], r['name'])} {r['ret_1d']:+.1f}%"
                 + (f", 거래량 {r['vol_ratio']:.1f}배" if r["vol_ratio"] else "")
                 + f" · 고래 {r['n_hold']}곳 보유")
    if disc:
        r = disc[0]
        H.append(f"<b>고래보다 싸게</b> — {stock_label(r['sym'], r['name'])}: 분기말 대비 {r['vs_qe']:+.1f}%, 편입 {r['n_in']}곳")
    if idx and idx["r1y"] is not None and idx["s1y"] is not None:
        H.append(f"<b>고래 인덱스</b> 1년 {idx['r1y']:+.1f}% vs S&P500 {idx['s1y']:+.1f}% · "
                 f"어제 {idx['r1d']:+.2f}% vs {idx['s1d']:+.2f}%")
    if sec_rows:
        top, bot = sec_rows[0], sec_rows[-1]
        H.append(f"<b>자금 흐름</b> — {top['sector']}으로 순유입 {top['score']:+d}, {bot['sector']}에서 순유출 {bot['score']:+d}")
    nxt, days = next_13f_deadline()
    H.append(f"다음 13F 마감 <b>{nxt.month}/{nxt.day}</b> · D-{days}")
    return H[:6]


def make_dashboard_v2(path, inst, ppl, agg, hist, details, hits, items, prev, pc, Q, disc, conv, mov, secs, idx,
                      live=(), clus=(), cost=(), warn=(), earn=(), bt=None):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                        PageBreak, KeepTogether)
        from reportlab.graphics.shapes import Drawing, String, Rect, Line, PolyLine, Circle
        from reportlab.graphics.charts.barcharts import HorizontalBarChart
    except ImportError:
        return None
    KRF = register_korean_font()
    if not KRF:
        return None

    INK = colors.HexColor("#1b1a18"); MUT = colors.HexColor("#6f6b64"); LINE = colors.HexColor("#dcd8cd")
    PAPER = colors.HexColor("#f6f4ef"); ACC = colors.HexColor("#1f4d3a"); ACC2 = colors.HexColor("#2d6a4f")
    UP, DOWN, NEW, WARN = (colors.HexColor("#c0392b"), colors.HexColor("#1d6fb8"),
                           colors.HexColor("#7b3fa0"), colors.HexColor("#b7791f"))
    PAL = [colors.HexColor(c) for c in ("#2d6a4f", "#b4451f", "#2b6cb0", "#8a5a00", "#6b46c1", "#0f766e", "#9d174d")]
    # 행동 색: 어느 칸에서 보든 뜻이 같다 (주가 숫자만 국내 관행대로 빨강=상승)
    GO, CAUT, STOP, EXIT = (colors.HexColor("#1f7a4d"), colors.HexColor("#c2740a"),
                            colors.HexColor("#8a8580"), colors.HexColor("#2b5f9e"))
    ZCOL = {"contra": GO, "chase": CAUT, "flee": STOP, "profit": EXIT}
    ZNAME = {"contra": ("역행 매수", "관심"), "chase": ("추격 매수", "주의"),
             "flee": ("동반 이탈", "회피"), "profit": ("차익 실현", "매도 검토")}
    W, COL = 190 * mm, 93 * mm

    T = ParagraphStyle("t", fontName=KRF, fontSize=22, leading=25, textColor=colors.white)
    TS = ParagraphStyle("ts", fontName=KRF, fontSize=8.6, leading=11, textColor=colors.HexColor("#cfe3d8"))
    TR = ParagraphStyle("tr", fontName=KRF, fontSize=8.2, leading=10, textColor=colors.HexColor("#cfe3d8"), alignment=2)
    H2 = ParagraphStyle("h2", fontName=KRF, fontSize=10.5, leading=13, textColor=ACC)
    HINT = ParagraphStyle("hint", fontName=KRF, fontSize=7.2, leading=9, textColor=MUT, alignment=2)
    BUL = ParagraphStyle("b", fontName=KRF, fontSize=8.7, leading=12.4, leftIndent=10, bulletIndent=0)
    SM = ParagraphStyle("s", fontName=KRF, fontSize=7.2, leading=9.6, textColor=MUT)
    KPIN = ParagraphStyle("kn", fontName=KRF, fontSize=15.5, leading=18, textColor=INK)
    KPIL = ParagraphStyle("kl", fontName=KRF, fontSize=7.2, leading=9, textColor=MUT)
    KPIS = ParagraphStyle("ks", fontName=KRF, fontSize=7.2, leading=9.2, textColor=MUT)
    today = date.today().isoformat()

    def pad(t, l=0, r=0, tp=1, b=1):
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), l), ("RIGHTPADDING", (0, 0), (-1, -1), r),
                               ("TOPPADDING", (0, 0), (-1, -1), tp), ("BOTTOMPADDING", (0, 0), (-1, -1), b),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    WD = "월화수목금토일"[date.today().weekday()]
    def title_band(sub, page):
        right = Paragraph(f"{page} / 3<br/>{date.today().strftime('%Y년 %m월 %d일')} ({WD})", TR)
        t = Table([[Paragraph("고래 40 · 실전 대시보드", T), right], [Paragraph(sub, TS), ""]], colWidths=[W - 45 * mm, 45 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACC), ("LEFTPADDING", (0, 0), (-1, -1), 9),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, 0), 7),
                               ("BOTTOMPADDING", (0, 1), (-1, 1), 7), ("TOPPADDING", (0, 1), (-1, 1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, 0), 1), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LINEBELOW", (0, 1), (-1, 1), 2.2, WARN)]))
        return t

    def sec(title, hint=""):
        """번호 없는 섹션 헤더: 왼쪽 굵은 색 막대 + 제목 + 오른쪽 설명."""
        t = Table([[Paragraph(title, H2), Paragraph(hint, HINT)]], colWidths=[W * 0.55, W * 0.45])
        t.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, 0), 3, ACC2), ("LEFTPADDING", (0, 0), (0, 0), 6),
                               ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                               ("LINEBELOW", (0, 0), (-1, 0), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        return t

    def sec_half(title, hint=""):
        t = Table([[Paragraph(title, H2)], [Paragraph(hint, ParagraphStyle("hl", parent=HINT, alignment=0))]] if hint
                  else [[Paragraph(title, H2)]], colWidths=[COL])
        t.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 3, ACC2), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0.5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("LINEBELOW", (0, -1), (-1, -1), 0.5, LINE)]))
        return t

    HERO = ParagraphStyle("hero", fontName=KRF, fontSize=17, leading=20, textColor=INK)
    HTAG = ParagraphStyle("htag", fontName=KRF, fontSize=7.8, leading=10)
    HWHY = ParagraphStyle("hwhy", fontName=KRF, fontSize=8.6, leading=12, leftIndent=8, bulletIndent=0)

    def hero_card():
        h = hero_pick(Q, mov, list(clus), list(cost), list(warn), idx)
        if not h:
            return None
        col = ZCOL.get(h["zone"], GO); zt, act = ZNAME.get(h["zone"], ("", ""))
        r = h["row"]
        chips = []
        if r.get("ret_1y") is not None:
            chips.append(("1년 주가", f"{r['ret_1y']:+.0f}%", UP if r["ret_1y"] >= 0 else DOWN))
        if r.get("n_hold"):
            chips.append(("보유 고래", f"{r['n_hold']}곳", INK))
        if r.get("score") is not None:
            chips.append(("편입 순증감", f"{r['score']:+d}", INK))
        if r.get("wscore"):
            chips.append(("가중 순증감", f"{r['wscore']:+.1f}", INK))
        if r.get("cost_basis"):
            chips.append(("고래 평단", f"${r['cost_basis']:,.0f}", INK))
        if r.get("last"):
            chips.append(("현재가", f"${r['last']:,.2f}", INK))
        chip_t = Table([[Paragraph(f'<font color="#{MUT.hexval()[4:]}" size="6.4">{a}</font>  '
                                   f'<font color="#{c.hexval()[4:]}"><b>{v}</b></font>',
                                   ParagraphStyle("c", fontName=KRF, fontSize=7.6, leading=9.5))
                        for a, v, c in chips]],
                       colWidths=[(W - 14) / max(1, len(chips))] * len(chips))
        chip_t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PAPER), ("BOX", (0, 0), (-1, -1), 0.3, LINE),
                                    ("LINEBEFORE", (1, 0), (-1, -1), 0.3, LINE),
                                    ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
        inner = [Paragraph(f'<font color="#{col.hexval()[4:]}"><b>오늘 이것 하나 · {zt} · {act}</b></font>', HTAG),
                 Paragraph(f"<b>{stock_label(h['sym'], h['name'])}</b>", HERO)]
        for wy in h["why"]:
            inner.append(Paragraph(wy, HWHY, bulletText="·"))
        inner += [Spacer(1, 3), chip_t]
        t = Table([[inner]], colWidths=[W])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.white), ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                               ("LINEBEFORE", (0, 0), (0, 0), 3.5, col),
                               ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                               ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        return t

    def kpi_cards():
        def card(label, val, sub, col=INK):
            st = ParagraphStyle("k", parent=KPIN, textColor=col)
            return [Paragraph(label, KPIL), Paragraph(val, st), Paragraph(sub, KPIS)]
        nxt, days = next_13f_deadline()
        c = []
        if idx and idx["r1y"] is not None:
            d = (idx["r1y"] or 0) - (idx["s1y"] or 0)
            c.append(card("고래 인덱스 · 1년", f"{idx['r1y']:+.1f}%", f"S&P500 {idx['s1y']:+.1f}% ({d:+.1f}p)",
                          UP if idx["r1y"] >= 0 else DOWN))
            c.append(card("고래 인덱스 · 어제", f"{idx['r1d']:+.2f}%", f"S&P500 {idx['s1d']:+.2f}%",
                          UP if idx["r1d"] >= 0 else DOWN))
        else:
            c.append(card("고래 인덱스", "—", "주가 자료 부족")); c.append(card("어제", "—", ""))
        c.append(card("실시간 신호", f"{len(live)}건", "Form 4 매수 · 13D/G · 최근 5영업일", UP if live else MUT))
        nc = len([1 for x in clus if x.get("cluster", 0) >= 3])
        c.append(card("동시 편입 종목", f"{nc}개", "이번 분기 3곳 이상이 한꺼번에 신규", GO if nc else MUT))
        c.append(card("다음 13F 마감", f"D-{days}", f"{nxt.month}/{nxt.day} · 편입·편출 대량 갱신", CAUT))
        t = Table([c], colWidths=[W / 5] * 5)
        st = [("BACKGROUND", (0, 0), (-1, -1), PAPER), ("BOX", (0, 0), (-1, -1), 0.4, LINE),
              ("LINEBEFORE", (1, 0), (-1, -1), 0.4, LINE),
              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
              ("VALIGN", (0, 0), (-1, -1), "TOP")]
        for i, cc in enumerate(c):      # 카드 값의 색을 위 띠에도
            st.append(("LINEABOVE", (i, 0), (i, 0), 2.4, cc[1].style.textColor))
        t.setStyle(TableStyle(st))
        return t

    def tbl(data, widths, right=(), paint=(), fs=7.6, rh=None):
        t = Table(data, colWidths=widths, rowHeights=rh, repeatRows=1)
        st = [("FONT", (0, 0), (-1, -1), KRF, fs), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("BACKGROUND", (0, 0), (-1, 0), ACC2), ("TOPPADDING", (0, 0), (-1, -1), 3),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 1), (-1, -1), 0.25, LINE),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
        for c in right:
            st.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
        for c, r, col in paint:
            st.append(("TEXTCOLOR", (c, r), (c, r), col))
        t.setStyle(TableStyle(st))
        return t

    def pct(v, nd=0):
        return "—" if v is None else f"{v:+.{nd}f}%"

    # ── 사분면 산점도 ──
    def quadrant_chart():
        from reportlab.pdfbase import pdfmetrics
        from reportlab.graphics.shapes import Polygon
        Wd, Hd = W, 98 * mm
        d = Drawing(Wd, Hd)
        x0, y0, ww, hh = 15 * mm, 10 * mm, Wd - 24 * mm, Hd - 18 * mm
        pts = [r for k in Q for r in Q[k]]
        if not pts:
            d.add(String(Wd / 2, Hd / 2, "표시할 종목이 없습니다", fontName=KRF, fontSize=8, fillColor=MUT, textAnchor="middle"))
            return d
        xs = [r["score"] for r in pts]; ys = [r["ret_1y"] for r in pts]
        xmax = max(abs(min(xs)), abs(max(xs)), 3) + 1
        # 세로축은 대다수가 들어오는 범위로 압축 — 벗어나는 종목은 가장자리에 화살표로
        ys_sorted = sorted(ys)
        hi_q = ys_sorted[min(len(ys) - 1, int(len(ys) * 0.9))]
        ymax = float(max(30, min(150, hi_q * 1.15 + 5)))
        ymin = float(max(-80, min(-30, min(ys) * 1.1 - 5)))
        def X(v): return x0 + (v + xmax) / (2 * xmax) * ww
        def Yraw(v): return y0 + (v - ymin) / (ymax - ymin) * hh
        cx, cy = X(0), Yraw(0)
        d.add(Rect(x0, cy, cx - x0, y0 + hh - cy, fillColor=colors.HexColor("#edf2f8"), strokeWidth=0))   # 좌상 차익실현
        d.add(Rect(cx, cy, x0 + ww - cx, y0 + hh - cy, fillColor=colors.HexColor("#fdf1e8"), strokeWidth=0))  # 우상 추격
        d.add(Rect(x0, y0, cx - x0, cy - y0, fillColor=colors.HexColor("#ececea"), strokeWidth=0))          # 좌하 동반이탈
        d.add(Rect(cx, y0, x0 + ww - cx, cy - y0, fillColor=colors.HexColor("#e6f3ec"), strokeWidth=0))     # 우하 역행
        for g in (-50, 50, 100):
            if ymin < g < ymax:
                d.add(Line(x0, Yraw(g), x0 + ww, Yraw(g), strokeColor=colors.white, strokeWidth=0.8))
                d.add(String(x0 - 1.5 * mm, Yraw(g) - 2.2, f"{g:+d}%", textAnchor="end", fillColor=MUT, fontName=KRF, fontSize=6.6))
        d.add(Line(cx, y0, cx, y0 + hh, strokeColor=MUT, strokeWidth=0.7))
        d.add(Line(x0, cy, x0 + ww, cy, strokeColor=MUT, strokeWidth=0.7))
        d.add(Rect(x0, y0, ww, hh, fillColor=None, strokeColor=LINE, strokeWidth=0.5))
        # 구역 이름 — 반투명 흰 박스 위에
        zones = []
        def zone(txt, x, y, col, anchor):
            fs = 7.6; tw = pdfmetrics.stringWidth(txt, KRF, fs) + 3 * mm
            bx = x - tw if anchor == "end" else x
            zones.append((bx - 1, y - 1.6 * mm - 1, bx + tw + 1, y + 3 * mm + 1))
            d.add(Rect(bx, y - 1.6 * mm, tw, 4.6 * mm, fillColor=colors.Color(1, 1, 1, alpha=0.82), strokeColor=col, strokeWidth=0.5, rx=1.6, ry=1.6))
            d.add(String(x - 1.5 * mm if anchor == "end" else x + 1.5 * mm, y - 0.3 * mm, txt, textAnchor=anchor, fillColor=col, fontName=KRF, fontSize=fs))
        zone("추격 매수 — 고래도 늦게 탔다 (주의)", x0 + ww - 1.5 * mm, y0 + hh - 4.3 * mm, CAUT, "end")
        zone("역행 매수 — 고래는 사고, 시장은 팔았다 (관심)", x0 + ww - 1.5 * mm, y0 + 3 * mm, GO, "end")
        zone("차익 실현 — 오른 뒤 고래가 나갔다 (매도 검토)", x0 + 1.5 * mm, y0 + hh - 4.3 * mm, EXIT, "start")
        zone("동반 이탈 — 내리는데 고래도 팔았다 (회피)", x0 + 1.5 * mm, y0 + 3 * mm, STOP, "start")
        d.add(String(x0 + ww / 2, 1.8 * mm, "가로: 편입 순증감 (이번 분기 편입 펀드 수 − 편출 펀드 수)   ·   세로: 1년 주가 등락", textAnchor="middle", fillColor=MUT, fontName=KRF, fontSize=6.8))
        for v in (ymin, 0, ymax):
            d.add(String(x0 - 1.5 * mm, Yraw(v) - 2.2, f"{v:+.0f}%", textAnchor="end", fillColor=INK, fontName=KRF, fontSize=6.6))
        for v in (-xmax + 1, 0, xmax - 1):
            d.add(String(X(v), y0 - 4.4 * mm, f"{v:+.0f}", textAnchor="middle", fillColor=INK, fontName=KRF, fontSize=6.6))
        colmap = ZCOL
        shown = sorted(pts, key=lambda r: -(abs(r["score"]) * 3 + r["n_hold"]))[:24]
        placed = list(zones)      # 라벨 사각형 목록 (충돌 회피용) — 구역 이름 박스 포함
        circles = []
        LFS = 6.8
        def overlaps(rc):
            return any(not (rc[2] < p[0] or rc[0] > p[2] or rc[3] < p[1] or rc[1] > p[3]) for p in placed)
        for r in shown:
            k = next(k for k in Q if r in Q[k]); col = colmap[k]
            x = X(r["score"]); v = r["ret_1y"]; clipped = v > ymax or v < ymin
            y = Yraw(max(ymin, min(ymax, v)))
            rad = 1.9 + min(6.5, r["n_hold"] / 2.6)
            if clipped:      # 범위 밖: 삼각형 화살표 + 실제 값
                y = y0 + hh - 8 * mm if v > ymax else y0 + 8 * mm
                tri = [x - 2.2 * mm, y - 1.6 * mm, x + 2.2 * mm, y - 1.6 * mm, x, y + 1.6 * mm] if v > ymax else \
                      [x - 2.2 * mm, y + 1.6 * mm, x + 2.2 * mm, y + 1.6 * mm, x, y - 1.6 * mm]
                d.add(Polygon(tri, fillColor=col, strokeColor=colors.white, strokeWidth=0.5))
                label = f"{r['sym']} {v:+.0f}%"; rad = 2.2
            else:
                circles.append((x, y, rad, col)); label = r["sym"]
            tw = pdfmetrics.stringWidth(label, KRF, LFS); th = LFS
            cands = [(x + rad + 1.2, y - th * 0.35), (x - rad - 1.2 - tw, y - th * 0.35),
                     (x - tw / 2, y + rad + 1.5), (x - tw / 2, y - rad - th - 0.5),
                     (x + rad + 1.2, y + rad), (x + rad + 1.2, y - rad - th), (x - rad - 1.2 - tw, y + rad), (x - rad - 1.2 - tw, y - rad - th)]
            for lx, ly in cands:
                rc = (lx - 0.6, ly - 0.6, lx + tw + 0.6, ly + th + 0.6)
                if x0 <= rc[0] and rc[2] <= x0 + ww and y0 <= rc[1] and rc[3] <= y0 + hh and not overlaps(rc):
                    break
            else:
                lx, ly = cands[0]; rc = (lx, ly, lx + tw, ly + th)
            placed.append(rc)
            # 라벨 뒤 흰 반투명 배경으로 겹침 완화
            d.add(Rect(rc[0], rc[1], rc[2] - rc[0], rc[3] - rc[1], fillColor=colors.Color(1, 1, 1, alpha=0.65), strokeWidth=0))
            d.add(String(lx, ly, label, fontName=KRF, fontSize=LFS, fillColor=INK))
        for x, y, rad, col in circles:
            d.add(Circle(x, y, rad, fillColor=col, strokeColor=colors.white, strokeWidth=0.6))
        d.add(String(x0 + ww, y0 + hh + 2.6 * mm, "원 크기 = 보유 펀드 수 · 삼각형 = 축 범위를 벗어난 종목(실제 등락 표기)", textAnchor="end", fillColor=MUT, fontName=KRF, fontSize=6.6))
        return d

    # ── 가로 막대 (재사용) ──
    def hbar(rows, labels, vals, colors_, fmt, height, vmin=None, vmax=None):
        d = Drawing(COL, height)
        if not rows:
            d.add(String(4 * mm, height / 2, "자료 없음", fontName=KRF, fontSize=6.6, fillColor=MUT)); return d
        ch = HorizontalBarChart()
        ch.x, ch.y, ch.width, ch.height = 48 * mm, 4 * mm, 38 * mm, height - 8 * mm
        ch.data = [vals[::-1]]
        ch.categoryAxis.categoryNames = [l[:24] for l in labels][::-1]
        ch.categoryAxis.labels.fontName = KRF; ch.categoryAxis.labels.fontSize = 7.1; ch.categoryAxis.labels.dx = -2
        ch.categoryAxis.strokeColor = LINE
        ch.valueAxis.labels.fontName = KRF; ch.valueAxis.labels.fontSize = 6.4
        lo_, hi_ = min(0, min(vals)), max(0, max(vals))
        ch.valueAxis.valueMin = vmin if vmin is not None else (lo_ * 1.3 if lo_ < 0 else 0)
        ch.valueAxis.valueMax = vmax if vmax is not None else (hi_ * 1.25 if hi_ > 0 else 1)
        ch.valueAxis.strokeColor = LINE; ch.valueAxis.gridStrokeColor = PAPER; ch.valueAxis.visibleGrid = True
        ch.bars.strokeWidth = 0; ch.barWidth = 7
        for i, c in enumerate(colors_[::-1]):
            ch.bars[(0, i)].fillColor = c
        d.add(ch)
        vmax_eff = ch.valueAxis.valueMax
        for i, v in enumerate(vals[::-1]):
            y = ch.y + (i + 0.5) * (ch.height / len(vals))
            frac = (v - ch.valueAxis.valueMin) / max(1e-9, vmax_eff - ch.valueAxis.valueMin)
            xv = ch.x + frac * ch.width
            x_zero = ch.x + (0 - ch.valueAxis.valueMin) / max(1e-9, vmax_eff - ch.valueAxis.valueMin) * ch.width
            if v < 0:   # 음수는 0선 오른쪽에 (왼쪽 항목 이름과 겹치지 않게)
                d.add(String(x_zero + 1.5 * mm, y - 1.8, fmt(v), fontName=KRF, fontSize=6.6, fillColor=INK))
            else:
                d.add(String(xv + 1.5 * mm, y - 1.8, fmt(v), fontName=KRF, fontSize=6.6, fillColor=INK))
        return d

    def rank_bars(rows, gkey):
        rows = rows[:10]
        cols = []
        for r in rows:
            _, k = rank_mark(prev, gkey, r["name"], r["rank"])
            cols.append({"up": UP, "down": DOWN, "new": NEW}.get(k, ACC2))
        return hbar(rows, [f"{r['rank']}. {r['name'][:21]}" for r in rows], [r["ret_1y"] for r in rows], cols,
                    lambda v: f"{v:+.0f}%", 36 * mm)

    def sector_bars():
        rows = secs[:9]
        return hbar(rows, [f"{d['sector']} ({d['n']})" for d in rows], [d["score"] for d in rows],
                    [UP if d["score"] > 0 else DOWN for d in rows], lambda v: f"{v:+d}", 36 * mm)

    def index_line():
        d = Drawing(COL, 36 * mm)
        if not idx:
            return d
        spy = yahoo_prices("SPY")
        start = (date.today() - timedelta(days=365)).isoformat()
        days = [k for k in sorted(spy) if k >= start]
        if len(days) < 20:
            return d
        series = {}
        for s in idx["picks"]:
            px = yahoo_prices(s)
            p0 = px_at(px, days[0])
            if p0:
                series[s] = [((px_at(px, k) or p0) / p0) for k in days]
        if not series:
            return d
        basket = [sum(v[i] for v in series.values()) / len(series) for i in range(len(days))]
        spyn = [spy[k] / spy[days[0]] for k in days]
        x0, y0, ww, hh = 10 * mm, 7 * mm, 70 * mm, 23 * mm
        lo, hi = min(min(basket), min(spyn)) * 0.98, max(max(basket), max(spyn)) * 1.02
        def Y(v): return y0 + (v - lo) / (hi - lo) * hh
        for g in range(4):
            gy = y0 + hh * g / 3; gv = lo + (hi - lo) * g / 3
            d.add(Line(x0, gy, x0 + ww, gy, strokeColor=PAPER, strokeWidth=0.6))
            d.add(String(x0 - 1.5 * mm, gy - 1.5, f"{(gv - 1) * 100:+.0f}%", textAnchor="end", fontName=KRF, fontSize=6.3, fillColor=MUT))
        for i, (ser, col, name) in enumerate(((basket, ACC2, f"고래 인덱스 {idx['r1y']:+.0f}%"), (spyn, MUT, f"S&P500 {idx['s1y']:+.0f}%"))):
            pts = []
            for j, v in enumerate(ser):
                pts += [x0 + j / (len(days) - 1) * ww, Y(v)]
            d.add(PolyLine(pts, strokeColor=col, strokeWidth=1.4 if i == 0 else 1.0))
            d.add(Rect(x0 + 2 * mm + i * 36 * mm, 32 * mm, 3 * mm, 1.6 * mm, fillColor=col, strokeWidth=0))
            d.add(String(x0 + 6 * mm + i * 36 * mm, 31.6 * mm, name, fontName=KRF, fontSize=7, fillColor=INK))
        d.add(String(x0, y0 - 4 * mm, days[0][:7], fontName=KRF, fontSize=6.3, fillColor=MUT))
        d.add(String(x0 + ww, y0 - 4 * mm, days[-1][:7], textAnchor="end", fontName=KRF, fontSize=6.3, fillColor=MUT))
        return d

    def flow_bars():
        ins = [a for a in top_flow(agg, 6, "in") if a["score"] > 0]
        outs = [a for a in top_flow(agg, 4, "out") if a["score"] < 0]
        rows = ins + outs[::-1]
        d = Drawing(COL, 36 * mm)
        if not rows:
            return d
        n = len(rows); top, bottom = 34 * mm, 2 * mm; rowh = (top - bottom) / n; cx = 46 * mm; half = 38 * mm
        mx = max(abs(a["score"]) for a in rows) or 1
        d.add(Line(cx, bottom, cx, top, strokeColor=LINE, strokeWidth=0.6))
        for i, a in enumerate(rows):
            y = top - (i + 0.5) * rowh; w_ = abs(a["score"]) / mx * half
            col = UP if a["score"] > 0 else DOWN; xx = cx if a["score"] > 0 else cx - w_
            d.add(Rect(xx, y - rowh * 0.32, w_, rowh * 0.64, fillColor=col, strokeWidth=0))
            lab = stock_label(a["sym"], a["name"])[:17]
            if a["score"] > 0:
                d.add(String(cx - 2 * mm, y - 1.8, lab, fontName=KRF, fontSize=7, textAnchor="end"))
                d.add(String(cx + w_ + 1.5 * mm, y - 1.8, f"+{a['score']}", fontName=KRF, fontSize=7, fillColor=col))
            else:
                d.add(String(cx + 2 * mm, y - 1.8, lab, fontName=KRF, fontSize=7))
                d.add(String(cx - w_ - 1.5 * mm, y - 1.8, f"{a['score']}", fontName=KRF, fontSize=7, fillColor=col, textAnchor="end"))
        return d

    def trend_chart():
        tr = trend_rows(agg, hist, 5)
        d = Drawing(COL, 33 * mm)
        if not tr or len(tr[0]["series"]) < 2:
            d.add(String(4 * mm, 24 * mm, "분기 이력이 2개 이상 쌓이면 표시됩니다", fontName=KRF, fontSize=6.6, fillColor=MUT))
            return d
        qs = [q for q, _ in tr[0]["series"]]
        x0, y0, ww, hh = 8 * mm, 7 * mm, 52 * mm, 22 * mm
        mx = max(v for r in tr for _, v in r["series"]) or 1
        for g in range(5):
            gy = y0 + hh * g / 4
            d.add(Line(x0, gy, x0 + ww, gy, strokeColor=PAPER, strokeWidth=0.6))
            d.add(String(x0 - 1.5 * mm, gy - 1.5, f"{int(mx * g / 4)}", fontName=KRF, fontSize=5.4, fillColor=MUT, textAnchor="end"))
        for j, q in enumerate(qs):
            d.add(String(x0 + (j / max(1, len(qs) - 1)) * ww, y0 - 4.5 * mm, q.replace(" 20", " '"),
                         fontName=KRF, fontSize=5.4, fillColor=MUT, textAnchor="middle"))
        for i, r in enumerate(tr):
            col = PAL[i % len(PAL)]; pts = []
            for j, (_, v) in enumerate(r["series"]):
                pts += [x0 + (j / max(1, len(qs) - 1)) * ww, y0 + v / mx * hh]
            d.add(PolyLine(pts, strokeColor=col, strokeWidth=1.3))
            ly = 29.5 * mm - i * 4.8 * mm
            d.add(Rect(64 * mm, ly - 1, 2.6 * mm, 2.6 * mm, fillColor=col, strokeWidth=0))
            d.add(String(67.5 * mm, ly - 0.6, f"{stock_label(r['sym'], r['name'])[:11]} {r['change']:+d}", fontName=KRF, fontSize=6.8))
        return d

    def change_table():
        rows = []
        for r in items["rank"][:4]:
            if r["kind"] == "new": rows.append(("순위", f"{r['g']} {r['name']}", "신규 진입", NEW))
            elif r["kind"] == "out": rows.append(("순위", f"{r['g']} {r['name']}", "이탈", DOWN))
            else: rows.append(("순위", f"{r['g']} {r['name']}", f"{'▲' if r['move'] > 0 else '▼'}{abs(r['move'])}", UP if r["move"] > 0 else DOWN))
        for r in items["ret"][:3]:
            rows.append(("수익률", f"{r['g']} {r['name']}", f"{r['diff']:+.1f}p", UP if r["diff"] > 0 else DOWN))
        for a in items["hold"][:3]:
            v = "신규" if a["diff"] is None else f"{a['diff']:+d}곳"
            rows.append(("보유수", stock_label(a["sym"], a["name"])[:18], v, NEW if a["diff"] is None else (UP if a["diff"] > 0 else DOWN)))
        for x in items["fresh"][:3]:
            rows.append(("개인", f"{x['who']} {x['tag']}", stock_label(x["sym"], x["issuer"])[:14], NEW))
        rows = rows[:11]
        if not rows:
            msg = "첫 실행 — 내일부터 표시" if items["first"] else "전일 대비 눈에 띄는 변화 없음"
            return pad(Table([[Paragraph(msg, SM)]], colWidths=[COL]))
        data = [["구분", "대상", "변화"]] + [[a, b, c] for a, b, c, _ in rows]
        paint = [(2, i, col) for i, (_, _, _, col) in enumerate(rows, start=1)]
        return tbl(data, [16 * mm, 54 * mm, 20 * mm], (2,), paint, fs=7.2)

    def pie_chart(dd):
        from reportlab.graphics.charts.piecharts import Pie
        d = Drawing(COL, 33 * mm)
        if not dd or not dd.get("holdings"):
            return d
        hs = dd["holdings"][:7]
        other = max(0.0, 100 - sum(h["weight"] for h in hs))
        vals = [h["weight"] for h in hs] + ([other] if other > 0.5 else [])
        labs = [stock_label(h["sym"], h["issuer"])[:14] for h in hs] + (["기타"] if other > 0.5 else [])
        p = Pie(); p.x, p.y, p.width, p.height = 3 * mm, 2 * mm, 29 * mm, 29 * mm
        p.data = vals; p.labels = None; p.slices.strokeWidth = 0.6; p.slices.strokeColor = colors.white
        for i in range(len(vals)):
            p.slices[i].fillColor = PAL[i % len(PAL)] if labs[i] != "기타" else LINE
        d.add(p)
        y = 29.5 * mm
        for i, (l, v) in enumerate(zip(labs, vals)):
            d.add(Rect(52 * mm, y - 1.2, 3 * mm, 3 * mm, fillColor=PAL[i % len(PAL)] if l != "기타" else LINE, strokeWidth=0))
            d.add(String(56.5 * mm, y - 1, f"{l}  {v:.1f}%", fontName=KRF, fontSize=7)); y -= 5.6 * mm
        return d

    def two(a_t, a, b_t, b, a_h="", b_h=""):
        return pad(Table([[sec_half(a_t, a_h), sec_half(b_t, b_h)], [Spacer(1, 3), Spacer(1, 3)], [a, b]],
                         colWidths=[COL + 2 * mm, COL + 2 * mm]))

    # ═══ 1쪽 ═══
    S = [title_band("1쪽 · 오늘 무엇을 볼까 — 고래 40곳의 매집·이탈을 주가·거래량과 대조"
                    + (f" · 전일({prev['date']}) 대비" if prev.get("date") else ""), 1),
         Spacer(1, 5), kpi_cards(), Spacer(1, 6)]
    hc = hero_card()
    if hc is not None:
        S += [hc, Spacer(1, 7)]
    S.append(sec("오늘의 한 줄", "히어로 카드 외에 눈여겨볼 것"))
    S.append(Spacer(1, 3))
    TAGCOL = {"역행 매수": "#2d6a4f", "추격 주의": "#b7791f", "동반 이탈": "#6f6b64", "전일 신호": "#c0392b",
              "고래보다 싸게": "#1d6fb8", "고래 인덱스": "#7b3fa0", "자금 흐름": "#8a5a00"}
    import re as _re
    for h in build_headlines_v2(inst, ppl, agg, Q, disc, mov, idx, hits, secs)[:5]:
        m = _re.match(r"<b>(.+?)</b>", h)
        if m and m.group(1) in TAGCOL:
            h = f'<font color="{TAGCOL[m.group(1)]}"><b>{m.group(1)}</b></font>' + h[m.end():]
        S.append(Paragraph(h, BUL, bulletText="▪"))
    S.append(Spacer(1, 5))
    lv_data = [["실시간 공시 (최근 5영업일)", "누가", "내용", "거래일"]]
    for x in list(live)[:7]:
        lab = stock_label(x.get("sym", ""), x.get("issuer", "")) or x.get("issuer", "")
        det = (f"매수 {x['shares']:,.0f}주" + (f" @ ${x['price']:,.2f}" if x.get("price") else "")
               if x["kind"] == "Form 4" else (f"지분 {x['pct']:.1f}%" if x.get("pct") else "지분 신고"))
        lv_data.append([f"[{x['kind']}] {lab[:20]}", x["who"][:16], det, (x.get("when") or x["filed"])[5:]])
    if len(lv_data) == 1:
        lv_data.append(["최근 5영업일 안에 감시 대상의 Form 4 매수·13D/G가 없습니다", "", "", ""])
    S.append(sec("실시간 신호 — 13F의 45일 공백을 메우는 자료",
                 "Form 4(임원·10% 주주 매수)는 2영업일, 13D/G(5% 지분)는 5영업일 안에 공시"))
    S.append(Spacer(1, 2))
    S.append(tbl(lv_data, [64 * mm, 40 * mm, 56 * mm, 20 * mm], (3,), fs=7.0))
    S.append(Spacer(1, 6))
    S.append(sec("고래 vs 시장 — 어디에 서 있나", "오른쪽 아래(역행 매수)가 관심 구역 · 오른쪽 위(추격)는 주의"))
    S.append(Spacer(1, 2))
    S.append(quadrant_chart())
    S.append(Spacer(1, 5))
    S.append(PageBreak())

    # ═══ 2쪽 · 행동 ═══
    S.append(title_band("2쪽 · 무엇을 사고, 무엇을 점검하나 — 전일 신호 · 평단 · 동시 편입 · 연속 이탈 · 실적", 2))
    S.append(Spacer(1, 4))
    S.append(pad(Table([[sec_half("전일 신호", "고래 3곳 이상 보유 종목 중 어제 3% 이상 등락 또는 거래량 20일 평균 2배 이상"),
                         sec_half("고래 평단 대비 현재가", "분기별 순매수 주식수 × 그 분기 평균가로 추정 · 음수면 고래보다 싸다")]],
                       colWidths=[COL + 2 * mm, COL + 2 * mm])))
    S.append(Spacer(1, 3))

    # 전일 신호 + 고래보다 싸게
    mv_data = [["종목", "등락", "거래량", "보유", "순증감"]]
    mv_paint = []
    for i, r in enumerate(mov[:7], start=1):
        mv_data.append([stock_label(r["sym"], r["name"])[:22], pct(r["ret_1d"], 1),
                        f"{r['vol_ratio']:.1f}배" if r["vol_ratio"] else "—", f"{r['n_hold']}곳", f"{r['score']:+d}"])
        mv_paint += [(1, i, UP if r["ret_1d"] > 0 else DOWN), (4, i, UP if r["score"] > 0 else (DOWN if r["score"] < 0 else MUT))]
    if len(mv_data) == 1:
        mv_data.append(["어제는 3% 이상 등락·거래량 2배 종목 없음", "", "", "", ""])
    mv_t = tbl(mv_data, [40 * mm, 13 * mm, 14 * mm, 12 * mm, 14 * mm], (1, 2, 3, 4), mv_paint)

    dc_data = [["종목", "괴리", "고래 평단", "현재가", "보유"]]
    dc_paint = []
    src_rows = list(cost)[:11] or [{**r, "gap": r.get("vs_qe"), "cost_basis": None} for r in disc[:11]]
    for i, r in enumerate(src_rows[:7], start=1):
        dc_data.append([stock_label(r["sym"], r["name"])[:20], pct(r.get("gap"), 1),
                        f"${r['cost_basis']:,.0f}" if r.get("cost_basis") else "—",
                        f"${r['last']:,.0f}" if r.get("last") else "—", f"{r['n_hold']}곳"])
        if r.get("gap") is not None:
            dc_paint.append((1, i, DOWN if r["gap"] < 0 else UP))
    if len(dc_data) == 1:
        dc_data.append(["해당 없음", "", "", "", ""])
    dc_t = tbl(dc_data, [40 * mm, 15 * mm, 17 * mm, 14 * mm, 12 * mm], (1, 2, 3, 4), dc_paint)
    S.append(pad(Table([[mv_t, dc_t]], colWidths=[COL + 2 * mm, COL + 2 * mm])))
    S.append(Spacer(1, 2))
    S.append(Paragraph("순증감 = 이번 분기 편입 펀드 수 − 편출 펀드 수 (양수면 고래가 사는 중). 괴리 = 고래 추정 평단 대비 현재가이며, 13F 분기 자료로 역산한 값이라 실제 체결가가 아닙니다.", SM))

    S.append(Spacer(1, 6))
    if bt and bt.get("zones"):
        cells = []
        for k in ("contra", "chase", "profit", "flee"):
            v = bt["zones"].get(k); zt, act = ZNAME[k]
            if not v:
                cells.append([Paragraph(f"{zt} · {act}", KPIL), Paragraph("표본 없음", KPIS), Paragraph("", KPIS)])
                continue
            cs = ParagraphStyle("bt", parent=KPIN, textColor=UP if v["avg"] >= 0 else DOWN)
            cells.append([Paragraph(f"{zt} · {act}", KPIL), Paragraph(f"{v['avg']:+.1f}%", cs),
                          Paragraph(f"{v['n']}종목 · 지수 대비 승률 {v['win']:.0f}%", KPIS)])
        bt_t = Table([cells], colWidths=[W / 4] * 4)
        bstyle = [("BACKGROUND", (0, 0), (-1, -1), PAPER), ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                  ("LINEBEFORE", (1, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
        for i, k in enumerate(("contra", "chase", "profit", "flee")):
            bstyle.append(("LINEABOVE", (i, 0), (i, 0), 2.4, ZCOL[k]))
        bt_t.setStyle(TableStyle(bstyle))
        bench = f"같은 기간 S&P500 {bt['bench']:+.1f}%" if bt.get("bench") is not None else ""
        S.append(sec("이 방법이 먹혔나 — 자체 검증",
                     f"{bt['quarter']} 기준으로 구역을 나눈 뒤 지금까지의 수익률 · {bench}"))
        S.append(Spacer(1, 3)); S.append(bt_t); S.append(Spacer(1, 6))

    cl_data = [["종목", "동시 신규", "보유", "가중 순증감", "1년"]]
    cl_paint = []
    for i, r in enumerate(list(clus)[:9], start=1):
        cl_data.append([stock_label(r["sym"], r["name"])[:18], f"{r['cluster']}곳", f"{r['n_hold']}곳",
                        f"{r.get('wscore', 0):+.1f}", pct(r.get("ret_1y"))])
        if r.get("ret_1y") is not None:
            cl_paint.append((4, i, UP if r["ret_1y"] >= 0 else DOWN))
    if len(cl_data) == 1:
        cl_data.append(["3곳 이상 동시 신규 편입 종목 없음", "", "", "", ""])
    wn_data = [["종목", "연속 이탈", "가중 순증감", "보유", "1년"]]
    wn_paint = []
    for i, r in enumerate(list(warn)[:9], start=1):
        wn_data.append([stock_label(r["sym"], r["name"])[:18], f"{abs(r['streak'])}분기",
                        f"{r.get('wscore', 0):+.1f}", f"{r['n_hold']}곳", pct(r.get("ret_1y"))])
        wn_paint += [(1, i, DOWN), (4, i, UP if (r.get("ret_1y") or 0) >= 0 else DOWN)]
    if len(wn_data) == 1:
        wn_data.append(["연속 이탈 추세 종목 없음", "", "", "", ""])
    S.append(pad(Table([[sec_half("동시 편입", "같은 분기에 여러 곳이 한꺼번에 신규로 담은 종목 — 합의가 막 생기는 지점"),
                         sec_half("보유 중이면 점검", "2분기 이상 연속 이탈 + 성적 좋은 곳이 먼저 빠지는 종목")],
                        [Spacer(1, 3), Spacer(1, 3)],
                        [tbl(cl_data, [34 * mm, 16 * mm, 13 * mm, 20 * mm, 12 * mm], (1, 2, 3, 4), cl_paint),
                         tbl(wn_data, [34 * mm, 16 * mm, 20 * mm, 13 * mm, 12 * mm], (1, 2, 3, 4), wn_paint)]],
                       colWidths=[COL + 2 * mm, COL + 2 * mm])))
    S.append(Spacer(1, 6))
    er_data = [["종목", "D-day", "발표일", "보유", "순증감", "1년"]]
    er_paint = []
    for i, r in enumerate(list(earn)[:8], start=1):
        er_data.append([stock_label(r["sym"], r["name"])[:22], f"D-{r['dday']}", r["earn"],
                        f"{r['n_hold']}곳", f"{r['score']:+d}", pct(r.get("ret_1y"))])
        er_paint.append((1, i, UP if r["dday"] <= 2 else INK))
    if len(er_data) == 1:
        er_data.append(["열흘 안에 실적이 잡힌 종목이 없습니다", "", "", "", "", ""])
    S.append(sec("곧 실적 발표", "고래가 3곳 이상 든 종목 중 열흘 안에 실적이 잡힌 것 — 행동 시점이 여기 걸립니다"))
    S.append(Spacer(1, 2))
    S.append(tbl(er_data, [74 * mm, 20 * mm, 30 * mm, 20 * mm, 24 * mm, 22 * mm], (1, 2, 3, 4, 5), er_paint))
    S.append(Spacer(1, 7))

    # ── 색과 용어 읽는 법 ──
    def swatch(col, title, desc):
        t = Table([[Paragraph(f"<b>{title}</b>", ParagraphStyle("sw", fontName=KRF, fontSize=8, leading=10,
                                                               textColor=col))],
                   [Paragraph(desc, SM)]], colWidths=[W / 4 - 4])
        t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 2.4, col), ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                               ("BOX", (0, 0), (-1, -1), 0.3, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (0, 0), 5),
                               ("BOTTOMPADDING", (0, 1), (0, 1), 5), ("TOPPADDING", (0, 1), (0, 1), 0),
                               ("BOTTOMPADDING", (0, 0), (0, 0), 1)]))
        return t
    S.append(sec("읽는 법", "행동 색은 어느 칸에서 보든 뜻이 같습니다. 주가 숫자만 국내 관행대로 빨강이 상승, 파랑이 하락입니다"))
    S.append(Spacer(1, 3))
    leg = Table([[swatch(GO, "관심 · 역행 매수", "고래는 사는데 주가는 내렸다. 지금 사면 고래와 비슷하거나 더 싼 값."),
                  swatch(CAUT, "주의 · 추격 매수", "고래도 이미 오른 뒤 탔다. 따라 사면 고래보다 훨씬 비싸게 산다."),
                  swatch(EXIT, "매도 검토 · 차익 실현", "오른 뒤 고래가 나갔다. 보유 중이면 차익 실현 시점을 따져볼 것."),
                  swatch(STOP, "회피 · 동반 이탈", "내리는데 고래도 팔았다. 새로 들어갈 이유가 약하다.")]],
                colWidths=[W / 4] * 4)
    leg.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 0),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    S.append(leg)
    S.append(Spacer(1, 5))
    S.append(Paragraph(
        "가중 순증감 = 성적 좋은 펀드의 한 표를 더 무겁게 센 편입·편출 합계(수익률 순위 1위 2.5표 ~ 하위 1.0표). "
        "동시 신규 = 같은 분기에 새로 담은 펀드 수로, 누적 보유 수와 다릅니다. "
        "연속 이탈 = 보유 펀드 수가 몇 분기 연달아 줄었는지 — 한 분기짜리 잡음과 추세를 구분합니다.", SM))

    S.append(PageBreak())

    # ═══ 3쪽 · 구조 ═══
    S.append(title_band("3쪽 · 구조와 흐름 — 누가 잘하고, 어디에 돈이 몰리고, 확신은 어디에 있나", 3))
    S.append(Spacer(1, 4))
    S.append(two("기관 TOP 10 · 1년 수익률", rank_bars(inst, "inst"), "유명인 TOP 10 · 1년 수익률", rank_bars(ppl, "ppl"),
                 "13F 보유 복제 기준 · 빨강=순위 상승, 파랑=하락, 보라=신규", "막대 색은 전일 대비 순위 변화"))
    S.append(Spacer(1, 3))
    cv_data = [["종목", "점수", "보유", "평균비중", "1년"]]
    cv_paint = []
    for i, a in enumerate(conv[:10], start=1):
        c = pc.get(a["sym"], {})
        cv_data.append([stock_label(a["sym"], a["name"])[:22], f"{a['conviction']:.0f}", f"{a['n_hold']}곳",
                        f"{a['avg_w']:.1f}%", pct(c.get("ret_1y"))])
        if c.get("ret_1y") is not None:
            cv_paint.append((4, i, UP if c["ret_1y"] >= 0 else DOWN))
    cv_t = tbl(cv_data, [44 * mm, 11 * mm, 12 * mm, 14 * mm, 12 * mm], (1, 2, 3, 4), cv_paint)
    S.append(pad(Table([[sec_half("섹터별 자금 흐름", "섹터 안 종목들의 편입 순증감 합 · 괄호는 종목 수 — 고래 돈이 어디로 가나"),
                         sec_half("컨빅션 TOP 10", "보유 펀드들의 포트 내 비중 합 — 소수가 크게 든 종목이 위로")],
                        [Spacer(1, 3), Spacer(1, 3)], [sector_bars(), cv_t]], colWidths=[COL + 2 * mm, COL + 2 * mm])))
    S.append(Spacer(1, 3))
    S.append(two("고래 인덱스 vs S&P500 · 1년", index_line(), "이번 분기 편입·편출 쏠림", flow_bars(),
                 "컨빅션 TOP 10 동일비중 가상 포트 — 이 방법이 먹히는지 매일 검증", "빨강 = 새로 사거나 늘린 펀드 우세 · 파랑 = 팔거나 줄인 펀드 우세"))
    S.append(Spacer(1, 3))
    top_person = (details or [None])[0]
    S.append(two("분기별 보유 펀드 수 추이", trend_chart(),
                 f"유명인 1위 · {top_person['name']} 포트 구성" if top_person else "유명인 1위 포트", pie_chart(top_person),
                 "최근 분기들에서 보유 펀드 수 변화가 큰 종목 5개", "최신 13F 기준 상위 보유 비중"))
    S.append(Spacer(1, 6))
    S.append(sec("전일 대비 달라진 것", "순위 · 수익률 · 보유 펀드 수 · 개인 편입 중 눈에 띄는 변화만"))
    S.append(Spacer(1, 3))
    S.append(change_table())

    FOOT = ("고래 인덱스 = 컨빅션 상위 10종목 동일비중 가상 포트 (거래비용·리밸런싱 미반영). 수익률·비중은 13F 공시 기준 추정치이며 13F는 분기말 후 45일에 공개됩니다.",
            "출처 13f.info · Yahoo Finance · 투자 자문이 아닙니다.")
    def on_page(canv, doc_):
        canv.saveState()
        canv.setStrokeColor(LINE); canv.setLineWidth(0.4)
        canv.line(10 * mm, 9.5 * mm, 200 * mm, 9.5 * mm)
        canv.setFont(KRF, 6.2); canv.setFillColor(MUT)
        canv.drawString(10 * mm, 6.4 * mm, FOOT[0])
        canv.drawString(10 * mm, 3.4 * mm, FOOT[1])
        canv.drawRightString(200 * mm, 3.4 * mm, f"고래 40 · {today} · {doc_.page}/3")
        canv.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=8 * mm, bottomMargin=12 * mm, title=f"고래 40 {today}", author="whale40")
    doc.build(S, onFirstPage=on_page, onLaterPages=on_page)
    return path


# ════════════════════════════════════════════════════════ 텔레그램
TG_LIMIT = 3900


def tg(token, method, **kw):
    try:
        j = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kw).json()
        if not j.get("ok"):
            log(f"  텔레그램 {method}: {j.get('description')}")
        return j
    except requests.RequestException as e:
        log(f"  텔레그램 {method} 오류: {e}")
        return {"ok": False}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def top3_lines(Q, clus, cost, mov, warn, live):
    """PDF를 열지 않아도 출퇴근길에 읽히는 세 줄."""
    L = []
    if live:
        x = live[0]
        lab = stock_label(x.get("sym", ""), x.get("issuer", "")) or x.get("issuer", "")
        det = (f'{x["shares"]:,.0f}주 매수' if x["kind"] == "Form 4"
               else (f'지분 {x["pct"]:.1f}%' if x.get("pct") else "지분 신고"))
        L.append(f"⚡ <b>{esc(lab)}</b> — {esc(x['who'])}{josa(x['who'])} {esc(det)} ({esc(x['kind'])})")
    if Q and Q.get("contra"):
        r = Q["contra"][0]
        L.append(f"🎯 <b>{esc(stock_label(r['sym'], r['name']))}</b> — 고래 {r['n_in']}곳이 사는데 1년 {r['ret_1y']:+.0f}%")
    if clus:
        r = clus[0]
        L.append(f"🤝 <b>{esc(stock_label(r['sym'], r['name']))}</b> — 이번 분기 {r['cluster']}곳이 동시 신규 편입")
    if cost and cost[0]["gap"] < 0:
        r = cost[0]
        L.append(f"💵 <b>{esc(stock_label(r['sym'], r['name']))}</b> — 고래 평단보다 {abs(r['gap']):.0f}% 싸다")
    if mov:
        r = mov[0]
        L.append(f"📈 <b>{esc(stock_label(r['sym'], r['name']))}</b> — 어제 {r['ret_1d']:+.1f}%"
                 + (f", 거래량 {r['vol_ratio']:.1f}배" if r.get("vol_ratio") else ""))
    if warn:
        r = warn[0]
        L.append(f"⚠️ <b>{esc(stock_label(r['sym'], r['name']))}</b> — {abs(r['streak'])}분기 연속 이탈, 보유 중이면 점검")
    return L[:4]


def summary(inst, ppl, hits, delta, agg, prev=None, live=None, Q=None, clus=None,
            cost=None, mov=None, warn=None):
    prev = prev or {}
    L = [f"🐋 <b>고래 40 · {date.today().isoformat()}</b>", ""]
    t3 = top3_lines(Q, clus or [], cost or [], mov or [], warn or [], live or [])
    if t3:
        L += t3 + ["", "─────────", ""]
    if hits:
        L.append(f"새 13F <b>{len(hits)}건</b>")
        L.append("")
        for h in hits[:6]:
            names = ", ".join(stock_label(x["sym"], x["issuer"]) for x in h["new"][:4])
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

    con = top_consensus(agg, 5)
    if con:
        L += ["", "🤝 <b>함께 보유 TOP 5</b>"]
        for a in con:
            hm, _ = num_mark(prev, "hold", a["sym"], a["n_hold"])
            L.append(f"  {esc(stock_label(a['sym'], a['name']))} — {a['n_hold']}곳"
                     + (f" ({hm})" if hm and hm != "–" else ""))

    flow = [r for r in top_flow(agg, 5, "in") if r["score"] > 0]
    if flow:
        L += ["", "📈 <b>편입 쏠림 TOP 5</b>"]
        for a in flow:
            L.append(f"  {esc(stock_label(a['sym'], a['name']))} — 편입 {a['n_in']} / 편출 {a['n_out']}")

    for rows, gl, gkey in ((inst, "기관", "inst"), (ppl, "유명인", "ppl")):
        if not rows:
            continue
        L += ["", f"🏆 <b>{gl} TOP 5</b> (1년)"]
        for r in rows[:5]:
            rm, _ = rank_mark(prev, gkey, r["name"], r["rank"])
            L.append(f"  {r['rank']}. {esc(r['name'])}  <b>{r['ret_1y']:+.1f}%</b>"
                     + (f"  {rm}" if rm and rm != "–" else ""))

    L += ["", "<i>13F 보유 복제 기준 추정치. 실제 펀드 수익률이 아니며 투자 자문이 아닙니다.</i>"]
    return "\n".join(L)


def send_telegram(text, md_path, pdf_path=None, digest_path=None, mobile_path=None):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        log("텔레그램 설정 없음 — 전송 생략")
        return
    for i in range(0, len(text), TG_LIMIT):
        tg(token, "sendMessage", json={"chat_id": chat, "text": text[i:i + TG_LIMIT],
                                       "parse_mode": "HTML", "disable_web_page_preview": True})
        time.sleep(0.4)

    today = date.today().isoformat()
    for p, fname, mime, cap in (
            (mobile_path, f"고래40-{today}.html", "text/html", f"📱 모바일 리포트 {today} — 열어서 스크롤하세요"),
            (digest_path, f"whale40-대시보드-{today}.pdf", "application/pdf", f"📊 대시보드 PDF {today}"),
            (pdf_path, f"whale40-{today}.pdf", "application/pdf", f"전체 리포트 {today} (PDF)"),
            (md_path, f"whale40-{today}.md", "text/markdown", f"원본 텍스트 {today}")):
        if not p or not os.path.exists(p):
            continue
        try:
            with open(p, "rb") as fh:
                tg(token, "sendDocument", data={"chat_id": chat, "caption": cap},
                   files={"document": (fname, fh, mime)})
            time.sleep(0.6)
        except OSError as e:
            log(f"  첨부 실패 {fname}: {e}")
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
        qs = manager_quarters(f[1], 3, debug=True)
        log(f"  분기 {len(qs)}개: {[(q['quarter'], q['filed']) for q in qs]}")
        if qs:
            hs = holdings(qs[0]["id"], debug=True)
            log(f"  최신 분기 보유 {len(hs)}종목")
            for h in hs[:5]:
                log(f"    {stock_label(h['sym'], h['issuer'])[:26]:26} "
                    f"{h['value']:>14,.0f}천$ {h['shares']:>14,.0f}주")
    px = yahoo_prices("AAPL", debug=True)
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

    log("\n집단 분석 (공동 보유 · 편입/편출 · 분기 추이)")
    agg, hist = crowd_analysis(watch)
    log(f"  종목 {len(agg):,}개 집계, 이력 {len(hist)}개 분기")

    log("\n유명인 개인별 상세 (상위 20명, 그중 10명은 최초 편입 시기까지)")
    details = people_details(ppl, detail_n=20, deep_n=10)
    log(f"  {len(details)}명 집계")

    prev = load_prevday()
    if prev.get("date"):
        log(f"전일({prev['date']}) 자료와 비교해 변화를 표시합니다")

    md = render(inst, ppl, hits, delta, agg, hist, details, prev)
    today = date.today().isoformat()
    (REPORT / f"{today}.md").write_text(md, encoding="utf-8")
    (REPORT / "latest.md").write_text(md, encoding="utf-8")
    jsave(DATA / "ranking.json", {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "institutions": inst, "people": ppl})

    pdf = None
    try:
        pdf = make_pdf(REPORT / f"{today}.pdf", inst, ppl, hits, delta, agg, hist, details, prev)
        if pdf:
            log(f"PDF 생성: report/{today}.pdf")
    except Exception as e:
        log(f"PDF 생성 실패(무시하고 계속): {type(e).__name__}: {e}")

    log("\n실시간 공시 (Form 4 매수 · 13D/G — 13F의 45일 공백을 메움)")
    live = []
    try:
        live = edgar_live(watch)
    except Exception as e:
        log(f"  EDGAR 건너뜀: {type(e).__name__}: {e}")

    digest = mobile = None
    try:
        items = digest_items(inst, ppl, agg, details, hits, prev)
        log("\n실전 분석 (가격 맥락 · 사분면 · 컨빅션 · 평단 · 클러스터 · 검증)")
        top_q = (inst or ppl)[0]["quarter"] if (inst or ppl) else ""
        pc, qe = price_context(agg, top_q)
        Q = quadrant(agg, pc)
        disc = discount_list(agg, pc)
        conv = conviction_list(agg)
        mov = movers(agg, pc)
        secs = sector_flow(agg, pc)
        idx = whale_index(agg, pc)
        clus = cluster_rows(agg, pc)
        cost = cost_rows(agg, pc)
        warn = warning_rows(agg, pc)
        earn = earnings_rows(agg, pc)
        bt = backtest(agg, hist)
        log(f"  가격맥락 {len(pc)} · 사분면 {sum(len(v) for v in Q.values())} · 전일신호 {len(mov)} · "
            f"동시편입 {len(clus)} · 평단 {len(cost)} · 경고 {len(warn)} · 실적 {len(earn)}"
            + (f" · 인덱스 1Y {idx['r1y']:+.1f}%" if idx and idx['r1y'] is not None else "")
            + (f" · 검증 {bt['quarter']}" if bt else ""))
        try:
            mobile = make_mobile_html(REPORT / f"{today}-mobile.html", inst, ppl, agg, hist, details,
                                      items, prev, pc, Q, disc, conv, mov, secs, idx, live,
                                      clus, cost, warn, earn, bt)
            docs = Path("docs")
            docs.mkdir(exist_ok=True)
            (docs / "index.html").write_text(Path(mobile).read_text(encoding="utf-8"), encoding="utf-8")
            log(f"모바일 리포트 생성 → report/{today}-mobile.html (docs/index.html 에도 복사)")
        except Exception as e:
            import traceback
            log(f"모바일 리포트 실패: {type(e).__name__}: {e}")
            log(traceback.format_exc()[-600:])
        digest = make_dashboard_v2(REPORT / f"{today}-digest.pdf", inst, ppl, agg, hist, details, hits,
                                   items, prev, pc, Q, disc, conv, mov, secs, idx,
                                   live, clus, cost, warn, earn, bt)
        if digest:
            log(f"대시보드 생성 → report/{today}-digest.pdf")
    except Exception as e:
        import traceback
        log(f"대시보드 실패(무시하고 계속): {type(e).__name__}: {e}")
        log(traceback.format_exc()[-800:])

    print(md)
    log(f"\n완료 — 새 13F {len(hits)}건 · 실시간 {len(live)}건 → report/{today}.md")
    send_telegram(summary(inst, ppl, hits, delta, agg, prev, live, locals().get("Q"),
                          locals().get("clus"), locals().get("cost"), locals().get("mov"),
                          locals().get("warn")),
                  REPORT / f"{today}.md", pdf, digest, mobile)
    save_daystate(day_state(inst, ppl, agg, details))


if __name__ == "__main__":
    main()
