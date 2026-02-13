# 주식분석 및 예측 어플리케이션 Agent 

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-Bedrock-FF9900?logo=amazon-aws&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-Kiro_CLI-232F3E?logo=amazon-aws&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.0+-FF4B4B?logo=streamlit&logoColor=white)

Strands Agents SDK와 Amazon Bedrock Claude 모델을 사용한 주식 정보 조회, 분석, 예측 Agent 입니다.

## 🎬 데모 영상

[![YouTube](https://img.shields.io/badge/YouTube-개발과정_영상-red?style=for-the-badge&logo=youtube)](https://youtu.be/Fy1OkAH-PJ0?si=kBJSSUU2mSR5vsV5)

## 🏗️ 아키텍처

![AWS 아키텍처](images/architecture.png)

<details>
<summary>📊 아키텍처 다이어그램 (텍스트 버전)</summary>

```mermaid
flowchart LR
    subgraph AWS Cloud
        ECR[📦 ECR<br/>Container Registry]
        CF[🌐 CloudFront<br/>HTTPS]
        ALB[⚖️ ALB<br/>HTTP:80]
        ECS[🐳 ECS Fargate<br/>Streamlit App]
        Bedrock[🤖 Bedrock<br/>Claude 3.5]
    end

    User[👤 사용자] --> CF
    CF --> ALB
    ALB --> ECS
    ECS <--> |API Calls| Bedrock
    ECR -.-> |Pull Image| ECS
```

</details>

**배포 구조**: User → CloudFront (HTTPS) → ALB (HTTP:80) → ECS Fargate (Streamlit) → Bedrock Claude 3.5

## 📸 스크린샷

### 메인 화면 - 주가 차트
![메인 화면](images/fig1.png)

### AI 기반 주가 예측
![주가 예측](images/fig2.png)

### 기술적 분석 및 뉴스
![기술적 분석](images/fig3.png)

## 기능
 
  1. 💰 현재가 조회 → 주가 데이터 수집
  2. 📊 기술적 분석 → RSI, MACD, 볼린저밴드 계산
  3. 💼 펀더멘털 분석 → P/E, ROE, 재무비율 분석
  4. 🏛️ 기관 보유 현황 → 주요 투자자 데이터 수집
  5. 🏆 동종업계 비교 → 경쟁사 지표 비교
  6. 🌍 거시경제 지표 → 금리, 환율, VIX 분석
  7. 📰 뉴스 감성 분석 → 최신 뉴스 NLP 분석
  8. 🤖 AI 종합 판단 → Claude AI 분석 진행

### 🎯 주요 특징
- **실시간 진행 상황 표시**: AI 분석 중 8단계 진행률 + 투자 팁 제공
- **매수/매도/관망 신호**: 종합 분석 결과를 한눈에 확인
- **NLP 뉴스 감성 분석**: Google News 기반 긍정/부정 점수화 (-100 ~ +100)
- **한글 완벽 지원**: 모든 분석 결과를 한글로 친절하게 제공

## 기술 스택

| 카테고리 | 기술 |
|----------|------|
| AI Framework | Strands Agents SDK |
| AI Model | Amazon Bedrock Claude 3.5 Sonnet |
| Frontend | Streamlit, Plotly |
| Data | yfinance, Google News RSS |
| Infrastructure | AWS CDK (CloudFront, ALB, ECS Fargate, ECR) |
| Security | CloudFront Prefix List, Secret Header 검증 |
| Logging | ALB/CloudFront Access Logs → S3 |

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

## AWS 배포

### 인프라 배포 (CDK)

```bash
cd cdk
npm install

# AWS 계정 부트스트랩 (최초 1회)
npx cdk bootstrap aws://<ACCOUNT_ID>/us-east-1

# 인프라 배포
export CDK_DEFAULT_ACCOUNT=<ACCOUNT_ID>
npx cdk deploy
```

### 앱 배포 (Docker → ECR → ECS)

```bash
# 배포 스크립트 실행 (빌드 + push + 서비스 업데이트)
./deploy.sh

# 특정 태그로 배포
./deploy.sh v1.0.0
```

배포 스크립트가 자동으로 수행하는 작업:
1. ECR 로그인
2. Docker 이미지 빌드
3. ECR에 이미지 Push
4. ECS 서비스 강제 재배포

배포 완료 후 출력되는 **CloudFront URL**로 접속할 수 있습니다.

### 배포 모니터링

```bash
# ECS 서비스 상태 확인
aws ecs describe-services --region us-east-1 \
  --cluster stock-app-cluster --services <SERVICE_NAME> \
  --query 'services[0].deployments'

# 컨테이너 로그 확인
aws logs tail /ecs/stock-app --region us-east-1 --follow

# 컨테이너 내부 디버깅 (ECS Exec)
aws ecs execute-command --region us-east-1 \
  --cluster stock-app-cluster --task <TASK_ID> \
  --container stock-app --interactive --command "/bin/bash"
```

### 보안 구성
- ECS Fargate: Private Subnet에서 실행 (직접 접근 불가)
- ALB: CloudFront Managed Prefix List로 CloudFront IP만 허용
- Origin 검증: X-Origin-Verify 비밀 헤더로 직접 ALB 접근 차단
- 로깅: ALB/CloudFront 액세스 로그 → S3 (90일 보관), 컨테이너 로그 → CloudWatch (30일 보관)

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
├── app.py              # Streamlit UI (메인 애플리케이션)
├── stock_agent.py      # AI Agent 도구 정의
├── Dockerfile          # 컨테이너 이미지 정의
├── .dockerignore       # Docker 빌드 제외 파일
├── deploy.sh           # ECR 빌드/Push/배포 스크립트
├── run_app.sh          # 로컬 실행 스크립트
├── requirements.txt    # Python 패키지 의존성
├── cdk/                # AWS CDK 인프라 코드
│   ├── lib/
│   │   └── stock-app-stack.ts  # CloudFront, ALB, ECS Fargate, ECR 설정
│   └── bin/
│       └── app.ts
├── images/             # 스크린샷 및 아키텍처 이미지
└── README.md
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

## 🤝 기여 방법

1. 이 저장소를 Fork 합니다
2. 새 브랜치를 생성합니다 (`git checkout -b feature/새기능`)
3. 변경사항을 커밋합니다 (`git commit -m 'Add 새기능'`)
4. 브랜치에 Push 합니다 (`git push origin feature/새기능`)
5. Pull Request를 생성합니다

## 📄 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.
