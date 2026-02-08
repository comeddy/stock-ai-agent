#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re
from stock_agent import get_stock_price, analyze_stock_trend, analyze_company_news, get_ticker, get_fundamental_analysis, get_institutional_holders, get_macro_indicators
from strands import Agent
from strands.models import BedrockModel

# 페이지 설정
st.set_page_config(
    page_title="주식 정보 AI Agent",
    page_icon="📊",
    layout="wide"
)

# 세션 상태 초기화
if 'bedrock_model' not in st.session_state:
    st.session_state.bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        region_name="us-east-1"
    )

if 'system_prompt' not in st.session_state:
    st.session_state.system_prompt = """당신은 주식 정보 도우미입니다.

**사용자 입력 처리:**
- 사용자가 "삼성전자", "삼성전자 주가", "삼성전자 분석" 등을 입력하면 회사명은 "삼성전자"입니다
- "주가", "분석", "매수", "매도" 같은 키워드는 무시하고 회사명만 추출하세요
- 예: "삼성전자 주가분석" → company_name="삼성전자"
- 예: "SK 하이닉스 매수 타이밍" → company_name="SK 하이닉스"

**중요: 도구 호출 시 회사명을 절대 번역하지 마세요**
- 사용자: "삼성전자" → company_name="삼성전자" (O)
- 사용자: "삼성전자" → company_name="Samsung Electronics" (X)

**종합 분석 요청 시 반드시 6가지 도구 모두 사용:**
1. get_stock_price - 현재가 확인
2. analyze_stock_trend - 기술적 분석
3. get_fundamental_analysis - 기본적 분석 (밸류에이션, 수익성, 재무건전성, 성장성)
4. get_institutional_holders - 수급 분석 (기관/외국인 보유현황)
5. get_macro_indicators - 거시경제 지표 (지수, VIX, 금리, 환율, 원자재)
6. analyze_company_news - 뉴스 감성 분석

**주가 분석 시 매수/매도 신호를 명확히 표시:**

✅ 매수 신호 (긍정적):
- 현재가 > 이동평균선 (상승 추세)
- RSI < 30 (과매도, 반등 가능성)
- RSI 30-50 (안정적 매수 구간)
- 거래량 증가 + 가격 상승
- 골든크로스 발생 (단기 이평선이 장기 이평선 상향 돌파)
- MACD > Signal (상승 모멘텀)
- 볼린저밴드 하단 근처 (20% 이하)

❌ 매도 신호 (부정적):
- 현재가 < 이동평균선 (하락 추세)
- RSI > 70 (과매수, 조정 가능성)
- 거래량 감소 + 가격 하락
- 데드크로스 발생 (단기 이평선이 장기 이평선 하향 돌파)
- MACD < Signal (하락 모멘텀)
- 볼린저밴드 상단 근처 (80% 이상)

⚠️ 중립 (관망):
- RSI 50-70 (상승 중이나 과열 주의)
- 볼린저밴드 중간 (40-60%)
- 혼조된 신호들

**분석 결과 형식 (반드시 실제 데이터 값을 포함하세요):**
```
📊 종합 판단: [매수 고려 / 매도 고려 / 관망 추천]

💰 현재 주가 정보:
- 현재가: {실제 current_price 값}
- 전일 대비: {실제 change_percent 값}%

📈 기술적 분석 근거:

🎯 RSI (상대강도지수): {실제 rsi 값}
   → 의미: 0~100 사이 값으로 주가의 과열/침체 정도를 측정
   → 해석: 30 이하=과매도(반등 기대), 70 이상=과매수(조정 주의), 30~70=중립
   → 현재 판단: [과매수/과매도/중립]

📊 이동평균선: 현재가 vs MA5({값}), MA20({값}), MA60({값})
   → 의미: 일정 기간 평균 주가로 추세 방향 파악
   → 해석: 현재가 > 이동평균 = 상승추세, 현재가 < 이동평균 = 하락추세
   → 현재 판단: [상승/하락 추세]

📉 MACD: {실제 macd 값} vs Signal {실제 signal 값}
   → 의미: 단기/장기 이동평균 차이로 추세 전환점 포착
   → 해석: MACD > Signal = 상승 모멘텀, MACD < Signal = 하락 모멘텀
   → 현재 판단: [상승/하락 모멘텀]

📏 볼린저밴드: {실제 bb_position 값}%
   → 의미: 주가 변동 범위를 나타내며 0%=하단, 100%=상단
   → 해석: 20% 이하=저평가 구간, 80% 이상=고평가 구간
   → 현재 판단: [저평가/적정/고평가 구간]

⚡ 크로스 신호: {골든크로스/데드크로스/없음}
   → 의미: 단기 이동평균이 장기 이동평균을 교차하는 시점
   → 해석: 골든크로스=매수신호(상승전환), 데드크로스=매도신호(하락전환)

💰 기본적 분석 근거:

📊 밸류에이션: P/E {실제 값}, P/B {실제 값}
   → 해석: P/E < 15 저평가, 15-25 적정, > 25 고평가
   → 현재 판단: [저평가/적정/고평가]

📈 수익성: ROE {실제 값}%, 영업이익률 {실제 값}%
   → 해석: ROE > 15% 우수, 10-15% 양호, < 10% 개선 필요
   → 현재 판단: [우수/양호/개선필요]

🏦 재무건전성: 부채비율 {실제 값}%, 유동비율 {실제 값}
   → 해석: 부채비율 < 100% 안정, 유동비율 > 1.5 양호
   → 현재 판단: [안정/보통/위험]

🚀 성장성: 매출성장률 {실제 값}%, 이익성장률 {실제 값}%
   → 해석: 성장률 > 20% 고성장, 0-20% 성장, < 0% 역성장
   → 현재 판단: [고성장/성장/역성장]

🏛️ 수급 현황: 기관 보유 {실제 값}%, 내부자 보유 {실제 값}%
   → 해석: 기관 보유 증가 = 긍정 신호
   → 현재 판단: [긍정/중립/부정]

🌍 거시경제 환경:

📊 주요 지수: S&P500 {값}({변동률}%), KOSPI {값}({변동률}%)
   → 의미: 글로벌 주식시장 전반적 흐름 파악
   → 해석: 지수 상승 = 위험자산 선호, 지수 하락 = 안전자산 선호
   → 현재 판단: [상승장/하락장/혼조]

😰 VIX (공포지수): {실제 값}
   → 의미: 시장 변동성과 투자심리를 측정 (0-40+ 범위)
   → 해석: 15 이하=안정, 15-20=중립, 20-30=공포, 30+=극심한 공포
   → 현재 판단: [안정/중립/공포/극심한 공포]

🏦 미국 국채 금리: 10Y {값}%
   → 의미: 무위험 수익률 기준, 금리 상승시 주식 매력도 하락
   → 해석: 금리 급등 = 주식 약세, 금리 하락 = 주식 강세
   → 현재 판단: [주식 우호적/중립/주식 비우호적]

💱 환율: USD/KRW {값}원
   → 의미: 원화 가치, 수출기업/수입기업 영향
   → 해석: 원화 약세 = 수출기업 긍정, 원화 강세 = 수입기업 긍정
   → 현재 판단: [원화 강세/중립/원화 약세]

🛢️ 원자재: 금 ${값}, 유가 ${값}
   → 의미: 인플레이션 및 경기 전망 지표
   → 해석: 금 상승 = 안전자산 선호, 유가 상승 = 인플레 우려
   → 현재 판단: [위험선호/안전선호/중립]

✅ 긍정 요인:
- [기술적 분석 + 기본적 분석 기반 구체적 이유]

❌ 부정 요인:
- [기술적 분석 + 기본적 분석 기반 구체적 이유]

📰 뉴스 분석:
- [실제 뉴스 제목] → [긍정/부정 판단 및 이유]

⚠️ 투자 판단은 본인의 책임이며, 이 분석은 참고용입니다.
```

반드시 한글로 답변하세요.
"""

if 'history' not in st.session_state:
    st.session_state.history = []

# 헤더
st.title("📊 주식 정보 AI Agent")
st.markdown("실시간 주가 조회 및 AI 기반 투자 분석")

# 사이드바
with st.sidebar:
    st.header("📌 사용 가이드")
    st.markdown("""
    **지원 기능:**
    - 실시간 주가 조회
    - 기술적 분석 (이동평균, RSI, MACD 등)
    - 뉴스 감성 분석
    
    **입력 예시:**
    - 삼성전자
    - 삼성전자 주가분석
    - SK 하이닉스 매수 타이밍
    - Amazon
    """)
    
    st.divider()
    
    st.header("⭐ 관심 종목")
    
    # 세션 상태에 관심 종목 리스트 초기화
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = ["삼성전자", "SK하이닉스", "네이버"]
    
    # 관심 종목 추가 폼
    with st.form("add_watchlist"):
        new_stock = st.text_input("종목 추가", placeholder="예: 카카오, Apple")
        submitted = st.form_submit_button("➕ 추가")
        if submitted and new_stock:
            if new_stock not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_stock)
                st.success(f"{new_stock} 추가됨!")
            else:
                st.warning("이미 등록된 종목입니다.")
    
    # 관심 종목 목록 (클릭 가능)
    st.markdown("**등록된 종목:**")
    for stock in st.session_state.watchlist:
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button(stock, key=f"watch_{stock}", use_container_width=True):
                st.session_state.company_input = stock
                st.rerun()
        with col2:
            if st.button("🗑️", key=f"del_{stock}"):
                st.session_state.watchlist.remove(stock)
                st.rerun()
    
    st.divider()
    
    st.header("📈 지원 종목")
    st.markdown("""
    **한국 주식:**
    - 삼성전자, SK하이닉스
    - 네이버, 카카오
    - 현대차, LG전자, 포스코
    
    **미국 주식:**
    - Amazon, Apple, Tesla
    - Google, Microsoft, Meta, Nvidia
    """)

# 메인 영역
col1, col2 = st.columns([3, 1])

with col1:
    user_input = st.text_input(
        "회사명을 입력하세요",
        placeholder="예: 삼성전자, Amazon, SK 하이닉스",
        key="company_input"
    )

with col2:
    analyze_button = st.button("🔍 분석하기", type="primary", use_container_width=True)

# 기간 선택 (분석 전에 표시)
if 'selected_period' not in st.session_state:
    st.session_state.selected_period = "3개월"

period_option = st.radio(
    "기간 선택",
    ["3개월", "6개월", "1년", "5년"],
    horizontal=True,
    index=["3개월", "6개월", "1년", "5년"].index(st.session_state.selected_period),
    key="period_radio"
)

# 기간 변경 시 자동 재분석
if period_option != st.session_state.selected_period:
    st.session_state.selected_period = period_option
    if user_input:
        st.rerun()

period_map = {
    "3개월": "3mo",
    "6개월": "6mo",
    "1년": "1y",
    "5년": "5y"
}
period = period_map[period_option]

# 분석 실행
if (analyze_button or st.session_state.get('auto_analyze')) and user_input:
    with st.spinner("분석 중..."):
        try:
            # 자동 분석 플래그 설정
            st.session_state.auto_analyze = True

            # 회사명 추출 (키워드 제거)
            keywords = ['주가', '분석', '매수', '매도', '타이밍', '예측', '전망', '추천']
            company_name = user_input
            for keyword in keywords:
                company_name = company_name.replace(keyword, '').strip()
            # 빈 문자열이면 원본 사용
            if not company_name:
                company_name = user_input.split()[0]
            ticker = get_ticker(company_name)
            
            # 주가 데이터 조회
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            
            if not df.empty:
                # 탭 생성
                tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 차트", "🔮 예측", "📊 기술적 분석", "💰 펀더멘털", "🌍 거시경제", "📰 뉴스"])
                
                with tab1:
                    # 주가 차트 (Toss 스타일)
                    fig = go.Figure()
                    
                    # 캔들스틱 차트
                    fig.add_trace(go.Candlestick(
                        x=df.index,
                        open=df['Open'],
                        high=df['High'],
                        low=df['Low'],
                        close=df['Close'],
                        name='주가',
                        increasing_line_color='#FF6B6B',
                        decreasing_line_color='#4ECDC4'
                    ))
                    
                    # 이동평균선
                    df['MA5'] = df['Close'].rolling(window=5).mean()
                    df['MA20'] = df['Close'].rolling(window=20).mean()
                    
                    fig.add_trace(go.Scatter(
                        x=df.index, y=df['MA5'],
                        name='MA5', line=dict(color='#FFE66D', width=1)
                    ))
                    fig.add_trace(go.Scatter(
                        x=df.index, y=df['MA20'],
                        name='MA20', line=dict(color='#A8DADC', width=1)
                    ))
                    
                    # 레이아웃
                    fig.update_layout(
                        title=f"{company_name} 주가 추이 ({period_option})",
                        yaxis_title="가격",
                        xaxis_title="날짜",
                        template="plotly_white",
                        height=500,
                        hovermode='x unified',
                        xaxis_rangeslider_visible=False
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 주요 지표 카드
                    current_price = df['Close'].iloc[-1]
                    prev_price = df['Close'].iloc[-2] if len(df) > 1 else current_price
                    change = current_price - prev_price
                    # ZeroDivision 방지
                    change_pct = (change / prev_price) * 100 if prev_price > 0 else 0

                    # 통화 단위 결정 (한국 주식: 원, 미국 주식: $)
                    currency = "원" if ticker.endswith(".KS") else "$"
                    price_format = f"{current_price:,.0f}{currency}" if ticker.endswith(".KS") else f"${current_price:,.2f}"
                    high_format = f"{df['High'].max():,.0f}{currency}" if ticker.endswith(".KS") else f"${df['High'].max():,.2f}"
                    low_format = f"{df['Low'].min():,.0f}{currency}" if ticker.endswith(".KS") else f"${df['Low'].min():,.2f}"

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("현재가", price_format, f"{change_pct:+.2f}%")
                    with col2:
                        st.metric("최고가", high_format)
                    with col3:
                        st.metric("최저가", low_format)
                    with col4:
                        st.metric("거래량", f"{df['Volume'].iloc[-1]:,.0f}")
                
                with tab2:
                    # AI 기반 미래 예측
                    st.subheader("🔮 AI 주가 예측")
                    
                    # 예측 기간 선택
                    forecast_period = st.selectbox(
                        "예측 기간",
                        ["7일", "1개월", "3개월", "6개월"],
                        key="forecast_period"
                    )
                    
                    if st.button("🤖 AI 예측 생성", use_container_width=True):
                        with st.spinner("AI가 종합 분석 중..."):
                            try:
                                # 기술적 분석 데이터 수집
                                analysis = analyze_stock_trend(company_name, period)
                                news = analyze_company_news(company_name)
                                price_info = get_stock_price(company_name)
                                # 기본적 분석 데이터 수집
                                fundamental = get_fundamental_analysis(company_name)
                                holders = get_institutional_holders(company_name)
                                # 거시경제 데이터 수집
                                macro = get_macro_indicators()

                                current_price = float(price_info.get('current_price', 0))

                                # 펀더멘털 데이터 추출
                                val = fundamental.get('valuation', {}) if 'error' not in fundamental else {}
                                prof = fundamental.get('profitability', {}) if 'error' not in fundamental else {}
                                health = fundamental.get('financial_health', {}) if 'error' not in fundamental else {}
                                growth = fundamental.get('growth', {}) if 'error' not in fundamental else {}

                                # AI 예측 프롬프트
                                forecast_agent = Agent(
                                    model=st.session_state.bedrock_model,
                                    tools=[],
                                    system_prompt=f"""당신은 전문 주식 애널리스트입니다.

다음 데이터를 종합 분석하여 {forecast_period} 후 주가를 예측하세요:

**현재 주가 정보:**
- 회사: {company_name}
- 현재가: {current_price}
- 전일 대비: {price_info.get('change_percent')}%

**기술적 분석:**
- RSI: {analysis.get('rsi')}
- MA5: {analysis.get('ma5')}, MA20: {analysis.get('ma20')}, MA60: {analysis.get('ma60')}
- MACD: {analysis.get('macd')}, Signal: {analysis.get('macd_signal')}
- 볼린저밴드 위치: {analysis.get('bb_position')}%
- 크로스 신호: {analysis.get('cross_signal')}
- 변동성: {analysis.get('volatility')}%
- 거래량 비율: {analysis.get('volume_ratio')}%

**기본적 분석 (펀더멘털):**
- P/E (주가수익비율): {val.get('pe_ratio')}
- P/B (주가순자산비율): {val.get('pb_ratio')}
- ROE (자기자본이익률): {prof.get('roe')}%
- 영업이익률: {prof.get('operating_margin')}%
- 부채비율: {health.get('debt_to_equity')}%
- 매출 성장률: {growth.get('revenue_growth')}%
- 이익 성장률: {growth.get('earnings_growth')}%

**수급 현황:**
- 기관 보유비율: {holders.get('institutional_percent') if 'error' not in holders else 'N/A'}%
- 내부자 보유비율: {holders.get('insider_percent') if 'error' not in holders else 'N/A'}%

**거시경제 환경:**
- 시장 심리: {macro.get('market_sentiment', 'N/A')}
- S&P 500: {macro.get('indices', {}).get('S&P 500', {}).get('price', 'N/A')} ({macro.get('indices', {}).get('S&P 500', {}).get('change_percent', 0):+.2f}%)
- KOSPI: {macro.get('indices', {}).get('KOSPI', {}).get('price', 'N/A')} ({macro.get('indices', {}).get('KOSPI', {}).get('change_percent', 0):+.2f}%)
- VIX (공포지수): {macro.get('volatility', {}).get('VIX', {}).get('value', 'N/A')} ({macro.get('volatility', {}).get('VIX', {}).get('interpretation', 'N/A')})
- 미국 10년물 금리: {macro.get('bonds', {}).get('US 10Y Treasury', {}).get('yield', 'N/A')}%
- USD/KRW 환율: {macro.get('currencies', {}).get('USD/KRW', {}).get('rate', 'N/A')}원
- 금 가격: ${macro.get('commodities', {}).get('Gold', {}).get('price', 'N/A')}
- 유가 (WTI): ${macro.get('commodities', {}).get('Crude Oil (WTI)', {}).get('price', 'N/A')}

**최근 뉴스:**
{chr(10).join([f"- {item['title']}" for item in news.get('news', [])[:3]])}

**예측 요구사항:**
1. {forecast_period} 후 예상 주가를 **반드시 숫자로만** 출력 (예: 160000)
2. 상승/하락/보합 중 하나 선택
3. 예측 근거 (기술적 지표 + 펀더멘털 + 뉴스 + 시장 상황)
4. 신뢰도 (상/중/하)
5. 주요 리스크 요인

**출력 형식 (정확히 따르세요):**
```
예상주가: [숫자만]
방향: [상승/하락/보합]

📊 예측 근거:
- [기술적 분석 근거]
- [펀더멘털 분석 근거]
- [거시경제 환경 영향]
- [뉴스 영향]

신뢰도: [상/중/하]
⚠️ 리스크: [주요 위험 요인]
```

**중요: 예상주가는 반드시 숫자만 출력하세요 (단위 없이)**
"""
                                )
                                
                                forecast_response = str(forecast_agent(f"{company_name} {forecast_period} 주가 예측"))
                                
                                # 예측 주가 추출
                                price_match = re.search(r'예상주가:\s*([0-9,.]+)', forecast_response)
                                predicted_price = None
                                if price_match:
                                    predicted_price = float(price_match.group(1).replace(',', ''))
                                
                                # 그래프 생성
                                if predicted_price:
                                    fig_forecast = go.Figure()
                                    
                                    # 과거 데이터 (최근 30일)
                                    recent_df = df.tail(30)
                                    fig_forecast.add_trace(go.Scatter(
                                        x=recent_df.index,
                                        y=recent_df['Close'],
                                        name='실제 주가',
                                        line=dict(color='#4ECDC4', width=2),
                                        mode='lines'
                                    ))
                                    
                                    # 예측 포인트
                                    last_date = df.index[-1]
                                    period_days = {"7일": 7, "1개월": 30, "3개월": 90, "6개월": 180}
                                    future_date = last_date + pd.Timedelta(days=period_days[forecast_period])
                                    
                                    # 현재가 → 예측가 연결선
                                    fig_forecast.add_trace(go.Scatter(
                                        x=[last_date, future_date],
                                        y=[current_price, predicted_price],
                                        name='예측',
                                        line=dict(color='#FF6B6B', width=2, dash='dash'),
                                        mode='lines+markers',
                                        marker=dict(size=10)
                                    ))
                                    
                                    # 신뢰 구간 (±10%)
                                    upper_bound = predicted_price * 1.1
                                    lower_bound = predicted_price * 0.9
                                    
                                    fig_forecast.add_trace(go.Scatter(
                                        x=[future_date, future_date],
                                        y=[lower_bound, upper_bound],
                                        mode='lines',
                                        line=dict(color='rgba(255,107,107,0.3)', width=0),
                                        showlegend=False,
                                        hoverinfo='skip'
                                    ))
                                    
                                    fig_forecast.update_layout(
                                        title=f"{company_name} AI 주가 예측 ({forecast_period})",
                                        yaxis_title="가격",
                                        xaxis_title="날짜",
                                        template="plotly_white",
                                        height=400,
                                        hovermode='x unified'
                                    )
                                    
                                    st.plotly_chart(fig_forecast, use_container_width=True)
                                    
                                    # 예측 요약 카드
                                    price_change = predicted_price - current_price
                                    # ZeroDivision 방지
                                    price_change_pct = (price_change / current_price) * 100 if current_price > 0 else 0

                                    # 통화 단위 결정
                                    curr_format = f"{current_price:,.0f}원" if ticker.endswith(".KS") else f"${current_price:,.2f}"
                                    pred_format = f"{predicted_price:,.0f}원" if ticker.endswith(".KS") else f"${predicted_price:,.2f}"

                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        st.metric("현재가", curr_format)
                                    with col2:
                                        st.metric(
                                            f"{forecast_period} 후 예측",
                                            pred_format,
                                            f"{price_change_pct:+.2f}%"
                                        )
                                    with col3:
                                        if price_change_pct > 0:
                                            st.success("📈 상승 예상")
                                        elif price_change_pct < 0:
                                            st.error("📉 하락 예상")
                                        else:
                                            st.info("➡️ 보합 예상")
                                
                                # AI 예측 결과 표시
                                st.markdown("---")
                                st.markdown("### 🤖 AI 종합 분석")
                                st.markdown(forecast_response)
                                
                                st.divider()
                                st.caption("💡 이 예측은 현재 기술적 지표, 최근 뉴스, 시장 상황을 종합한 AI 분석입니다.")
                                
                            except Exception as e:
                                st.error(f"예측 중 오류 발생: {str(e)}")
                    else:
                        st.info("👆 버튼을 클릭하여 AI 기반 주가 예측을 생성하세요.")
                
                with tab3:
                    # 기술적 분석
                    analysis = analyze_stock_trend(company_name, period)
                    
                    if "error" not in analysis:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.subheader("📊 이동평균선")
                            ma_data = pd.DataFrame({
                                '지표': ['MA5', 'MA20', 'MA60'],
                                '값': [analysis.get('ma5'), analysis.get('ma20'), analysis.get('ma60')]
                            })
                            st.dataframe(ma_data, hide_index=True, use_container_width=True)
                            
                            st.subheader("📈 MACD")
                            st.write(f"MACD: {analysis.get('macd', 'N/A')}")
                            st.write(f"Signal: {analysis.get('macd_signal', 'N/A')}")
                            st.write(f"Histogram: {analysis.get('macd_histogram', 'N/A')}")
                        
                        with col2:
                            st.subheader("🎯 RSI")
                            rsi = analysis.get('rsi')
                            if rsi:
                                st.metric("RSI (14일)", f"{rsi:.2f}")
                                if rsi < 30:
                                    st.success("과매도 구간 - 반등 가능성")
                                elif rsi > 70:
                                    st.error("과매수 구간 - 조정 가능성")
                                else:
                                    st.info("중립 구간")
                            
                            st.subheader("📊 볼린저밴드")
                            bb_pos = analysis.get('bb_position')
                            if bb_pos:
                                # 0-100 범위로 제한
                                bb_pos_clamped = max(0, min(100, bb_pos))
                                st.metric("현재 위치", f"{bb_pos:.1f}%")
                                st.progress(bb_pos_clamped / 100)
                            
                            if analysis.get('cross_signal'):
                                st.subheader("⚡ 크로스 신호")
                                signal = analysis['cross_signal']
                                if signal == "골든크로스":
                                    st.success(f"🟢 {signal} - 매수 신호")
                                else:
                                    st.error(f"🔴 {signal} - 매도 신호")
                    else:
                        st.error(analysis['error'])

                with tab4:
                    # 펀더멘털 분석 (기본적 분석)
                    st.subheader("💰 펀더멘털 분석")

                    # 데이터 조회
                    fundamental = get_fundamental_analysis(company_name)
                    holders = get_institutional_holders(company_name)

                    if "error" not in fundamental:
                        # 밸류에이션
                        st.markdown("#### 📊 밸류에이션")
                        val = fundamental['valuation']
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            pe = val.get('pe_ratio')
                            pe_status = "저평가" if pe and pe < 15 else ("고평가" if pe and pe > 25 else "적정")
                            st.metric("P/E (주가수익비율)", f"{pe:.1f}" if pe else "N/A", pe_status if pe else None)
                        with col2:
                            pb = val.get('pb_ratio')
                            pb_status = "저평가" if pb and pb < 1 else ("고평가" if pb and pb > 3 else "적정")
                            st.metric("P/B (주가순자산비율)", f"{pb:.2f}" if pb else "N/A", pb_status if pb else None)
                        with col3:
                            peg = val.get('peg_ratio')
                            peg_status = "저평가" if peg and peg < 1 else ("고평가" if peg and peg > 2 else "적정")
                            st.metric("PEG", f"{peg:.2f}" if peg else "N/A", peg_status if peg else None)
                        with col4:
                            ps = val.get('ps_ratio')
                            st.metric("PSR (주가매출비율)", f"{ps:.2f}" if ps else "N/A")

                        st.divider()

                        # 수익성
                        st.markdown("#### 📈 수익성")
                        prof = fundamental['profitability']
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            roe = prof.get('roe')
                            roe_status = "우수" if roe and roe > 15 else ("양호" if roe and roe > 10 else "개선필요")
                            st.metric("ROE (자기자본이익률)", f"{roe:.1f}%" if roe else "N/A", roe_status if roe else None)
                        with col2:
                            roa = prof.get('roa')
                            st.metric("ROA (총자산이익률)", f"{roa:.1f}%" if roa else "N/A")
                        with col3:
                            op_margin = prof.get('operating_margin')
                            st.metric("영업이익률", f"{op_margin:.1f}%" if op_margin else "N/A")
                        with col4:
                            net_margin = prof.get('profit_margin')
                            st.metric("순이익률", f"{net_margin:.1f}%" if net_margin else "N/A")

                        st.divider()

                        # 재무건전성
                        st.markdown("#### 🏦 재무건전성")
                        health = fundamental['financial_health']
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            debt = health.get('debt_to_equity')
                            debt_status = "안정" if debt and debt < 100 else ("주의" if debt and debt < 200 else "위험")
                            st.metric("부채비율", f"{debt:.1f}%" if debt else "N/A", debt_status if debt else None)
                        with col2:
                            current = health.get('current_ratio')
                            current_status = "양호" if current and current > 1.5 else ("보통" if current and current > 1 else "주의")
                            st.metric("유동비율", f"{current:.2f}" if current else "N/A", current_status if current else None)
                        with col3:
                            quick = health.get('quick_ratio')
                            st.metric("당좌비율", f"{quick:.2f}" if quick else "N/A")

                        st.divider()

                        # 성장성
                        st.markdown("#### 🚀 성장성")
                        growth = fundamental['growth']
                        col1, col2 = st.columns(2)
                        with col1:
                            rev_growth = growth.get('revenue_growth')
                            growth_status = "고성장" if rev_growth and rev_growth > 20 else ("성장" if rev_growth and rev_growth > 0 else "역성장")
                            st.metric("매출 성장률", f"{rev_growth:.1f}%" if rev_growth else "N/A", growth_status if rev_growth else None)
                        with col2:
                            earn_growth = growth.get('earnings_growth')
                            st.metric("이익 성장률", f"{earn_growth:.1f}%" if earn_growth else "N/A")

                        st.divider()

                        # 기관/외국인 보유 현황
                        st.markdown("#### 🏛️ 기관/외국인 보유 현황")
                        if "error" not in holders:
                            col1, col2 = st.columns(2)
                            with col1:
                                inst = holders.get('institutional_percent')
                                st.metric("기관 보유비율", f"{inst:.1f}%" if inst else "N/A")
                            with col2:
                                insider = holders.get('insider_percent')
                                st.metric("내부자 보유비율", f"{insider:.1f}%" if insider else "N/A")

                            # 주요 기관투자자 목록
                            if holders.get('top_institutions'):
                                st.markdown("**주요 기관투자자**")
                                inst_data = []
                                for inst in holders['top_institutions'][:5]:
                                    inst_data.append({
                                        "기관명": inst['holder'],
                                        "보유비율": f"{inst['percent']:.2f}%" if inst['percent'] else "N/A"
                                    })
                                if inst_data:
                                    st.dataframe(pd.DataFrame(inst_data), hide_index=True, use_container_width=True)
                        else:
                            st.info("기관 보유 데이터를 조회할 수 없습니다.")
                    else:
                        st.warning("펀더멘털 데이터를 조회할 수 없습니다.")

                with tab5:
                    # 거시경제 지표
                    st.subheader("🌍 거시경제 지표")

                    with st.spinner("거시경제 데이터 조회 중..."):
                        macro = get_macro_indicators()

                    # 시장 심리 배너
                    sentiment = macro.get("market_sentiment", "중립")
                    if "공포" in sentiment:
                        st.error(f"📉 시장 심리: {sentiment}")
                    elif "낙관" in sentiment:
                        st.success(f"📈 시장 심리: {sentiment}")
                    else:
                        st.info(f"➡️ 시장 심리: {sentiment}")

                    st.divider()

                    # 주요 지수
                    st.markdown("#### 📊 주요 지수")
                    indices = macro.get("indices", {})
                    if indices:
                        cols = st.columns(4)
                        for i, (name, data) in enumerate(indices.items()):
                            with cols[i % 4]:
                                change = data.get("change_percent", 0)
                                st.metric(
                                    name,
                                    f"{data.get('price', 0):,.2f}",
                                    f"{change:+.2f}%"
                                )

                    st.divider()

                    col1, col2 = st.columns(2)

                    with col1:
                        # VIX (공포지수)
                        st.markdown("#### 😰 VIX (공포지수)")
                        vix_data = macro.get("volatility", {}).get("VIX", {})
                        if vix_data:
                            vix_value = vix_data.get("value", 0)
                            interpretation = vix_data.get("interpretation", "N/A")
                            st.metric("VIX", f"{vix_value:.2f}", interpretation)

                            # VIX 게이지
                            vix_normalized = min(vix_value / 40 * 100, 100)
                            st.progress(vix_normalized / 100)
                            st.caption("0-15: 안정 | 15-20: 중립 | 20-30: 공포 | 30+: 극심한 공포")

                        # 채권/금리
                        st.markdown("#### 🏦 미국 국채 금리")
                        bonds = macro.get("bonds", {})
                        for name, data in bonds.items():
                            st.metric(name, f"{data.get('yield', 0):.3f}%")

                    with col2:
                        # 환율
                        st.markdown("#### 💱 환율")
                        currencies = macro.get("currencies", {})
                        for name, data in currencies.items():
                            change = data.get("change_percent", 0)
                            st.metric(
                                name,
                                f"{data.get('rate', 0):,.2f}",
                                f"{change:+.2f}%"
                            )

                        # 원자재
                        st.markdown("#### 🛢️ 원자재")
                        commodities = macro.get("commodities", {})
                        for name, data in commodities.items():
                            change = data.get("change_percent", 0)
                            st.metric(
                                name,
                                f"${data.get('price', 0):,.2f}",
                                f"{change:+.2f}%"
                            )

                with tab6:
                    # 뉴스 분석
                    news = analyze_company_news(company_name)

                    if "error" not in news and news.get('news'):
                        st.subheader(f"📰 최근 뉴스 ({news['news_count']}건)")
                        for item in news['news']:
                            with st.container():
                                st.markdown(f"**{item['title']}**")
                                st.caption(f"📅 {item['published']}")
                                st.link_button("기사 보기", item['link'], use_container_width=True)
                                st.divider()
                    else:
                        st.warning("뉴스를 찾을 수 없습니다.")
            
            # AI 분석 추가
            st.markdown("---")
            st.subheader("🤖 AI 종합 분석")
            
            # 매번 새로운 Agent 인스턴스 생성
            agent = Agent(
                model=st.session_state.bedrock_model,
                tools=[get_stock_price, analyze_stock_trend, get_fundamental_analysis, get_institutional_holders, get_macro_indicators, analyze_company_news],
                system_prompt=st.session_state.system_prompt
            )
            
            response = agent(user_input)
            st.markdown(str(response))
            
            # 히스토리 저장
            st.session_state.history.append({
                "query": user_input,
                "response": str(response)
            })
            
        except Exception as e:
            st.error(f"오류가 발생했습니다: {str(e)}")

# 히스토리 표시
if st.session_state.history:
    st.markdown("---")
    with st.expander("📜 조회 히스토리", expanded=False):
        for i, item in enumerate(reversed(st.session_state.history[-5:]), 1):
            st.markdown(f"**{i}. {item['query']}**")
            st.text(item['response'][:200] + "..." if len(item['response']) > 200 else item['response'])
            st.markdown("---")

# 푸터
st.markdown("---")
st.caption("⚠️ 이 분석은 참고용이며, 투자 판단은 본인의 책임입니다.")
