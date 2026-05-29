# app.py
# 섹터 관심도 대시보드 - Streamlit
# 실행: streamlit run app.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import datetime
import sqlite3

from sectors import SECTORS, get_all_keywords
from summarizer import load_summary, load_all_summaries
from telegram_collector import (
    load_telegram_sector_summary, load_telegram_daily, load_telegram_rank
)
from collector import (
    start_scheduler, load_trend_data, load_news_data,
    load_sector_summary, DB_PATH
)

# ─────────────────────────────────────────
# 기본 설정
# ─────────────────────────────────────────
st.set_page_config(
    page_title="섹터 관심도 대시보드",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 스케줄러 시작 (앱 최초 로드 시 1회)
if "scheduler_started" not in st.session_state:
    start_scheduler()
    st.session_state["scheduler_started"] = True

# ─────────────────────────────────────────
# 사이드바: 섹터 선택
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📡 섹터 선택")

    big = st.selectbox(
        "대분류",
        list(SECTORS.keys()),
        index=0
    )

    mid = st.selectbox(
        "중분류",
        list(SECTORS[big].keys()),
        index=0
    )

    keywords = SECTORS[big][mid]
    selected_kw = st.selectbox("소분류 키워드", keywords, index=0)

    st.divider()

    # 기간 선택
    period = st.radio(
        "조회 기간",
        ["7일", "30일", "90일"],
        index=1,
        horizontal=True
    )
    days_map = {"7일": 7, "30일": 30, "90일": 90}
    days = days_map[period]

    st.divider()
    st.caption(f"마지막 수집: {datetime.date.today().strftime('%Y-%m-%d')} 18:00")
    if st.button("🔄 지금 수집", use_container_width=True):
        from collector import collect_today
        with st.spinner("수집 중..."):
            collect_today()
        st.success("수집 완료!")
        st.rerun()


# ─────────────────────────────────────────
# 헤더
# ─────────────────────────────────────────
st.markdown(f"# 📡 섹터 관심도 대시보드")
st.markdown(f"**{big}** › **{mid}** › **{selected_kw}** | 최근 {period}")
st.divider()


# ─────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────
trend_df = load_trend_data(selected_kw, days)
news_df  = load_news_data(selected_kw, days)

# DB에 데이터가 없을 때 안내
no_data = trend_df.empty and news_df.empty


# ─────────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────────
tab6, tab4, tab5, tab2, tab3, tab1 = st.tabs(["🤖 AI 섹터 요약", "📅 일별 섹터 순위", "📡 텔레그램 채널", "📰 뉴스 & 감성", "🗺️ 섹터 전체 지도", "📈 구글 트렌드"])


# ── TAB 1: 일별 트렌드 ──────────────────────────────
with tab1:
    if no_data:
        st.info("아직 수집된 데이터가 없습니다. 사이드바에서 '지금 수집' 버튼을 눌러주세요.")
    else:
        # 상단 지표 카드
        col1, col2, col3, col4 = st.columns(4)

        if not trend_df.empty:
            latest_trend = trend_df["value"].iloc[-1]
            prev_trend   = trend_df["value"].iloc[-2] if len(trend_df) > 1 else latest_trend
            delta_trend  = latest_trend - prev_trend
            avg_trend    = trend_df["value"].mean()
            max_trend    = trend_df["value"].max()

            col1.metric("현재 관심도", f"{latest_trend:.0f}",
                        delta=f"{delta_trend:+.0f} (전일 대비)")
            col2.metric(f"{period} 평균", f"{avg_trend:.1f}")
            col3.metric(f"{period} 최고", f"{max_trend:.0f}")

        if not news_df.empty:
            total_news = news_df["count"].sum()
            col4.metric(f"{period} 총 기사", f"{total_news:,}건")

        st.markdown("### 구글 트렌드 관심도 추이")

        if not trend_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=trend_df["date"],
                y=trend_df["value"],
                mode="lines+markers",
                name="관심도",
                line=dict(color="#5B5EF4", width=2.5),
                marker=dict(size=5),
                fill="tozeroy",
                fillcolor="rgba(91,94,244,0.08)"
            ))
            fig.update_layout(
                xaxis_title="날짜",
                yaxis_title="관심도 (0~100)",
                yaxis=dict(range=[0, 105]),
                height=340,
                margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                hovermode="x unified"
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
            st.plotly_chart(fig, use_container_width=True)

        # 같은 중분류 키워드들 비교
        st.markdown(f"### {mid} 키워드 비교 (최근 {period} 평균)")
        compare_rows = []
        conn = sqlite3.connect(DB_PATH)
        since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        for kw in keywords:
            row = pd.read_sql(
                "SELECT AVG(value) as avg FROM trend_daily WHERE keyword=? AND date>=?",
                conn, params=(kw, since)
            )
            avg = row["avg"].iloc[0]
            compare_rows.append({"키워드": kw, "평균 관심도": avg if avg else 0})
        conn.close()

        compare_df = pd.DataFrame(compare_rows).sort_values("평균 관심도", ascending=True)
        fig2 = go.Figure(go.Bar(
            x=compare_df["평균 관심도"],
            y=compare_df["키워드"],
            orientation="h",
            marker_color=[
                "#5B5EF4" if kw == selected_kw else "#C8C9FA"
                for kw in compare_df["키워드"]
            ]
        ))
        fig2.update_layout(
            height=max(200, len(keywords) * 36),
            margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(range=[0, 105])
        )
        st.plotly_chart(fig2, use_container_width=True)


# ── TAB 2: 뉴스 & 감성 ──────────────────────────────
with tab2:
    if no_data:
        st.info("아직 수집된 데이터가 없습니다.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 일별 뉴스 기사 수")
            if not news_df.empty:
                fig3 = go.Figure(go.Bar(
                    x=news_df["date"],
                    y=news_df["count"],
                    marker_color="#1D9E75"
                ))
                fig3.update_layout(
                    height=300,
                    margin=dict(l=0, r=0, t=10, b=0),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig3, use_container_width=True)

        with col2:
            st.markdown("### 일별 감성 분포")
            if not news_df.empty:
                fig4 = go.Figure()
                fig4.add_trace(go.Bar(
                    name="긍정",
                    x=news_df["date"],
                    y=news_df["pos_count"],
                    marker_color="#378ADD"
                ))
                fig4.add_trace(go.Bar(
                    name="부정",
                    x=news_df["date"],
                    y=news_df["neg_count"],
                    marker_color="#E24B4A"
                ))
                fig4.update_layout(
                    barmode="stack",
                    height=300,
                    margin=dict(l=0, r=0, t=10, b=0),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig4, use_container_width=True)

        # 감성 요약 지표
        if not news_df.empty:
            total_pos = news_df["pos_count"].sum()
            total_neg = news_df["neg_count"].sum()
            total_sent = total_pos + total_neg

            st.markdown("### 감성 요약")
            c1, c2, c3 = st.columns(3)
            c1.metric("긍정 기사", f"{total_pos}건")
            c2.metric("부정 기사", f"{total_neg}건")
            if total_sent > 0:
                sentiment_score = total_pos / total_sent * 100
                label = "😊 긍정 우세" if sentiment_score >= 60 else \
                        "😟 부정 우세" if sentiment_score < 40 else "😐 중립"
                c3.metric("감성 점수", f"{sentiment_score:.0f}점", delta=label)

            # 진행바
            if total_sent > 0:
                st.progress(int(sentiment_score), text=f"긍정 {sentiment_score:.0f}% / 부정 {100-sentiment_score:.0f}%")


# ── TAB 3: 섹터 전체 지도 ──────────────────────────────
with tab3:
    st.markdown(f"### {big} 전체 키워드 관심도 순위")
    st.caption(f"최근 {period} 평균 기준 · 관심도 높을수록 현재 시장이 주목 중인 섹터")

    summary_df = load_sector_summary(big, days)

    if summary_df.empty:
        st.info("아직 수집된 데이터가 없습니다.")
    else:
        # 감성 비율 계산
        summary_df["감성"] = summary_df.apply(
            lambda r: f"긍정 {r['pos']/(r['pos']+r['neg'])*100:.0f}%"
            if (r["pos"] + r["neg"]) > 0 else "—", axis=1
        )
        summary_df["관심도"] = summary_df["avg_trend"].fillna(0).round(1)
        summary_df["뉴스(건)"] = summary_df["total_news"].fillna(0).astype(int)

        # 히트맵 스타일 테이블
        display_df = summary_df[["mid", "keyword", "관심도", "뉴스(건)", "감성"]].rename(
            columns={"mid": "중분류", "keyword": "키워드"}
        )

        st.dataframe(
            display_df,
            use_container_width=True,
            height=500,
            column_config={
                "관심도": st.column_config.ProgressColumn(
                    "관심도", min_value=0, max_value=100, format="%.0f"
                ),
                "뉴스(건)": st.column_config.NumberColumn("뉴스(건)", format="%d건"),
            }
        )

        # 트리맵: 섹터별 관심도 시각화
        st.markdown("### 관심도 트리맵")
        if not summary_df.empty and summary_df["관심도"].sum() > 0:
            fig5 = px.treemap(
                summary_df[summary_df["관심도"] > 0],
                path=["mid", "keyword"],
                values="관심도",
                color="관심도",
                color_continuous_scale=["#E6F1FB", "#378ADD", "#0C447C"],
                title=""
            )
            fig5.update_layout(
                height=450,
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig5, use_container_width=True)

# ── TAB 4: 일별 섹터 순위 ──────────────────────────────
with tab4:
    st.markdown("### 📅 일별 섹터 순위 비교")
    st.caption("텔레그램(선행) → 구글 트렌드(동행) → 네이버 뉴스(후행) · 각각 독립 스케일")

    rank_days = st.slider("조회 기간 (일)", min_value=3, max_value=30, value=7, key="rank_days")
    since_rank = (datetime.date.today() - datetime.timedelta(days=rank_days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)

    # ── 구글 트렌드 순위
    trend_rank_df = pd.read_sql("""
        SELECT date, big, AVG(value) as score
        FROM trend_daily WHERE date>=?
        GROUP BY date, big ORDER BY date DESC, score DESC
    """, conn, params=(since_rank,))

    # ── 네이버 뉴스 순위
    news_rank_df = pd.read_sql("""
        SELECT date, big, SUM(count) as score
        FROM news_daily WHERE date>=?
        GROUP BY date, big ORDER BY date DESC, score DESC
    """, conn, params=(since_rank,))

    # ── 텔레그램 순위
    try:
        tg_rank_df = pd.read_sql("""
            SELECT date, big, SUM(count) as score
            FROM telegram_daily WHERE date>=?
            GROUP BY date, big ORDER BY date DESC, score DESC
        """, conn, params=(since_rank,))
    except Exception:
        tg_rank_df = pd.DataFrame()

    conn.close()

    def make_rank_pivot(df, score_fmt=".1f"):
        if df.empty:
            return pd.DataFrame()
        dates = sorted(df["date"].unique(), reverse=True)
        rows = []
        for d in dates:
            day = df[df["date"]==d].sort_values("score", ascending=False).reset_index(drop=True)
            row = {"날짜": d}
            for i, r in day.iterrows():
                val = r["score"] if r["score"] else 0
                fmt = f"{val:{score_fmt}}" if "." in score_fmt else f"{int(val)}"
                row[f"{i+1}위"] = f"{r['big']} ({fmt})"
            rows.append(row)
        return pd.DataFrame(rows)

    # 세 개 순위표 나란히
    col_tg, col_tr, col_nw = st.columns(3)
    with col_tg:
        st.markdown("#### 📡 텔레그램 (선행)")
        st.caption("애널리스트 언급 횟수")
        tg_pivot = make_rank_pivot(tg_rank_df, score_fmt="d")
        if tg_pivot.empty:
            st.info("텔레그램 데이터 없음. telegram_collector.py 실행 필요")
        else:
            st.dataframe(tg_pivot, use_container_width=True, hide_index=True)

    with col_tr:
        st.markdown("#### 🔍 구글 트렌드 (동행)")
        st.caption("일반 대중 검색량 (0~100)")
        tr_pivot = make_rank_pivot(trend_rank_df, score_fmt=".1f")
        if tr_pivot.empty:
            st.info("구글 트렌드 데이터 없음")
        else:
            st.dataframe(tr_pivot, use_container_width=True, hide_index=True)

    with col_nw:
        st.markdown("#### 📰 네이버 뉴스 (후행)")
        st.caption("언론 보도 기사 수")
        nw_pivot = make_rank_pivot(news_rank_df, score_fmt="d")
        if nw_pivot.empty:
            st.info("뉴스 데이터 없음")
        else:
            st.dataframe(nw_pivot, use_container_width=True, hide_index=True)

    st.divider()

    # ── 드릴다운: 날짜 + 대분류 선택 → 소분류 3개 지표 동시 비교
    st.markdown("### 🔍 소분류 드릴다운")
    st.caption("날짜와 대분류 선택 시 소분류별 3개 지표 순위 동시 비교")

    all_dates = sorted(set(
        trend_rank_df["date"].tolist() + news_rank_df["date"].tolist()
    ), reverse=True)

    col_a, col_b = st.columns(2)
    with col_a:
        selected_date = st.selectbox("날짜", options=all_dates if all_dates else ["데이터 없음"], key="drill_date")
    with col_b:
        selected_big_drill = st.selectbox("대분류", options=list(SECTORS.keys()), key="drill_big")

    if all_dates:
        conn = sqlite3.connect(DB_PATH)

        # 구글 트렌드 소분류
        drill_trend = pd.read_sql("""
            SELECT keyword, mid, COALESCE(value,0) as 구글트렌드
            FROM trend_daily WHERE date=? AND big=? ORDER BY value DESC
        """, conn, params=(selected_date, selected_big_drill))

        # 뉴스 소분류
        drill_news = pd.read_sql("""
            SELECT keyword, COALESCE(count,0) as 뉴스기사수
            FROM news_daily WHERE date=? AND big=? ORDER BY count DESC
        """, conn, params=(selected_date, selected_big_drill))

        # 텔레그램 소분류
        try:
            drill_tg = pd.read_sql("""
                SELECT keyword, SUM(count) as 텔레그램언급
                FROM telegram_daily WHERE date=? AND big=? GROUP BY keyword ORDER BY 텔레그램언급 DESC
            """, conn, params=(selected_date, selected_big_drill))
        except Exception:
            drill_tg = pd.DataFrame(columns=["keyword","텔레그램언급"])

        conn.close()

        if not drill_trend.empty:
            # 세 지표 머지
            merged = drill_trend.merge(drill_news, on="keyword", how="left")
            merged = merged.merge(drill_tg, on="keyword", how="left")
            merged = merged.fillna(0)
            merged["구글트렌드"] = merged["구글트렌드"].round(1)
            merged["뉴스기사수"] = merged["뉴스기사수"].astype(int)
            merged["텔레그램언급"] = merged["텔레그램언급"].astype(int)

            # 각 지표별 순위 컬럼 추가
            merged["트렌드순위"] = merged["구글트렌드"].rank(ascending=False).astype(int)
            merged["뉴스순위"] = merged["뉴스기사수"].rank(ascending=False).astype(int)
            merged["텔레순위"] = merged["텔레그램언급"].rank(ascending=False).astype(int)

            st.markdown(f"**{selected_date} · {selected_big_drill}**")

            # 세 컬럼으로 각 지표 순위 표시
            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption("📡 텔레그램 순위")
                st.dataframe(
                    merged.sort_values("텔레그램언급", ascending=False)[["mid","keyword","텔레그램언급"]].rename(
                        columns={"mid":"중분류","keyword":"키워드","텔레그램언급":"언급횟수"}
                    ).assign(순위=range(1, len(merged)+1))[["순위","중분류","키워드","언급횟수"]],
                    use_container_width=True, hide_index=True
                )
            with c2:
                st.caption("🔍 구글 트렌드 순위")
                st.dataframe(
                    merged.sort_values("구글트렌드", ascending=False)[["mid","keyword","구글트렌드"]].rename(
                        columns={"mid":"중분류","keyword":"키워드","구글트렌드":"관심도"}
                    ).assign(순위=range(1, len(merged)+1))[["순위","중분류","키워드","관심도"]],
                    use_container_width=True, hide_index=True,
                    column_config={"관심도": st.column_config.ProgressColumn("관심도", min_value=0, max_value=100, format="%.1f")}
                )
            with c3:
                st.caption("📰 뉴스 순위")
                st.dataframe(
                    merged.sort_values("뉴스기사수", ascending=False)[["mid","keyword","뉴스기사수"]].rename(
                        columns={"mid":"중분류","keyword":"키워드","뉴스기사수":"기사수"}
                    ).assign(순위=range(1, len(merged)+1))[["순위","중분류","키워드","기사수"]],
                    use_container_width=True, hide_index=True,
                    column_config={"기사수": st.column_config.NumberColumn("기사수", format="%d건")}
                )


# ── TAB 5: 텔레그램 채널 ──────────────────────────────
with tab5:
    st.markdown("### 📡 텔레그램 채널 언급 분석")
    st.caption("증권사 리포트 채널 50개 · 섹터 키워드 언급 빈도 집계")

    tg_days = st.slider("조회 기간 (일)", min_value=1, max_value=30, value=7, key="tg_days")
    tg_big  = st.selectbox("대분류", list(SECTORS.keys()), key="tg_big")

    tg_df = load_telegram_sector_summary(tg_big, tg_days)

    if tg_df.empty:
        st.info("텔레그램 데이터가 없습니다. telegram_collector.py를 먼저 실행해주세요.")
        st.code("python telegram_collector.py", language="bash")
    else:
        # 상단 지표
        col1, col2, col3 = st.columns(3)
        col1.metric("총 언급 키워드", f"{len(tg_df)}개")
        col2.metric("총 언급 횟수", f"{int(tg_df['total_mentions'].sum()):,}회")
        col3.metric("언급 채널 수", f"{int(tg_df['channel_count'].max())}개")

        # 언급 순위 테이블
        st.markdown(f"#### {tg_big} 키워드 언급 순위 (최근 {tg_days}일)")
        tg_df.insert(0, "순위", range(1, len(tg_df)+1))
        st.dataframe(
            tg_df[["순위", "mid", "keyword", "total_mentions", "channel_count"]].rename(
                columns={"mid": "중분류", "keyword": "키워드",
                         "total_mentions": "총 언급", "channel_count": "채널 수"}
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "총 언급": st.column_config.ProgressColumn(
                    "총 언급", min_value=0,
                    max_value=int(tg_df["total_mentions"].max()) + 1,
                    format="%d회"
                ),
            }
        )

        # 바차트
        fig7 = go.Figure(go.Bar(
            x=tg_df["total_mentions"],
            y=tg_df["keyword"],
            orientation="h",
            marker_color="#1D9E75",
            text=tg_df["total_mentions"],
            textposition="outside"
        ))
        fig7.update_layout(
            height=max(300, len(tg_df)*28),
            margin=dict(l=0, r=60, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed")
        )
        st.plotly_chart(fig7, use_container_width=True)

        st.divider()

        # 키워드 선택 → 일별 언급 추이
        st.markdown("#### 키워드별 일별 언급 추이")
        tg_kw = st.selectbox("키워드 선택", tg_df["keyword"].tolist(), key="tg_kw")
        tg_daily = load_telegram_daily(tg_kw, tg_days)

        if not tg_daily.empty:
            fig8 = go.Figure()
            fig8.add_trace(go.Scatter(
                x=tg_daily["date"],
                y=tg_daily["mentions"],
                mode="lines+markers",
                name="언급 횟수",
                line=dict(color="#1D9E75", width=2.5),
                fill="tozeroy",
                fillcolor="rgba(29,158,117,0.1)"
            ))
            fig8.add_trace(go.Scatter(
                x=tg_daily["date"],
                y=tg_daily["channels"],
                mode="lines+markers",
                name="언급 채널 수",
                line=dict(color="#EF9F27", width=2, dash="dot"),
                yaxis="y2"
            ))
            fig8.update_layout(
                height=300,
                margin=dict(l=0, r=60, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(title="언급 횟수"),
                yaxis2=dict(title="채널 수", overlaying="y", side="right"),
                hovermode="x unified",
                legend=dict(x=0, y=1)
            )
            st.plotly_chart(fig8, use_container_width=True)

        # 날짜별 대분류 순위
        st.divider()
        st.markdown("#### 날짜별 텔레그램 섹터 언급 순위")
        rank_dates = sorted(
            pd.read_sql("SELECT DISTINCT date FROM telegram_daily ORDER BY date DESC LIMIT 14",
                       sqlite3.connect(DB_PATH))["date"].tolist(),
            reverse=True
        )
        if rank_dates:
            tg_rank_rows = []
            for d in rank_dates:
                rank_d = load_telegram_rank(d)
                row = {"날짜": d}
                for i, r in rank_d.iterrows():
                    row[f"{i+1}위"] = f"{r['big']} ({int(r['total_mentions'])})"
                tg_rank_rows.append(row)
            st.dataframe(pd.DataFrame(tg_rank_rows), use_container_width=True, hide_index=True)


# ── TAB 6: AI 섹터 요약 ──────────────────────────────
with tab6:
    st.markdown("### 🤖 AI 섹터 흐름 요약")
    st.caption("텔레그램 애널리스트 메시지 + 뉴스 + 트렌드 데이터 기반 · Claude 자동 요약")

    SENTIMENT_COLOR = {
        "강한매수": "#1D9E75",
        "매수":     "#5DCAA5",
        "중립":     "#888780",
        "매도":     "#EF9F27",
        "강한매도": "#E24B4A",
    }
    SENTIMENT_EMOJI = {
        "강한매수": "🟢",
        "매수":     "🔵",
        "중립":     "⚪",
        "매도":     "🟠",
        "강한매도": "🔴",
    }

    sum_date = st.selectbox(
        "날짜 선택",
        options=sorted([datetime.date.today().strftime("%Y-%m-%d")], reverse=True),
        key="sum_date"
    )
    sum_big = st.selectbox("대분류", list(SECTORS.keys()), key="sum_big")

    # 전체 요약 한눈에 보기
    st.markdown(f"#### {sum_big} 중분류별 흐름 요약")
    all_sum = load_all_summaries(sum_date)
    big_sum = all_sum[all_sum["big"] == sum_big] if not all_sum.empty else pd.DataFrame()

    if big_sum.empty:
        st.info("요약 데이터가 없습니다. 터미널에서 실행해주세요:")
        st.code("python summarizer.py", language="bash")
    else:
        # 감성 분포 요약 카드
        sentiment_counts = big_sum["sentiment"].value_counts()
        cols = st.columns(len(sentiment_counts))
        for i, (sent, cnt) in enumerate(sentiment_counts.items()):
            color = SENTIMENT_COLOR.get(sent, "#888")
            emoji = SENTIMENT_EMOJI.get(sent, "⚪")
            cols[i].markdown(
                f"<div style='text-align:center;padding:8px;border-radius:8px;"
                f"border:1px solid {color};color:{color}'>"
                f"<b>{emoji} {sent}</b><br>{cnt}개 섹터</div>",
                unsafe_allow_html=True
            )

        st.markdown("")

        # 중분류별 요약 카드
        for _, row in big_sum.iterrows():
            sent = row["sentiment"]
            color = SENTIMENT_COLOR.get(sent, "#888")
            emoji = SENTIMENT_EMOJI.get(sent, "⚪")
            with st.expander(f"{emoji} **{row['mid']}** — {sent} | 📌 {row['top_keywords']}", expanded=False):
                st.markdown(row["summary"])

    st.divider()

    # 특정 중분류 상세 요약
    st.markdown("#### 중분류 상세 요약")
    sum_mid = st.selectbox(
        "중분류 선택",
        list(SECTORS[sum_big].keys()),
        key="sum_mid"
    )

    detail = load_summary(sum_date, sum_big, sum_mid)
    if detail:
        sent = detail["sentiment"]
        color = SENTIMENT_COLOR.get(sent, "#888")
        emoji = SENTIMENT_EMOJI.get(sent, "⚪")

        st.markdown(
            f"<div style='padding:12px;border-radius:8px;border-left:4px solid {color}'>"
            f"<b>{emoji} {sent}</b> &nbsp;|&nbsp; 📌 {detail['top_keywords']}<br><br>"
            f"{detail['summary']}"
            f"<br><br><small style='color:gray'>생성: {detail['generated_at']}</small>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.info(f"{sum_date} · {sum_big} > {sum_mid} 요약 없음")

st.divider()
st.caption("데이터 출처: Google Trends · Naver News | 매일 18:00 자동 수집 | 감성 분석: 키워드 사전 기반")
