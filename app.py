#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from stock_agent import get_stock_price, analyze_stock_trend, analyze_company_news, get_ticker
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

**종합 분석 요청 시 반드시 3가지 도구 모두 사용:**
1. get_stock_price - 현재가 확인
2. analyze_stock_trend - 기술적 분석
3. analyze_company_news - 뉴스 감성 분석

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

**분석 결과 형식:**
```
📊 종합 판단: [매수 고려 / 매도 고려 / 관망 추천]

긍정 요인:
- [구체적 이유]

부정 요인:
- [구체적 이유]

📰 뉴스 분석:
- [최근 뉴스 제목과 긍정/부정 판단]
- 뉴스 제목을 보고 회사에 긍정적인지 부정적인지 판단하세요
- 긍정 키워드: 실적 개선, 신제품, 투자 확대, 수주, 협력
- 부정 키워드: 실적 악화, 리콜, 소송, 감원, 적자

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
            
            # 회사명 추출
            company_name = user_input.split()[0]
            ticker = get_ticker(company_name)
            
            # 주가 데이터 조회
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            
            if not df.empty:
                # 탭 생성
                tab1, tab2, tab3, tab4 = st.tabs(["📈 차트", "🔮 예측", "📊 기술적 분석", "📰 뉴스"])
                
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
                    prev_price = df['Close'].iloc[-2]
                    change = current_price - prev_price
                    change_pct = (change / prev_price) * 100
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("현재가", f"{current_price:,.0f}원", f"{change_pct:+.2f}%")
                    with col2:
                        st.metric("최고가", f"{df['High'].max():,.0f}원")
                    with col3:
                        st.metric("최저가", f"{df['Low'].min():,.0f}원")
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
                                
                                current_price = float(price_info.get('current_price', 0))
                                
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

**최근 뉴스:**
{chr(10).join([f"- {item['title']}" for item in news.get('news', [])[:3]])}

**예측 요구사항:**
1. {forecast_period} 후 예상 주가를 **반드시 숫자로만** 출력 (예: 160000)
2. 상승/하락/보합 중 하나 선택
3. 예측 근거 (기술적 지표 + 뉴스 + 시장 상황)
4. 신뢰도 (상/중/하)
5. 주요 리스크 요인

**출력 형식 (정확히 따르세요):**
```
예상주가: [숫자만]
방향: [상승/하락/보합]

📊 예측 근거:
- [기술적 분석 근거]
- [뉴스 영향]
- [시장 상황]

신뢰도: [상/중/하]
⚠️ 리스크: [주요 위험 요인]
```

**중요: 예상주가는 반드시 숫자만 출력하세요 (단위 없이)**
"""
                                )
                                
                                forecast_response = str(forecast_agent(f"{company_name} {forecast_period} 주가 예측"))
                                
                                # 예측 주가 추출
                                import re
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
                                    price_change_pct = (price_change / current_price) * 100
                                    
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        st.metric("현재가", f"{current_price:,.0f}원")
                                    with col2:
                                        st.metric(
                                            f"{forecast_period} 후 예측",
                                            f"{predicted_price:,.0f}원",
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
                
                with tab3:
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
                tools=[get_stock_price, analyze_stock_trend, analyze_company_news],
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
