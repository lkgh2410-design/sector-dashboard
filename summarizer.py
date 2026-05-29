# summarizer.py
# 중분류별 일별 요약 생성 - Claude API 사용
# 매일 자동 실행 (collector.py 수집 후)

import sqlite3
import datetime
import requests
import json
import pandas as pd

DB_PATH = "sector_data.db"
ANTHROPIC_API_KEY = ""  # 여기에 Claude API 키 입력 or 환경변수로 관리

# ─────────────────────────────────────────
# DB 초기화
# ─────────────────────────────────────────
def init_summary_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS summary_daily (
            date         TEXT,
            big          TEXT,
            mid          TEXT,
            summary      TEXT,
            top_keywords TEXT,
            sentiment    TEXT,
            generated_at TEXT,
            PRIMARY KEY (date, big, mid)
        )
    """)
    conn.commit()
    conn.close()
    print("[요약 DB] 초기화 완료")


# ─────────────────────────────────────────
# Claude API 호출
# ─────────────────────────────────────────
def call_claude(prompt: str) -> str:
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=body,
        timeout=30
    )
    data = resp.json()
    if "error" in data:
        raise Exception(f"API 오류: {data['error']['type']} - {data['error']['message']}")
    if "content" not in data:
        raise Exception(f"예상치 못한 응답: {data}")
    return data["content"][0]["text"]


# ─────────────────────────────────────────
# 중분류별 데이터 수집
# ─────────────────────────────────────────
def get_mid_data(date_str: str, big: str, mid: str) -> dict:
    conn = sqlite3.connect(DB_PATH)

    # 구글 트렌드 top 키워드
    trend_df = pd.read_sql("""
        SELECT keyword, value FROM trend_daily
        WHERE date=? AND big=? AND mid=?
        ORDER BY value DESC LIMIT 5
    """, conn, params=(date_str, big, mid))

    # 뉴스 기사 수 + 감성
    news_df = pd.read_sql("""
        SELECT keyword, count, pos_count, neg_count FROM news_daily
        WHERE date=? AND big=? AND mid=?
        ORDER BY count DESC LIMIT 5
    """, conn, params=(date_str, big, mid))

    # 텔레그램 메시지 원문 (최근 30개)
    try:
        tg_df = pd.read_sql("""
            SELECT DISTINCT m.message FROM telegram_messages m
            JOIN telegram_daily t ON m.date=t.date AND m.channel=t.channel
            WHERE m.date=? AND t.big=? AND t.mid=?
            LIMIT 30
        """, conn, params=(date_str, big, mid))
        tg_messages = tg_df["message"].tolist()
    except Exception:
        tg_messages = []

    conn.close()

    return {
        "trend": trend_df.to_dict("records"),
        "news": news_df.to_dict("records"),
        "tg_messages": tg_messages
    }


# ─────────────────────────────────────────
# 요약 생성
# ─────────────────────────────────────────
def generate_summary(date_str: str, big: str, mid: str) -> dict:
    data = get_mid_data(date_str, big, mid)

    # 데이터 없으면 스킵
    if not data["trend"] and not data["news"] and not data["tg_messages"]:
        return None

    # 프롬프트 구성
    trend_text = ""
    if data["trend"]:
        trend_text = "\n".join([
            f"- {r['keyword']}: 관심도 {r['value']:.0f}/100"
            for r in data["trend"] if r["value"]
        ])

    news_text = ""
    if data["news"]:
        news_text = "\n".join([
            f"- {r['keyword']}: 기사 {r['count']}건 (긍정 {r['pos_count']}, 부정 {r['neg_count']})"
            for r in data["news"]
        ])

    tg_text = ""
    if data["tg_messages"]:
        tg_text = "\n\n".join(data["tg_messages"][:15])  # 최대 15개

    prompt = f"""당신은 주식 시장 섹터 분석가입니다.
아래는 {date_str} 기준 [{big} > {mid}] 섹터의 데이터입니다.

## 구글 트렌드 관심도 (상위 키워드)
{trend_text if trend_text else "데이터 없음"}

## 네이버 뉴스 기사 수
{news_text if news_text else "데이터 없음"}

## 텔레그램 애널리스트 채널 메시지
{tg_text if tg_text else "데이터 없음"}

위 데이터를 바탕으로 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.

{{
  "summary": "3~5문장으로 오늘 이 섹터의 시장 흐름과 투자자 관심도를 요약. 구체적 수치나 키워드 언급 포함.",
  "top_keywords": "오늘 가장 주목받은 키워드 3~5개를 쉼표로 구분",
  "sentiment": "강한매수/매수/중립/매도/강한매도 중 하나"
}}"""

    try:
        response = call_claude(prompt)
        # JSON 파싱
        clean = response.strip()
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        result = json.loads(clean)
        return result
    except Exception as e:
        print(f"  ↳ 파싱 오류: {e}\n  ↳ 응답: {response[:200]}")
        return None


# ─────────────────────────────────────────
# 전체 중분류 요약 실행
# ─────────────────────────────────────────
def summarize_all(date_str: str = None):
    if date_str is None:
        date_str = datetime.date.today().strftime("%Y-%m-%d")

    from sectors import SECTORS
    init_summary_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*40}")
    print(f"[요약 생성] {date_str}")
    print(f"{'='*40}")

    for big, mids in SECTORS.items():
        for mid in mids.keys():
            # 이미 생성된 요약 있으면 스킵
            c.execute("SELECT COUNT(*) FROM summary_daily WHERE date=? AND big=? AND mid=?",
                     (date_str, big, mid))
            if c.fetchone()[0] > 0:
                print(f"[스킵] {big} > {mid} (이미 존재)")
                continue

            print(f"[요약 중] {big} > {mid}...")
            result = generate_summary(date_str, big, mid)

            if result:
                c.execute("""
                    INSERT OR REPLACE INTO summary_daily
                    (date, big, mid, summary, top_keywords, sentiment, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (date_str, big, mid,
                      result.get("summary", ""),
                      result.get("top_keywords", ""),
                      result.get("sentiment", "중립"),
                      now))
                conn.commit()
                print(f"  ↳ 완료: {result.get('sentiment')} | {result.get('top_keywords')}")
            else:
                print(f"  ↳ 데이터 부족으로 스킵")

    conn.close()
    print(f"\n[요약 완료] {date_str}\n")


# ─────────────────────────────────────────
# DB 조회 (app.py에서 사용)
# ─────────────────────────────────────────
def load_summary(date_str: str, big: str, mid: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT summary, top_keywords, sentiment, generated_at
        FROM summary_daily WHERE date=? AND big=? AND mid=?
    """, (date_str, big, mid))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "summary": row[0],
            "top_keywords": row[1],
            "sentiment": row[2],
            "generated_at": row[3]
        }
    return None

def load_all_summaries(date_str: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT big, mid, summary, top_keywords, sentiment
            FROM summary_daily WHERE date=?
            ORDER BY big, mid
        """, conn, params=(date_str,))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key = input("Claude API 키 입력: ").strip()
    ANTHROPIC_API_KEY = api_key
    summarize_all()
