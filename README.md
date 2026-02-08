# 주식 정보 AI Agent

Strands Agents SDK와 Amazon Bedrock Claude 모델을 사용한 주식 정보 조회 AI Agent입니다.

## 🏗️ 아키텍처

![AWS 아키텍처](images/architecture.png)

**배포 구조**: User -> CloudFront (HTTPS) → ALB (HTTP:80) → EC2 (Streamlit) → Bedrock Claude 3.5

## 📸 스크린샷

[![개발과정 영상](https://img.youtube.com/vi/Fy1OkAH-PJ0/maxresdefault.jpg)](https://youtu.be/Fy1OkAH-PJ0?si=8uR1r2ScOfdrgFx9)

### 메인 화면 - 주가 차트
![메인 화면](images/fig1.png)

### AI 기반 주가 예측
![주가 예측](images/fig2.png)

### 기술적 분석 및 뉴스
![기술적 분석](images/fig3.png)

## 기능

- 실시간 주식 현재가 조회
- 전일 대비 변동률 계산
- **주가 추이 분석**
  - 이동평균선 (5일, 20일, 60일)
  - RSI (상대강도지수) - 과매수/과매도 판단
  - MACD (이동평균수렴확산) - 추세 전환 신호
  - 볼린저 밴드 - 가격 변동성 및 과열/침체 구간
  - 골든크로스/데드크로스 - 매수/매도 타이밍
  - 변동성 및 거래량 분석
  - 기간별 수익률 계산
- **뉴스 감성 분석** (NEW)
  - Google News에서 최근 뉴스 수집
  - AI 기반 긍정/부정/중립 판단
  - 주가 영향도 평가
- 한글로 친절한 응답 제공

## 기술 스택

- **Strands Agents SDK**: AI Agent 프레임워크
- **Amazon Bedrock**: Claude 3.5 Sonnet 모델
- **yfinance**: 주가 데이터 조회

## 설치 방법

1. 가상환경 활성화:
```bash
source venv/bin/activate
```

2. 패키지 설치 (이미 완료됨):
```bash
pip install -r requirements.txt
```

## AWS 설정

Amazon Bedrock 사용을 위해 AWS 자격증명이 필요합니다:

```bash
# AWS CLI로 설정
aws configure

# 또는 환경변수 설정
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

## 실행 방법

**Streamlit UI 버전 (추천):**
```bash
# 방법 1: 실행 스크립트 사용
./run_app.sh

# 방법 2: 직접 실행
source venv/bin/activate
streamlit run app.py
```

**CLI 버전:**
```bash
source venv/bin/activate
python stock_agent.py
```

브라우저가 자동으로 열리며 `http://localhost:8501`에서 접속 가능합니다.

## 사용 예시

```
📊 종합 판단: 관망 추천

현재가: 60,700원 (전일대비 -1.94%)
3개월 수익률: +31.67%

긍정 요인:
- 주가가 5일(60,420원), 20일(59,365원), 60일(52,830원) 이동평균선 위에 위치하여 전반적인 상승 추세
- RSI 56.67로 적정 구간에 위치 (과열/과매도 아님)
- 3개월간 31.67%의 강한 상승세 기록
- 볼린저밴드 중앙(57.61%) 부근에서 안정적 움직임

부정 요인:
- MACD(-231.81)가 시그널선 아래에 위치하여 단기 하락 모멘텀 존재
- 거래량 비율 47.6%로 다소 낮은 편
- 변동성이 52.08%로 높은 편이라 리스크 주의 필요

📰 뉴스 분석:
- "KEPCO stock jumps 9%" - 증권사의 목표가 상향 조정(70,000원)으로 주가 9% 상승했다는 긍정적 뉴스

⚠️ 투자 조언:
1. 전반적인 추세는 상승세이나 단기 하락 모멘텀이 감지됨
2. 높은 변동성을 감안하여 분할 매수 전략 고려
3. 60일 이동평균선(52,830원)을 지지선으로 활용 가능
4. 전기요금 정책, 원자재 가격 등 외부 변수에 민감하므로 관련 뉴스 모니터링 필요

⚠️ 투자 판단은 본인의 책임이며, 이 분석은 참고용입니다.
```

## 지원 기업

**미국 주식** (영문/한글 모두 지원):
- Amazon / 아마존 (AMZN)
- Apple / 애플 (AAPL)
- Tesla / 테슬라 (TSLA)
- Google / 구글 (GOOGL)
- Microsoft / 마이크로소프트 (MSFT)
- Meta / 메타 (META)
- Nvidia / 엔비디아 (NVDA)

**한국 주식**:
- 삼성전자 (005930.KS)
- SK하이닉스 / 하이닉스 (000660.KS)
- 네이버 (035420.KS)
- 카카오 (035720.KS)
- 현대차 / 현대자동차 (005380.KS)
- LG전자 (066570.KS)
- 포스코 (005490.KS)

**기타 한국 주식**: 6자리 종목코드를 직접 입력하면 조회 가능합니다.
- 예: "051910" (LG화학), "035720" (카카오)

다른 기업은 티커 심볼을 직접 입력하면 조회 가능합니다.

## 프로젝트 구조

```
.
├── stock_agent.py      # 메인 Agent 코드 (CLI 버전)
├── app.py             # Streamlit UI 버전
├── run_app.sh         # Streamlit 실행 스크립트
├── requirements.txt    # 패키지 의존성
├── .env.example       # 환경변수 예시
└── README.md          # 프로젝트 문서
```

## 코드 품질

- ✅ 중복 코드 제거 (공통 함수 추출)
- ✅ 에러 처리 강화 (try-except)
- ✅ 0으로 나누기 방지 (RSI, 변동성 계산)
- ✅ 데이터 검증 (NaN, 빈 데이터)
- ✅ 타입 안정성 (명확한 반환 타입)

## 주의사항

- yfinance는 Yahoo Finance API를 사용하므로 실시간 데이터가 약간 지연될 수 있습니다
- AWS Bedrock 사용 시 비용이 발생할 수 있습니다
- 투자 조언이 아닌 정보 제공 목적입니다
