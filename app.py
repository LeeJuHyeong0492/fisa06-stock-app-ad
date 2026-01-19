# =========================
# 표준 라이브러리
# =========================
import datetime
from io import BytesIO
import os

# =========================
# 서드파티 라이브러리
# =========================
import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import plotly.graph_objects as go
from dotenv import load_dotenv

# =========================
# 기본 설정
# =========================
load_dotenv()
st.set_page_config(layout="wide")

TITLE = os.getenv("TITLE", "📊 주가 리스크 분석 대시보드")
st.title(TITLE)

# =========================
# KRX 종목 유틸
# =========================
@st.cache_data
def get_krx_company_list():
    url = "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
    df = pd.read_html(url, header=0, encoding="EUC-KR")[0]
    df = df[["회사명", "종목코드"]]
    df["종목코드"] = df["종목코드"].apply(lambda x: f"{x:06}")
    return df

def get_stock_code(name):
    if name.isdigit() and len(name) == 6:
        return name
    df = get_krx_company_list()
    code = df.loc[df["회사명"] == name, "종목코드"]
    if code.empty:
        raise ValueError("종목을 찾을 수 없습니다.")
    return code.values[0]

# =========================
# Sidebar
# =========================
st.sidebar.header("🔍 조회 조건")

company_name = st.sidebar.text_input("회사명 또는 종목코드")

today = datetime.date.today()
start_date, end_date = st.sidebar.date_input(
    "조회 기간",
    (datetime.date(today.year, 1, 1), today)
)

st.sidebar.markdown("### 📈 이동평균선")
show_ma5 = st.sidebar.checkbox("MA5", True)
show_ma20 = st.sidebar.checkbox("MA20", True)
show_ma60 = st.sidebar.checkbox("MA60", False)

run = st.sidebar.button("분석 실행")

# =========================
# Main
# =========================
if run:
    if not company_name:
        st.warning("회사명을 입력하세요.")
        st.stop()

    with st.spinner("데이터 수집 중..."):
        code = get_stock_code(company_name)
        df = fdr.DataReader(
            code,
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d")
        )

    if df.empty:
        st.info("데이터가 없습니다.")
        st.stop()

    # =========================
    # 지표 계산
    # =========================
    df["Daily_Return"] = df["Close"].pct_change()
    df["Cum_Max"] = df["Close"].cummax()
    df["Drawdown"] = df["Close"] / df["Cum_Max"] - 1

    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA60"] = df["Close"].rolling(60).mean()

    return_rate = (df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100
    volatility = df["Daily_Return"].std() * 100
    downside_vol = df.loc[df["Daily_Return"] < 0, "Daily_Return"].std() * 100
    mdd = df["Drawdown"].min() * 100
    var_95 = df["Daily_Return"].quantile(0.05) * 100

    mdd_date = df["Drawdown"].idxmin()
    peak_price = df.loc[:mdd_date, "Close"].max()
    recovery_df = df.loc[mdd_date:]
    recovery_days = (
        (recovery_df[recovery_df["Close"] >= peak_price].index[0] - mdd_date).days
        if not recovery_df[recovery_df["Close"] >= peak_price].empty
        else None
    )

    mdd_idx = df["Drawdown"].idxmin()  # MDD 발생 날짜

    # MDD 이전 구간에서 최고가(peak) 날짜
    peak_idx = df.loc[:mdd_idx, "Close"].idxmax()

    # =========================
    # 📈 Plotly 캔들 차트
    # =========================
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Candlestick"
    ))

    if show_ma5:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["MA5"],
            mode="lines", name="MA5"
        ))

    if show_ma20:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["MA20"],
            mode="lines", name="MA20"
        ))

    if show_ma60:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["MA60"],
            mode="lines", name="MA60"
        ))

    # 🔴 Drawdown 구간 배경 음영
    fig.add_vrect(
    x0=peak_idx,
    x1=mdd_idx,
    fillcolor="red",
    opacity=0.15,
    layer="below",
    line_width=0,
    annotation_text="MDD 구간",
    annotation_position="top left"
    )

    fig.update_layout(
        title=f"{company_name} 캔들차트 · 이동평균 · Drawdown",
        height=500,
        xaxis_rangeslider_visible=False
    )

    st.plotly_chart(fig, use_container_width=True)

    # =========================
    # 📊 KPI 카드
    # =========================
    st.subheader("📊 수익 · 리스크 요약")

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("수익률", f"{return_rate:.2f}%")
    c2.metric("변동성", f"{volatility:.2f}%")
    c3.metric("MDD", f"{mdd:.2f}%")
    c4.metric("MDD 회복 기간", f"{recovery_days}일" if recovery_days else "미회복")
    c5.metric("하방 변동성", f"{downside_vol:.2f}%")
    c6.metric("VaR (95%)", f"{var_95:.2f}%")

    # =========================
    # 📥 다운로드
    # =========================
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="price")

    st.download_button(
        "📥 엑셀 다운로드",
        data=output.getvalue(),
        file_name=f"{company_name}_리스크분석.xlsx",
        mime="application/vnd.ms-excel"
    )
