# 표준 라이브러리
import datetime
from io import BytesIO

# 서드파티 라이브러리
import datetime
from io import BytesIO
import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import matplotlib.pyplot as plt
import koreanize_matplotlib
import os
from dotenv import load_dotenv
# pip install streamlit pandas finance-datareader matplotlib koreanize-matplotlib python-dotenv

load_dotenv()
title = os.getenv('TITLE')
st.header(title)

def get_krx_company_list() -> pd.DataFrame:
    try:
        # 파이썬 및 인터넷의 기본 문자열 인코딩 방식- UTF-8
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        # MS 프로그램들은 cp949 / 구 몇몇 파일들의 인코딩 방식: EUC-KR
        df_listing = pd.read_html(url, header=0, flavor='bs4', encoding='EUC-KR')[0]
        
        # 필요한 컬럼만 추출 및 종목코드 6자리 포맷 맞추기
        df_listing = df_listing[['회사명', '종목코드']].copy()
        df_listing['종목코드'] = df_listing['종목코드'].apply(lambda x: f'{x:06}')
        return df_listing
    except Exception as e:
        st.error(f"상장사 명단을 불러오는 데 실패했습니다: {e}")
        return pd.DataFrame(columns=['회사명', '종목코드'])

def get_stock_code_by_company(company_name: str) -> str:
    # 만약 입력값이 숫자 6자리라면 그대로 반환
    if company_name.isdigit() and len(company_name) == 6:
        return company_name
    
    company_df = get_krx_company_list()
    codes = company_df[company_df['회사명'] == company_name]['종목코드'].values
    if len(codes) > 0:
        return codes[0]
    else:
        raise ValueError(f"'{company_name}'을 찾을 수 없습니다. 종목코드 6자리를 직접 입력해보세요.")

company_name = st.sidebar.text_input('조회할 회사를 입력하세요')
# https://docs.streamlit.io/develop/api-reference/widgets/st.date_input

today = datetime.datetime.now()
jan_1 = datetime.date(today.year, 1, 1)

selected_dates = st.sidebar.date_input(
    '조회할 날짜를 입력하세요',
    (jan_1, today),
    format="MM.DD.YYYY",
)

# st.write(selected_dates)

confirm_btn = st.sidebar.button('조회하기') # 클릭하면 True

# --- 메인 로직 ---
if confirm_btn:
    if not company_name:
        st.warning("회사명을 입력하세요.")
    else:
        try:
            with st.spinner("데이터 수집 중..."):
                stock_code = get_stock_code_by_company(company_name)
                start = selected_dates[0].strftime("%Y%m%d")
                end = selected_dates[1].strftime("%Y%m%d")
                price_df = fdr.DataReader(stock_code, start, end)

            if price_df.empty:
                st.info("해당 기간 데이터가 없습니다.")
            else:
                st.subheader(f"[{company_name}] 주가 데이터")
                st.dataframe(price_df.tail(10), use_container_width=True)

                # =========================
                # 📊 수익 & 리스크 계산
                # =========================
                price_df['Daily_Return'] = price_df['Close'].pct_change()
                price_df['Cum_Max'] = price_df['Close'].cummax()
                price_df['Drawdown'] = price_df['Close'] / price_df['Cum_Max'] - 1

                start_price = price_df['Close'].iloc[0]
                end_price = price_df['Close'].iloc[-1]
                return_rate = (end_price / start_price - 1) * 100

                volatility = price_df['Daily_Return'].std() * 100
                downside_vol = price_df.loc[
                    price_df['Daily_Return'] < 0,
                    'Daily_Return'
                ].std() * 100

                mdd = price_df['Drawdown'].min() * 100

                # MDD 회복 기간
                mdd_date = price_df['Drawdown'].idxmin()
                peak_price = price_df.loc[:mdd_date, 'Close'].max()
                recovery_df = price_df.loc[mdd_date:]
                recovery = recovery_df[recovery_df['Close'] >= peak_price]
                recovery_days = (
                    (recovery.index[0] - mdd_date).days
                    if not recovery.empty else None
                )

                var_95 = price_df['Daily_Return'].quantile(0.05) * 100

                # =========================
                # 📊 요약 출력
                # =========================
                st.subheader("📊 수익 · 리스크 요약")

                col1, col2, col3 = st.columns(3)

                col1.metric("수익률", f"{return_rate:.2f}%")
                col1.metric("변동성", f"{volatility:.2f}%")

                col2.metric("MDD", f"{mdd:.2f}%")
                col2.metric(
                    "MDD 회복 기간",
                    f"{recovery_days}일" if recovery_days else "미회복"
                )

                col3.metric("하방 변동성", f"{downside_vol:.2f}%")
                col3.metric("VaR (95%)", f"{var_95:.2f}%")

                # =========================
                # 📈 이동평균선
                # =========================
                price_df['MA5'] = price_df['Close'].rolling(5).mean()
                price_df['MA20'] = price_df['Close'].rolling(20).mean()
                price_df['MA60'] = price_df['Close'].rolling(60).mean()

                fig, ax = plt.subplots(figsize=(12, 5))

                price_df['Close'].plot(ax=ax, label="종가", linewidth=2)
                price_df['MA5'].plot(ax=ax, label="MA5", linestyle="--")
                price_df['MA20'].plot(ax=ax, label="MA20", linestyle="-.")
                price_df['MA60'].plot(ax=ax, label="MA60", linestyle=":")

                # 🔴 Drawdown 구간 전체 음영
                y_min = price_df[['Low', 'Close']].min().min()
                y_max = price_df[['High', 'Close']].max().max()

                ax.fill_between(
                    price_df.index,
                    y1=y_min,
                    y2=y_max,
                    where=price_df['Drawdown'] < 0,
                    color="red",
                    alpha=0.15,
                    label="Drawdown 구간"
                )

                ax.set_title(f"{company_name} 종가 · 이동평균 · 리스크")
                ax.set_ylabel("가격")
                ax.legend()
                ax.grid(True)

                st.pyplot(fig)

                # =========================
                # 📥 엑셀 다운로드
                # =========================
                output = BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    price_df.to_excel(writer, sheet_name="price")

                st.download_button(
                    label="📥 엑셀 다운로드",
                    data=output.getvalue(),
                    file_name=f"{company_name}_주가_리스크분석.xlsx",
                    mime="application/vnd.ms-excel"
                )

        except Exception as e:
            st.error(f"오류 발생: {e}")

    