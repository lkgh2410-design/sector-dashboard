# collector.py
# 구글 트렌드 + 네이버 뉴스 수집 → SQLite 저장
# 매일 1회 자동 수집 (APScheduler)

import sqlite3
import time
import datetime
import requests
from bs4 import BeautifulSoup
from pytrends.request import TrendReq
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
from sectors import SECTORS, get_all_keywords

DB_PATH = "sector_data.db"

# ─────────────────────────────────────────
# 1. DB 초기화
# ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 구글 트렌드: 키워드별 일별 관심도 (0~100)
    c.execute("""
        CREATE TABLE IF NOT EXISTS trend_daily (
            date      TEXT,
            keyword   TEXT,
            big       TEXT,
            mid       TEXT,
            value     REAL,
            PRIMARY KEY (date, keyword)
        )
    """)

    # 네이버 뉴스: 키워드별 일별 기사 수 + 감성
    c.execute("""
        CREATE TABLE IF NOT EXISTS news_daily (
            date      TEXT,
            keyword   TEXT,
            big       TEXT,
            mid       TEXT,
            count     INTEGER,
            pos_count INTEGER,
            neg_count INTEGER,
            PRIMARY KEY (date, keyword)
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] 초기화 완료")


# ─────────────────────────────────────────
# 2. 구글 트렌드 수집
# ─────────────────────────────────────────
# 긍정/부정 키워드 (간단한 사전 기반 감성 분류)
POS_WORDS = ["급등", "상승", "호재", "수주", "흑자", "성장", "기대", "돌파", "신고가",
             "증가", "확대", "수혜", "강세", "반등", "매수"]
NEG_WORDS = ["급락", "하락", "악재", "적자", "감소", "우려", "위기", "부진", "저조",
             "취소", "철회", "손실", "약세", "매도", "폭락"]

def collect_trends(keywords_info: list, date_str: str):
    """
    keywords_info: [{"대분류": ..., "중분류": ..., "키워드": ...}, ...]
    구글 트렌드는 한 번에 최대 5개 키워드만 조회 가능 → 5개씩 나눠서 수집
    """
    pytrends = TrendReq(hl="ko", tz=540)  # 한국 시간
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 5개씩 배치 처리
    batch_size = 5
    for i in range(0, len(keywords_info), batch_size):
        batch = keywords_info[i:i+batch_size]
        kw_list = [item["키워드"] for item in batch]

        try:
            pytrends.build_payload(kw_list, cat=0, timeframe="today 3-m", geo="KR")
            df = pytrends.interest_over_time()

            if df.empty:
                print(f"[트렌드] 데이터 없음: {kw_list}")
                continue

            # 오늘 날짜 행만 추출 (없으면 가장 최근 행)
            if date_str in df.index.strftime("%Y-%m-%d").tolist():
                row = df[df.index.strftime("%Y-%m-%d") == date_str].iloc[0]
            else:
                row = df.iloc[-1]

            for item in batch:
                kw = item["키워드"]
                if kw in df.columns:
                    val = float(row[kw])
                    c.execute("""
                        INSERT OR REPLACE INTO trend_daily
                        (date, keyword, big, mid, value)
                        VALUES (?, ?, ?, ?, ?)
                    """, (date_str, kw, item["대분류"], item["중분류"], val))

            conn.commit()
            print(f"[트렌드] 수집 완료: {kw_list}")
            time.sleep(10)  # 구글 차단 방지 - 넉넉하게

        except Exception as e:
            print(f"[트렌드] 오류 ({kw_list}): {e}")
            time.sleep(5)

    conn.close()


# ─────────────────────────────────────────
# 3. 네이버 뉴스 수집
# ─────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

def collect_naver_news(keywords_info: list, date_str: str):
    """
    네이버 뉴스 검색: 키워드별 오늘 기사 수 + 제목 감성 분석
    """
    import re
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for item in keywords_info:
        kw = item["키워드"]
        try:
            # 날짜 필터 없이 최신순 검색 (날짜 파라미터가 자주 막힘)
            url = (
                f"https://search.naver.com/search.naver"
                f"?where=news&query={requests.utils.quote(kw)}"
                f"&sm=tab_opt&sort=1"
            )
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.content, "html.parser")

            # 기사 제목 추출 - 네이버 HTML 구조 변경 대응, 여러 셀렉터 시도
            titles = []
            for selector in ["a.news_tit", "a.title", ".news_wrap a", ".group_news a"]:
                tags = soup.select(selector)
                if tags:
                    titles = [t.get_text(strip=True) for t in tags if t.get_text(strip=True)]
                    break

            # 기사 수: 총 결과 수 파싱 시도, 실패하면 제목 수로 대체
            count = 0
            for selector in [".title_desc.all_my", ".all_my", ".result_num"]:
                total_tag = soup.select_one(selector)
                if total_tag:
                    nums = re.findall(r"[\d,]+", total_tag.get_text())
                    if nums:
                        count = int(nums[0].replace(",", ""))
                        break

            # 총 결과 수 못 찾으면 제목 수로 대체
            if count == 0:
                count = len(titles)

            # 제목 기반 감성 분류
            pos, neg = 0, 0
            for title in titles:
                for w in POS_WORDS:
                    if w in title:
                        pos += 1
                        break
                for w in NEG_WORDS:
                    if w in title:
                        neg += 1
                        break

            print(f"[뉴스] {kw}: 제목 {len(titles)}개 파싱, 기사 {count}건, 긍정 {pos}, 부정 {neg}")

            # 제목도 0개면 HTML 구조 디버그용 출력
            if len(titles) == 0:
                print(f"  ↳ [경고] 제목 파싱 실패. 응답 상태코드: {resp.status_code}")

            c.execute("""
                INSERT OR REPLACE INTO news_daily
                (date, keyword, big, mid, count, pos_count, neg_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (date_str, kw, item["대분류"], item["중분류"], count, pos, neg))
            conn.commit()

            print(f"[뉴스] {kw}: 기사 {count}건, 긍정 {pos}, 부정 {neg}")
            time.sleep(1)  # 크롤링 간격

        except Exception as e:
            print(f"[뉴스] 오류 ({kw}): {e}")
            time.sleep(3)

    conn.close()


# ─────────────────────────────────────────
# 4. 누락 날짜 backfill
# ─────────────────────────────────────────
def backfill_missing(days: int = 7):
    """
    앱이 꺼져 있던 동안 누락된 날짜 자동 보완
    최근 days일 중 DB에 없는 날짜 수집
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    today = datetime.date.today()
    all_keywords = get_all_keywords()

    for i in range(days, 0, -1):
        d = today - datetime.timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")

        # 해당 날짜 데이터 있는지 확인
        c.execute("SELECT COUNT(*) FROM trend_daily WHERE date=?", (date_str,))
        count = c.fetchone()[0]

        if count == 0:
            print(f"[backfill] {date_str} 누락 → 수집 시작")
            collect_trends(all_keywords, date_str)
            collect_naver_news(all_keywords, date_str)
        else:
            print(f"[backfill] {date_str} 이미 존재 ({count}건)")

    conn.close()


# ─────────────────────────────────────────
# 5. 오늘 수집 (스케줄러가 매일 호출)
# ─────────────────────────────────────────
def collect_today():
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    print(f"\n{'='*40}")
    print(f"[수집 시작] {date_str}")
    print(f"{'='*40}")
    all_keywords = get_all_keywords()
    collect_trends(all_keywords, date_str)
    collect_naver_news(all_keywords, date_str)
    print(f"[수집 완료] {date_str}\n")


# ─────────────────────────────────────────
# 6. 스케줄러 시작 (Streamlit app.py에서 호출)
# ─────────────────────────────────────────
_scheduler = None

def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return  # 이미 실행 중

    init_db()
    backfill_missing(days=7)  # 앱 시작 시 최근 7일 보완

    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    _scheduler.add_job(collect_today, "cron", hour=18, minute=0)  # 매일 오후 6시
    _scheduler.start()
    print("[스케줄러] 시작 완료 - 매일 18:00 자동 수집")


# ─────────────────────────────────────────
# 7. DB 조회 함수 (app.py에서 사용)
# ─────────────────────────────────────────
def load_trend_data(keyword: str, days: int = 30) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql("""
        SELECT date, value
        FROM trend_daily
        WHERE keyword=? AND date>=?
        ORDER BY date
    """, conn, params=(keyword, since))
    conn.close()
    return df

def load_news_data(keyword: str, days: int = 30) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql("""
        SELECT date, count, pos_count, neg_count
        FROM news_daily
        WHERE keyword=? AND date>=?
        ORDER BY date
    """, conn, params=(keyword, since))
    conn.close()
    return df

def load_sector_summary(big: str, days: int = 7) -> pd.DataFrame:
    """대분류 전체 키워드의 최근 평균 관심도 요약"""
    conn = sqlite3.connect(DB_PATH)
    since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql("""
        SELECT t.mid, t.keyword,
               AVG(t.value) as avg_trend,
               SUM(n.count) as total_news,
               SUM(n.pos_count) as pos,
               SUM(n.neg_count) as neg
        FROM trend_daily t
        LEFT JOIN news_daily n
            ON t.date=n.date AND t.keyword=n.keyword
        WHERE t.big=? AND t.date>=?
        GROUP BY t.keyword
        ORDER BY avg_trend DESC
    """, conn, params=(big, since))
    conn.close()
    return df


# 직접 실행 시 즉시 수집 테스트
if __name__ == "__main__":
    init_db()
    collect_today()
