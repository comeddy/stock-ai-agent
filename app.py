#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주식 분석 Agent AI 서비스 - Streamlit 웹 애플리케이션

이 애플리케이션은 다음 기능을 제공합니다:
- 실시간 주가 조회 및 차트 시각화
- AI 기반 주가 예측
- 기술적 분석 (이동평균, RSI, MACD, 볼린저밴드)
- 기본적 분석 (밸류에이션, 수익성, 재무건전성)
- 동종업계 비교 분석
- 거시경제 지표 모니터링
- 뉴스 감성 분석 (NLP 기반)

사용 기술:
- Streamlit: 웹 UI 프레임워크
- yfinance: 주가 데이터 API
- Plotly: 인터랙티브 차트
- AWS Bedrock: Claude AI 모델
- Strands Agent SDK: AI 에이전트 프레임워크
"""

# =============================================================================
# 라이브러리 임포트
# =============================================================================
import streamlit as st          # 웹 UI 프레임워크
import yfinance as yf           # 야후 파이낸스 주가 데이터
import pandas as pd             # 데이터 처리
import plotly.graph_objects as go  # 인터랙티브 차트
from datetime import datetime, timedelta  # 날짜/시간 처리
import re                       # 정규표현식 (예측 결과 파싱용)

# 커스텀 모듈 임포트 - AI 에이전트 도구들
from stock_agent import (
    get_stock_price,            # 현재가 조회 도구
    analyze_stock_trend,        # 기술적 분석 도구
    analyze_company_news,       # 뉴스 감성 분석 도구
    get_ticker,                 # 회사명 → 티커 변환
    get_fundamental_analysis,   # 기본적 분석 도구
    get_institutional_holders,  # 기관 보유 현황 도구
    get_peer_comparison,        # 동종업계 비교 도구
    get_macro_indicators        # 거시경제 지표 도구
)

# AWS Bedrock 연동
from strands import Agent                    # AI 에이전트 클래스
from strands.models import BedrockModel      # Bedrock 모델 래퍼

# =============================================================================
# Streamlit 페이지 설정
# =============================================================================
st.set_page_config(
    page_title="주식 분석 Agent AI 서비스",  # 브라우저 탭 제목
    page_icon="💹",                    # 파비콘
    layout="wide"                      # 넓은 레이아웃 사용
)

# =============================================================================
# 세션 상태 초기화
# Streamlit은 매 인터랙션마다 스크립트를 재실행하므로
# 상태를 유지하려면 session_state를 사용해야 함
# =============================================================================

# Bedrock 모델 초기화 (한 번만 생성)
if 'bedrock_model' not in st.session_state:
    st.session_state.bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        region_name="us-east-1"
    )

# AI 에이전트 시스템 프롬프트 초기화
# 이 프롬프트는 AI가 어떻게 응답해야 하는지 정의함
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

**종합 분석 요청 시 반드시 8가지 도구 모두 사용:**
1. get_stock_price - 현재가 확인
2. analyze_stock_trend - 기술적 분석
3. get_fundamental_analysis - 기본적 분석 (밸류에이션, 수익성, 재무건전성, 성장성)
4. get_institutional_holders - 수급 분석 (기관/외국인 보유현황)
5. get_peer_comparison - 동종업계 비교 분석 (경쟁사 대비 상대 평가)
6. get_macro_indicators - 거시경제 지표 (지수, VIX, 금리, 환율, 원자재)
7. analyze_company_news - 뉴스 NLP 감성 분석 (점수화된 감성 분석)

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

🏆 동종업계 비교:

📊 업종: {섹터} - {업종}

📈 경쟁사 대비 상대 평가:
- P/E: {업종 평균 대비 상태} (회사: {값}, 업종평균: {값})
- P/B: {업종 평균 대비 상태} (회사: {값}, 업종평균: {값})
- ROE: {업종 평균 대비 상태} (회사: {값}%, 업종평균: {값}%)
   → 해석: 밸류에이션 저평가 + 수익성 상위 = 매력적
   → 현재 판단: [업종 대비 우수/적정/열위]

📰 뉴스 감성 분석:

🎯 종합 감성 점수: {-100~+100 점수} ({매우긍정/긍정/중립/부정/매우부정})
   → 의미: 뉴스 헤드라인의 NLP 기반 감성 분석 결과
   → 해석: +20 이상=매우 긍정, +5~+20=긍정, -5~+5=중립, -20~-5=부정, -20 이하=매우 부정
   → 긍정 뉴스: {개수}건, 부정 뉴스: {개수}건
   → 주요 긍정 키워드: {키워드들}
   → 주요 부정 키워드: {키워드들}

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

# 조회 히스토리 저장 (최근 검색 기록)
if 'history' not in st.session_state:
    st.session_state.history = []

# =============================================================================
# 페이지 헤더
# =============================================================================
st.title("💹 실시간 주가 조회 및 AI 기반 투자 분석 서비스")
st.markdown("실시간 주가 조회 및 AI 기반 투자 분석")

# =============================================================================
# 사이드바 - 사용 가이드 및 관심 종목 관리
# =============================================================================
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

    # -------------------------------------------------------------------------
    # 관심 종목 관리 섹션
    # 사용자가 자주 조회하는 종목을 저장하고 빠르게 접근 가능
    # -------------------------------------------------------------------------
    st.header("⭐ 관심 종목")

    # 세션 상태에 관심 종목 리스트 초기화 (기본 3개 종목)
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = ["삼성전자", "SK하이닉스", "네이버"]

    # 관심 종목 추가 입력 폼
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

# =============================================================================
# 메인 입력 영역
# =============================================================================
col1, col2 = st.columns([3, 1])  # 3:1 비율로 컬럼 분할

with col1:
    # 회사명 입력 필드
    user_input = st.text_input(
        "회사명을 입력하세요",
        placeholder="예: 삼성전자, Amazon, SK 하이닉스",
        key="company_input"
    )

with col2:
    # 분석 시작 버튼
    analyze_button = st.button("🔍 분석하기", type="primary", use_container_width=True)

# -------------------------------------------------------------------------
# 분석 기간 선택
# yfinance API에서 지원하는 기간: 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
# -------------------------------------------------------------------------
if 'selected_period' not in st.session_state:
    st.session_state.selected_period = "3개월"  # 기본값: 3개월

# 수평 라디오 버튼으로 기간 선택
period_option = st.radio(
    "기간 선택",
    ["3개월", "6개월", "1년", "5년"],
    horizontal=True,
    index=["3개월", "6개월", "1년", "5년"].index(st.session_state.selected_period),
    key="period_radio"
)

# 기간 변경 시 자동으로 페이지 새로고침하여 재분석
if period_option != st.session_state.selected_period:
    st.session_state.selected_period = period_option
    if user_input:
        st.rerun()

# 한글 기간명 → yfinance 기간 코드 매핑
period_map = {
    "3개월": "3mo",
    "6개월": "6mo",
    "1년": "1y",
    "5년": "5y"
}
period = period_map[period_option]

# =============================================================================
# 분석 실행 메인 로직
# 버튼 클릭 또는 자동 분석 플래그가 설정된 경우 실행
# =============================================================================
if (analyze_button or st.session_state.get('auto_analyze')) and user_input:
    with st.spinner("분석 중..."):  # 로딩 스피너 표시
        try:
            # 자동 분석 플래그 설정 (기간 변경 시 자동 재분석용)
            st.session_state.auto_analyze = True

            # ---------------------------------------------------------------------
            # 회사명 전처리: "삼성전자 주가분석" → "삼성전자"
            # 불필요한 키워드를 제거하여 순수 회사명만 추출
            # ---------------------------------------------------------------------
            keywords = ['주가', '분석', '매수', '매도', '타이밍', '예측', '전망', '추천']
            company_name = user_input
            for keyword in keywords:
                company_name = company_name.replace(keyword, '').strip()
            # 빈 문자열이면 원본의 첫 단어 사용
            if not company_name:
                company_name = user_input.split()[0]

            # 회사명을 티커 심볼로 변환 (예: "삼성전자" → "005930.KS")
            ticker = get_ticker(company_name)

            # ---------------------------------------------------------------------
            # yfinance를 통한 주가 데이터 조회
            # ---------------------------------------------------------------------
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)  # 선택된 기간의 OHLCV 데이터
            
            if not df.empty:
                # -----------------------------------------------------------------
                # 7개 탭으로 분석 결과 표시
                # 1. 차트: 캔들스틱 + 이동평균선
                # 2. 예측: AI 기반 미래 주가 예측
                # 3. 기술적 분석: RSI, MACD, 볼린저밴드
                # 4. 펀더멘털: 밸류에이션, 수익성, 재무건전성
                # 5. 동종업계 비교: 경쟁사 대비 평가
                # 6. 거시경제: 지수, 금리, 환율, VIX
                # 7. 뉴스: 감성 분석 포함
                # -----------------------------------------------------------------
                tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
                    "📈 차트", "🔮 예측", "📊 기술적 분석",
                    "💰 펀더멘털", "🏆 동종업계 비교", "🌍 거시경제", "📰 뉴스"
                ])

                # =============================================================
                # 탭 1: 주가 차트 (캔들스틱 + 이동평균선)
                # =============================================================
                with tab1:
                    # Plotly를 사용한 인터랙티브 차트 생성
                    fig = go.Figure()
                    
                    # 캔들스틱 차트 추가
                    # - 빨간색: 상승 (시가 < 종가)
                    # - 청록색: 하락 (시가 > 종가)
                    fig.add_trace(go.Candlestick(
                        x=df.index,
                        open=df['Open'],      # 시가
                        high=df['High'],      # 고가
                        low=df['Low'],        # 저가
                        close=df['Close'],    # 종가
                        name='주가',
                        increasing_line_color='#FF6B6B',   # 상승: 빨간색
                        decreasing_line_color='#4ECDC4'    # 하락: 청록색
                    ))

                    # 이동평균선 계산 및 추가
                    # MA5: 5일 단기 이동평균 (단기 추세)
                    # MA20: 20일 중기 이동평균 (중기 추세)
                    df['MA5'] = df['Close'].rolling(window=5).mean()
                    df['MA20'] = df['Close'].rolling(window=20).mean()

                    # MA5 선 추가 (노란색)
                    fig.add_trace(go.Scatter(
                        x=df.index, y=df['MA5'],
                        name='MA5', line=dict(color='#FFE66D', width=1)
                    ))
                    # MA20 선 추가 (하늘색)
                    fig.add_trace(go.Scatter(
                        x=df.index, y=df['MA20'],
                        name='MA20', line=dict(color='#A8DADC', width=1)
                    ))

                    # 차트 레이아웃 설정
                    fig.update_layout(
                        title=f"{company_name} 주가 추이 ({period_option})",
                        yaxis_title="가격",
                        xaxis_title="날짜",
                        template="plotly_white",       # 깔끔한 화이트 테마
                        height=500,                   # 차트 높이
                        hovermode='x unified',        # 호버 시 같은 x축 데이터 모두 표시
                        xaxis_rangeslider_visible=False  # 하단 미니 차트 숨김
                    )

                    # 차트를 Streamlit에 표시
                    st.plotly_chart(fig, use_container_width=True)

                    # ---------------------------------------------------------
                    # 주요 지표 카드 (현재가, 최고가, 최저가, 거래량)
                    # ---------------------------------------------------------
                    current_price = df['Close'].iloc[-1]  # 현재가 (최근 종가)
                    prev_price = df['Close'].iloc[-2] if len(df) > 1 else current_price  # 전일 종가
                    change = current_price - prev_price   # 변동폭
                    change_pct = (change / prev_price) * 100 if prev_price > 0 else 0  # 변동률 (%)

                    # 통화 단위 결정 (한국 주식: 원, 미국 주식: $)
                    # 티커가 .KS로 끝나면 한국 주식
                    currency = "원" if ticker.endswith(".KS") else "$"
                    price_format = f"{current_price:,.0f}{currency}" if ticker.endswith(".KS") else f"${current_price:,.2f}"
                    high_format = f"{df['High'].max():,.0f}{currency}" if ticker.endswith(".KS") else f"${df['High'].max():,.2f}"
                    low_format = f"{df['Low'].min():,.0f}{currency}" if ticker.endswith(".KS") else f"${df['Low'].min():,.2f}"

                    # 4개 컬럼으로 지표 카드 표시
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("현재가", price_format, f"{change_pct:+.2f}%")  # 변동률 표시
                    with col2:
                        st.metric("최고가", high_format)  # 기간 내 최고가
                    with col3:
                        st.metric("최저가", low_format)   # 기간 내 최저가
                    with col4:
                        st.metric("거래량", f"{df['Volume'].iloc[-1]:,.0f}")  # 최근 거래량
                
                # =============================================================
                # 탭 2: AI 기반 주가 예측
                # Claude AI를 활용하여 기술적/기본적 분석 데이터를 종합한 예측
                # =============================================================
                with tab2:
                    st.subheader("🔮 AI 주가 예측")

                    # 예측 기간 선택 드롭다운
                    forecast_period = st.selectbox(
                        "예측 기간",
                        ["1일", "7일", "1개월", "3개월", "6개월"],
                        key="forecast_period"
                    )

                    # AI 예측 생성 버튼
                    if st.button("🤖 AI 예측 생성", use_container_width=True):
                        with st.spinner("AI가 종합 분석 중..."):
                            try:
                                # ---------------------------------------------------------
                                # AI 예측을 위한 데이터 수집
                                # 모든 도구를 호출하여 종합 데이터를 수집
                                # ---------------------------------------------------------

                                # 기술적 분석 데이터 (RSI, MACD, 볼린저밴드 등)
                                analysis = analyze_stock_trend(company_name, period)

                                # 뉴스 감성 분석 데이터
                                news = analyze_company_news(company_name)

                                # 현재 주가 정보
                                price_info = get_stock_price(company_name)

                                # 기본적 분석 데이터 (밸류에이션, 수익성 등)
                                fundamental = get_fundamental_analysis(company_name)

                                # 기관/내부자 보유 현황
                                holders = get_institutional_holders(company_name)

                                # 동종업계 비교 데이터
                                peer_data = get_peer_comparison(company_name)

                                # 거시경제 지표 (지수, VIX, 금리, 환율)
                                macro = get_macro_indicators()

                                current_price = float(price_info.get('current_price', 0))

                                # 펀더멘털 데이터 안전하게 추출 (에러 시 빈 딕셔너리)
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

**동종업계 비교:**
- 섹터/업종: {peer_data.get('sector', 'N/A')} / {peer_data.get('industry', 'N/A')}
- 업종 대비 P/E: {peer_data.get('relative_position', {}).get('pe_ratio', 'N/A')}
- 업종 대비 ROE: {peer_data.get('relative_position', {}).get('roe', 'N/A')}
- 업종 대비 성장성: {peer_data.get('relative_position', {}).get('revenue_growth', 'N/A')}

**뉴스 감성 분석:**
- 종합 감성 점수: {news.get('overall_sentiment', {}).get('score', 0)} ({news.get('overall_sentiment', {}).get('label', '중립')})
- 긍정 뉴스: {news.get('overall_sentiment', {}).get('positive_count', 0)}건
- 부정 뉴스: {news.get('overall_sentiment', {}).get('negative_count', 0)}건
- 최근 뉴스 헤드라인:
{chr(10).join([f"  - [{item.get('sentiment_label', '중립')}] {item['title']}" for item in news.get('news', [])[:3]])}

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
- [동종업계 비교 결과]
- [거시경제 환경 영향]
- [뉴스 감성 분석 결과]

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
                                    # 예측 기간을 일수로 변환
                                    period_days = {"1일": 1, "7일": 7, "1개월": 30, "3개월": 90, "6개월": 180}
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
                
                # =============================================================
                # 탭 3: 기술적 분석
                # 이동평균, RSI, MACD, 볼린저밴드 등 기술적 지표 표시
                # =============================================================
                with tab3:
                    # 기술적 분석 도구 호출
                    analysis = analyze_stock_trend(company_name, period)

                    if "error" not in analysis:
                        col1, col2 = st.columns(2)

                        # 왼쪽 컬럼: 이동평균선, MACD
                        with col1:
                            # 이동평균선 테이블
                            st.subheader("📊 이동평균선")
                            ma_data = pd.DataFrame({
                                '지표': ['MA5', 'MA20', 'MA60'],  # 5일, 20일, 60일
                                '값': [analysis.get('ma5'), analysis.get('ma20'), analysis.get('ma60')]
                            })
                            st.dataframe(ma_data, hide_index=True, use_container_width=True)

                            # MACD (Moving Average Convergence Divergence)
                            # 추세 전환 신호를 포착하는 지표
                            st.subheader("📈 MACD")
                            st.write(f"MACD: {analysis.get('macd', 'N/A')}")        # MACD 선
                            st.write(f"Signal: {analysis.get('macd_signal', 'N/A')}")  # 시그널 선
                            st.write(f"Histogram: {analysis.get('macd_histogram', 'N/A')}")  # 히스토그램

                        # 오른쪽 컬럼: RSI, 볼린저밴드, 크로스 신호
                        with col2:
                            # RSI (Relative Strength Index) - 상대강도지수
                            # 0-100 범위, 30 이하 과매도, 70 이상 과매수
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

                            # 볼린저밴드 - 주가 변동 범위 표시
                            # 0%: 하단 밴드, 100%: 상단 밴드
                            st.subheader("📊 볼린저밴드")
                            bb_pos = analysis.get('bb_position')
                            if bb_pos:
                                bb_pos_clamped = max(0, min(100, bb_pos))  # 0-100 범위로 제한
                                st.metric("현재 위치", f"{bb_pos:.1f}%")
                                st.progress(bb_pos_clamped / 100)  # 프로그레스 바로 시각화

                            # 골든크로스/데드크로스 신호
                            # 골든크로스: 단기선이 장기선을 상향 돌파 (매수 신호)
                            # 데드크로스: 단기선이 장기선을 하향 돌파 (매도 신호)
                            if analysis.get('cross_signal'):
                                st.subheader("⚡ 크로스 신호")
                                signal = analysis['cross_signal']
                                if signal == "골든크로스":
                                    st.success(f"🟢 {signal} - 매수 신호")
                                else:
                                    st.error(f"🔴 {signal} - 매도 신호")
                    else:
                        st.error(analysis['error'])

                # =============================================================
                # 탭 4: 펀더멘털 분석 (기본적 분석)
                # 밸류에이션, 수익성, 재무건전성, 성장성, 기관 보유 현황
                # =============================================================
                with tab4:
                    st.subheader("💰 펀더멘털 분석")

                    # 기본적 분석 도구 호출
                    fundamental = get_fundamental_analysis(company_name)
                    # 기관/내부자 보유 현황 조회
                    holders = get_institutional_holders(company_name)

                    if "error" not in fundamental:
                        # ---------------------------------------------------------
                        # 밸류에이션 지표
                        # P/E: 주가수익비율 (낮을수록 저평가)
                        # P/B: 주가순자산비율 (1 이하면 저평가)
                        # PEG: 주가수익성장비율 (1 이하면 저평가)
                        # PSR: 주가매출비율
                        # ---------------------------------------------------------
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

                        # ---------------------------------------------------------
                        # 수익성 지표
                        # ROE: 자기자본이익률 (15% 이상 우수)
                        # ROA: 총자산이익률
                        # 영업이익률, 순이익률
                        # ---------------------------------------------------------
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

                # =============================================================
                # 탭 5: 동종업계 비교 분석
                # 같은 섹터/업종의 경쟁사와 주요 지표 비교
                # =============================================================
                with tab5:
                    st.subheader("🏆 동종업계 비교 분석")

                    with st.spinner("경쟁사 데이터 조회 중..."):
                        # 동종업계 비교 도구 호출
                        peer_data = get_peer_comparison(company_name)

                    if "error" not in peer_data:
                        # 섹터/업종 정보
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("섹터", peer_data.get("sector", "N/A"))
                        with col2:
                            st.metric("업종", peer_data.get("industry", "N/A"))

                        st.divider()

                        # 상대적 위치 요약
                        st.markdown("#### 📊 업종 대비 상대 평가")
                        rel_pos = peer_data.get("relative_position", {})
                        cols = st.columns(3)

                        metrics_labels = {
                            "pe_ratio": ("P/E", "밸류에이션"),
                            "pb_ratio": ("P/B", "밸류에이션"),
                            "roe": ("ROE", "수익성"),
                            "profit_margin": ("순이익률", "수익성"),
                            "revenue_growth": ("매출성장률", "성장성")
                        }

                        for i, (key, (label, category)) in enumerate(metrics_labels.items()):
                            with cols[i % 3]:
                                position = rel_pos.get(key, "N/A")
                                if "저평가" in str(position) or "상위" in str(position) or "이상" in str(position):
                                    st.success(f"{label}: {position}")
                                elif "고평가" in str(position) or "하위" in str(position) or "이하" in str(position):
                                    st.error(f"{label}: {position}")
                                else:
                                    st.info(f"{label}: {position}")

                        st.divider()

                        # 경쟁사 비교 테이블
                        st.markdown("#### 📈 경쟁사 비교")
                        company_metrics = peer_data.get("company_metrics", {})
                        peers = peer_data.get("peers", [])
                        industry_avg = peer_data.get("industry_average", {})

                        if peers:
                            # 비교 데이터프레임 생성
                            comparison_data = []

                            # 현재 회사 데이터
                            comparison_data.append({
                                "회사": f"⭐ {company_name}",
                                "P/E": company_metrics.get("pe_ratio", "-"),
                                "P/B": company_metrics.get("pb_ratio", "-"),
                                "ROE (%)": company_metrics.get("roe", "-"),
                                "순이익률 (%)": company_metrics.get("profit_margin", "-"),
                                "매출성장률 (%)": company_metrics.get("revenue_growth", "-")
                            })

                            # 경쟁사 데이터
                            for peer in peers:
                                comparison_data.append({
                                    "회사": peer.get("name", peer.get("ticker", "N/A")),
                                    "P/E": peer.get("pe_ratio", "-"),
                                    "P/B": peer.get("pb_ratio", "-"),
                                    "ROE (%)": peer.get("roe", "-"),
                                    "순이익률 (%)": peer.get("profit_margin", "-"),
                                    "매출성장률 (%)": peer.get("revenue_growth", "-")
                                })

                            # 업종 평균 행 추가
                            comparison_data.append({
                                "회사": "📊 업종 평균",
                                "P/E": industry_avg.get("pe_ratio", "-"),
                                "P/B": industry_avg.get("pb_ratio", "-"),
                                "ROE (%)": industry_avg.get("roe", "-"),
                                "순이익률 (%)": industry_avg.get("profit_margin", "-"),
                                "매출성장률 (%)": industry_avg.get("revenue_growth", "-")
                            })

                            df_comparison = pd.DataFrame(comparison_data)
                            st.dataframe(df_comparison, hide_index=True, use_container_width=True)

                            st.caption(f"비교 대상: {peer_data.get('peer_count', 0)}개 경쟁사")
                        else:
                            st.info("비교 가능한 경쟁사 데이터가 없습니다.")
                    else:
                        st.warning("동종업계 비교 데이터를 조회할 수 없습니다.")

                # =============================================================
                # 탭 6: 거시경제 지표
                # 시장 전반의 상황을 파악하기 위한 매크로 데이터
                # - 주요 지수 (S&P 500, NASDAQ, KOSPI 등)
                # - VIX (공포지수)
                # - 채권 금리
                # - 환율
                # - 원자재 가격
                # =============================================================
                with tab6:
                    st.subheader("🌍 거시경제 지표")

                    with st.spinner("거시경제 데이터 조회 중..."):
                        # 거시경제 지표 도구 호출
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

                # =============================================================
                # 탭 7: 뉴스 감성 분석
                # NLP 기반 키워드 감성 분석으로 뉴스의 긍정/부정 판단
                # - 종합 감성 점수 (-100 ~ +100)
                # - 개별 기사별 감성 분석
                # - 긍정/부정 키워드 하이라이트
                # =============================================================
                with tab7:
                    # 뉴스 감성 분석 도구 호출
                    news = analyze_company_news(company_name)

                    if "error" not in news and news.get('news'):
                        # 종합 감성 점수 및 라벨
                        overall = news.get("overall_sentiment", {})
                        overall_score = overall.get("score", 0)  # -100 ~ +100
                        overall_label = overall.get("label", "중립")  # 매우긍정/긍정/중립/부정/매우부정

                        st.subheader(f"📰 최근 뉴스 ({news['news_count']}건)")

                        # 감성 점수 요약
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            if overall_score > 0:
                                st.metric("종합 감성", overall_label, f"+{overall_score}")
                            else:
                                st.metric("종합 감성", overall_label, f"{overall_score}")
                        with col2:
                            st.metric("긍정 뉴스", f"{overall.get('positive_count', 0)}건", delta_color="off")
                        with col3:
                            st.metric("부정 뉴스", f"{overall.get('negative_count', 0)}건", delta_color="off")
                        with col4:
                            st.metric("중립 뉴스", f"{overall.get('neutral_count', 0)}건", delta_color="off")

                        # 감성 게이지 (-100 ~ +100)
                        normalized_score = (overall_score + 100) / 200  # 0~1 범위로 변환
                        st.progress(normalized_score)
                        st.caption("← 부정적 (-100) ————— 중립 (0) ————— 긍정적 (+100) →")

                        st.divider()

                        # 개별 뉴스 (감성 점수 포함)
                        for item in news['news']:
                            with st.container():
                                # 감성 배지
                                sentiment_score = item.get("sentiment_score", 0)
                                sentiment_label = item.get("sentiment_label", "중립")

                                col1, col2 = st.columns([4, 1])
                                with col1:
                                    st.markdown(f"**{item['title']}**")
                                with col2:
                                    if sentiment_score > 0:
                                        st.success(f"😊 +{sentiment_score}")
                                    elif sentiment_score < 0:
                                        st.error(f"😟 {sentiment_score}")
                                    else:
                                        st.info(f"😐 {sentiment_score}")

                                # 키워드 표시
                                pos_kw = item.get("positive_keywords", [])
                                neg_kw = item.get("negative_keywords", [])
                                if pos_kw or neg_kw:
                                    kw_text = ""
                                    if pos_kw:
                                        kw_text += f"🟢 {', '.join(pos_kw[:3])} "
                                    if neg_kw:
                                        kw_text += f"🔴 {', '.join(neg_kw[:3])}"
                                    st.caption(kw_text)

                                st.caption(f"📅 {item['published']}")
                                st.link_button("기사 보기", item['link'], use_container_width=True)
                                st.divider()
                    else:
                        st.warning("뉴스를 찾을 수 없습니다.")

            # =============================================================
            # AI 종합 분석
            # 모든 도구를 활용하여 종합적인 투자 판단 제공
            # =============================================================
            st.markdown("---")
            st.subheader("🤖 AI 종합 분석")

            # ---------------------------------------------------------
            # 분석 진행 상황을 실시간으로 표시
            # 사용자가 기다리는 동안 지루하지 않도록 UI 개선
            # ---------------------------------------------------------
            import time
            import random

            # 투자 팁 목록 (대기 중 표시)
            investment_tips = [
                "💡 분산 투자는 리스크를 줄이는 가장 기본적인 방법입니다.",
                "💡 장기 투자는 단기 변동성을 극복하는 좋은 전략입니다.",
                "💡 투자 전 기업의 재무제표를 확인하는 습관을 들이세요.",
                "💡 감정적 매매는 손실의 주요 원인입니다.",
                "💡 RSI 30 이하는 과매도, 70 이상은 과매수 구간입니다.",
                "💡 골든크로스는 단기 이평선이 장기 이평선을 상향 돌파할 때 발생합니다.",
                "💡 PER이 낮다고 무조건 저평가는 아닙니다. 업종 평균과 비교하세요.",
                "💡 기관 투자자의 매수는 긍정적 신호로 해석될 수 있습니다.",
                "💡 VIX 지수가 30 이상이면 시장이 극도로 불안한 상태입니다.",
                "💡 환율 변동은 수출 기업의 실적에 큰 영향을 미칩니다.",
            ]

            # 분석 단계 정의
            analysis_steps = [
                ("💰 현재가 조회 중...", "주가 데이터 수집"),
                ("📊 기술적 분석 중...", "RSI, MACD, 볼린저밴드 계산"),
                ("💼 펀더멘털 분석 중...", "P/E, ROE, 재무비율 분석"),
                ("🏛️ 기관 보유 현황 확인 중...", "주요 투자자 데이터 수집"),
                ("🏆 동종업계 비교 중...", "경쟁사 지표 비교"),
                ("🌍 거시경제 지표 확인 중...", "금리, 환율, VIX 분석"),
                ("📰 뉴스 감성 분석 중...", "최신 뉴스 NLP 분석"),
                ("🤖 AI가 종합 판단 중...", "Claude AI 분석 진행"),
            ]

            # 진행 상태 컨테이너 생성
            progress_container = st.container()
            with progress_container:
                progress_bar = st.progress(0)
                status_text = st.empty()
                tip_text = st.empty()

                # 랜덤 팁 표시
                tip_text.info(random.choice(investment_tips))

            # AI 에이전트 인스턴스 생성
            # 7개 도구를 모두 활용하여 종합 분석 수행
            agent = Agent(
                model=st.session_state.bedrock_model,
                tools=[
                    get_stock_price,           # 현재가 조회
                    analyze_stock_trend,       # 기술적 분석
                    get_fundamental_analysis,  # 기본적 분석
                    get_institutional_holders, # 기관 보유 현황
                    get_peer_comparison,       # 동종업계 비교
                    get_macro_indicators,      # 거시경제 지표
                    analyze_company_news       # 뉴스 감성 분석
                ],
                system_prompt=st.session_state.system_prompt
            )

            # 진행 상황 시뮬레이션과 함께 AI 분석 실행
            # (실제 진행 상황과 동기화하기 어려우므로 예상 시간 기반 표시)
            import threading
            import queue

            result_queue = queue.Queue()

            def run_agent():
                try:
                    result = agent(user_input)
                    result_queue.put(("success", result))
                except Exception as e:
                    result_queue.put(("error", str(e)))

            # 백그라운드에서 AI 분석 실행
            agent_thread = threading.Thread(target=run_agent)
            agent_thread.start()

            # 진행 상황 애니메이션 표시
            step_idx = 0
            while agent_thread.is_alive():
                if step_idx < len(analysis_steps):
                    step_name, step_desc = analysis_steps[step_idx]
                    progress = (step_idx + 1) / len(analysis_steps)
                    progress_bar.progress(progress)
                    status_text.markdown(f"**{step_name}** _{step_desc}_")

                    # 3초마다 팁 변경
                    if step_idx % 2 == 0:
                        tip_text.info(random.choice(investment_tips))

                    step_idx += 1
                time.sleep(2.5)  # 각 단계 사이 대기

            # 완료 표시
            progress_bar.progress(1.0)
            status_text.markdown("**✅ 분석 완료!**")
            tip_text.empty()

            # 결과 가져오기
            status, result = result_queue.get()
            if status == "error":
                st.error(f"분석 중 오류 발생: {result}")
                response = ""
            else:
                response = result

            # 진행 상태 컨테이너 정리
            time.sleep(0.5)
            progress_container.empty()

            response_text = str(response)

            # ---------------------------------------------------------
            # 종합 판단 요약 카드 (상단에 핵심 결론 강조)
            # ---------------------------------------------------------
            # 종합 판단 추출 (매수/매도/관망)
            if "매수 고려" in response_text or "매수 추천" in response_text:
                verdict = "📈 매수 고려"
                verdict_color = "green"
                st.success(f"### {verdict}")
            elif "매도 고려" in response_text or "매도 추천" in response_text:
                verdict = "📉 매도 고려"
                verdict_color = "red"
                st.error(f"### {verdict}")
            else:
                verdict = "⏸️ 관망 추천"
                verdict_color = "blue"
                st.info(f"### {verdict}")

            # ---------------------------------------------------------
            # 분석 결과를 시각적으로 구분된 섹션으로 표시
            # ---------------------------------------------------------
            with st.container():
                # 상세 분석 내용을 확장 가능한 패널로 표시
                with st.expander("📋 상세 분석 보기", expanded=True):
                    st.markdown(response_text)

            # 조회 히스토리에 저장 (최근 검색 기록 유지)
            st.session_state.history.append({
                "query": user_input,
                "response": str(response)
            })
            
        except Exception as e:
            st.error(f"오류가 발생했습니다: {str(e)}")

# =============================================================================
# 조회 히스토리 표시
# 최근 5개 검색 기록을 접을 수 있는 패널로 표시
# =============================================================================
if st.session_state.history:
    st.markdown("---")
    with st.expander("📜 조회 히스토리", expanded=False):
        # 최근 5개만 역순으로 표시 (최신이 위로)
        for i, item in enumerate(reversed(st.session_state.history[-5:]), 1):
            st.markdown(f"**{i}. {item['query']}**")
            # 응답이 길면 200자까지만 미리보기
            st.text(item['response'][:200] + "..." if len(item['response']) > 200 else item['response'])
            st.markdown("---")

# =============================================================================
# 푸터 - 면책 조항
# =============================================================================
st.markdown("---")
st.caption("⚠️ 이 분석은 참고용이며, 투자 판단은 본인의 책임입니다.")
