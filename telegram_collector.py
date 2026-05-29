# telegram_collector.py
# 텔레그램 공개 채널 메시지 수집 → 섹터 키워드 카운팅 + 감성 분석
# 실행 전: pip install telethon

import sqlite3
import datetime
import asyncio
import re
from telethon import TelegramClient
from telethon.tl.types import Channel
from sectors import SECTORS, get_all_keywords

DB_PATH = "sector_data.db"

# ─────────────────────────────────────────
# API 설정 - 여기에 직접 입력
# ─────────────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()
API_ID   = os.getenv("TELEGRAM_API_ID", "")
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
if not API_ID or not API_HASH:
    API_ID   = input("텔레그램 API ID 입력: ")
    API_HASH = input("텔레그램 API HASH 입력: ")

# ─────────────────────────────────────────
# 수집할 채널 목록
# ─────────────────────────────────────────
CHANNELS = [
    "insidertracking",
    "bornlupin",
    "kwusa",
    "hanaglobalbottomup",
    "ehdwl",
    "globalmktinsight",
    "haeinlim1",
    "globaletfi",
    "hana_us_stock",
    "mk81_koreainvestment",
    "chinaitev",
    "shinyoungglobal",
    "Barbarianglobal",
    "chunjonghyun",
    "beluga_investment",
    "d_ticker",
    "decoded_narratives",
    "Jstockclass",
    "anakinvest",
    "bumgore",
    "survival_DoPB",
    "yeonsour",
    "growthresearch",
    "yieldnspread",
    "lim_econ",
    "samsung_macro",
    "deandatbond",
    "Macrojunglemicrolens",
    "MacroAllocation",
    "harveyspecterMike",
    "kkkontemp",
    "rafikiresearch",
    "Samsung_Global_AI_SW",
    "seokokang",
    "ai_masters_community",
    "GlobalTechMoon",
    "KISemicon",
    "hyungkeunryu",
    "ITforYouFromHana",
    "merITz_tech",
    "jw_tech",
    "cahier_de_market",
    "theelec",
    "joonsungkim",
    "cjdbj",
    "s_esthermobility",
    "HANAchina",
    "aetherjapanresearch",
    "ShinhanUtilityNewEnergy",
    "eqmirae",
    "easobi",
    "norisknoreturn",
]

# ─────────────────────────────────────────
# DB 초기화 (텔레그램 테이블 추가)
# ─────────────────────────────────────────
def init_telegram_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS telegram_daily (
            date       TEXT,
            channel    TEXT,
            keyword    TEXT,
            big        TEXT,
            mid        TEXT,
            count      INTEGER,
            pos_count  INTEGER,
            neg_count  INTEGER,
            PRIMARY KEY (date, channel, keyword)
        )
    """)
    # 채널별 메시지 원문 저장 (선택)
    c.execute("""
        CREATE TABLE IF NOT EXISTS telegram_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            date       TEXT,
            channel    TEXT,
            message    TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("[텔레그램 DB] 초기화 완료")


# ─────────────────────────────────────────
# 감성 사전
# ─────────────────────────────────────────
POS_WORDS = ["급등", "상승", "호재", "수주", "흑자", "성장", "기대", "돌파", "신고가",
             "증가", "확대", "수혜", "강세", "반등", "매수", "어닝서프라이즈", "beat",
             "outperform", "bullish", "upgrade", "buy"]
NEG_WORDS = ["급락", "하락", "악재", "적자", "감소", "우려", "위기", "부진", "저조",
             "취소", "철회", "손실", "약세", "매도", "폭락", "miss", "downgrade",
             "bearish", "sell", "underperform"]


# ─────────────────────────────────────────
# 메인 수집 함수
# ─────────────────────────────────────────
async def collect_telegram(date_str: str, limit_per_channel: int = 50):
    """
    각 채널에서 오늘 날짜 메시지 수집 → 섹터 키워드 카운팅
    """
    all_keywords = get_all_keywords()
    # 키워드 → (대분류, 중분류) 매핑
    kw_map = {item["키워드"]: (item["대분류"], item["중분류"]) for item in all_keywords}
    # 소문자 매핑도 추가 (영문 키워드 대소문자 무시)
    kw_map_lower = {k.lower(): v for k, v in kw_map.items()}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    async with TelegramClient("sector_session", API_ID, API_HASH) as client:
        for ch in CHANNELS:
            try:
                print(f"[텔레그램] 수집 중: @{ch}")
                messages_today = []

                async for msg in client.iter_messages(ch, limit=limit_per_channel):
                    if not msg.text:
                        continue
                    msg_date = msg.date.strftime("%Y-%m-%d")
                    if msg_date < date_str:
                        break  # 오늘 이전 메시지면 중단
                    if msg_date == date_str:
                        messages_today.append(msg.text)
                        # 원문 저장
                        c.execute("""
                            INSERT OR IGNORE INTO telegram_messages (date, channel, message)
                            VALUES (?, ?, ?)
                        """, (date_str, ch, msg.text[:500]))  # 최대 500자

                if not messages_today:
                    print(f"  ↳ 오늘 메시지 없음")
                    continue

                full_text = " ".join(messages_today).lower()
                print(f"  ↳ 오늘 메시지 {len(messages_today)}개")

                # 키워드별 카운팅
                kw_counts = {}
                for kw, (big, mid) in kw_map.items():
                    pattern = re.compile(re.escape(kw), re.IGNORECASE)
                    cnt = len(pattern.findall(full_text))
                    if cnt > 0:
                        kw_counts[kw] = {"big": big, "mid": mid, "count": cnt}

                # 감성 분류
                pos = sum(1 for w in POS_WORDS if w.lower() in full_text)
                neg = sum(1 for w in NEG_WORDS if w.lower() in full_text)

                # DB 저장
                for kw, info in kw_counts.items():
                    c.execute("""
                        INSERT OR REPLACE INTO telegram_daily
                        (date, channel, keyword, big, mid, count, pos_count, neg_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (date_str, ch, kw, info["big"], info["mid"],
                          info["count"], pos, neg))

                conn.commit()

            except Exception as e:
                print(f"  ↳ 오류 ({ch}): {e}")

    conn.close()
    print(f"\n[텔레그램] 수집 완료: {date_str}")


# ─────────────────────────────────────────
# DB 조회 함수 (app.py에서 사용)
# ─────────────────────────────────────────
def load_telegram_sector_summary(big: str, days: int = 7):
    """대분류별 텔레그램 언급 빈도 요약"""
    import pandas as pd
    conn = sqlite3.connect(DB_PATH)
    since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql("""
        SELECT keyword, mid,
               SUM(count) as total_mentions,
               SUM(pos_count) as pos,
               SUM(neg_count) as neg,
               COUNT(DISTINCT channel) as channel_count
        FROM telegram_daily
        WHERE big=? AND date>=?
        GROUP BY keyword
        ORDER BY total_mentions DESC
    """, conn, params=(big, since))
    conn.close()
    return df

def load_telegram_daily(keyword: str, days: int = 30):
    """키워드별 일별 텔레그램 언급 추이"""
    import pandas as pd
    conn = sqlite3.connect(DB_PATH)
    since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql("""
        SELECT date, SUM(count) as mentions, COUNT(DISTINCT channel) as channels
        FROM telegram_daily
        WHERE keyword=? AND date>=?
        GROUP BY date
        ORDER BY date
    """, conn, params=(keyword, since))
    conn.close()
    return df

def load_telegram_rank(date_str: str):
    """특정 날짜 섹터별 언급 순위"""
    import pandas as pd
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT big, SUM(count) as total_mentions
        FROM telegram_daily
        WHERE date=?
        GROUP BY big
        ORDER BY total_mentions DESC
    """, conn, params=(date_str,))
    conn.close()
    return df


# ─────────────────────────────────────────
# 직접 실행
# ─────────────────────────────────────────
if __name__ == "__main__":
    init_telegram_db()
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    asyncio.run(collect_telegram(date_str))
