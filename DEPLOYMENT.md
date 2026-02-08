# AWS CDK 배포 가이드

## 📦 인프라 구조

```
CloudFront (HTTPS)
    ↓
Application Load Balancer (HTTP)
    ↓
EC2 Instance (Streamlit on port 8501)
```

## 🚀 배포 단계

### 1. 사전 준비

```bash
# AWS CLI 설정
aws configure

# CDK 설치
npm install -g aws-cdk

# TypeScript 설치
npm install -g typescript ts-node

# 프로젝트 의존성 설치
cd cdk
npm install
```

### 2. CDK Bootstrap (최초 1회)

```bash
cdk bootstrap aws://ACCOUNT-ID/us-east-1
```

### 3. 코드 업로드 준비

**중요:** EC2 UserData에서 GitHub 저장소를 클론합니다.

`cdk/lib/stock-app-stack.ts` 파일에서 수정:
```typescript
'git clone https://github.com/YOUR_USERNAME/stock-app.git',
```

또는 S3에 업로드:
```bash
# 코드를 zip으로 압축
cd /Users/youngjik/Documents/01.Work/20260208-stock-app-kiro-cli
zip -r stock-app.zip . -x "*.git*" -x "*node_modules*" -x "*cdk.out*"

# S3에 업로드
aws s3 cp stock-app.zip s3://YOUR-BUCKET/stock-app.zip

# UserData 수정
'aws s3 cp s3://YOUR-BUCKET/stock-app.zip /home/ec2-user/stock-app.zip',
'unzip stock-app.zip',
```

### 4. 환경 변수 설정

EC2에서 Bedrock 사용을 위해 IAM Role이 자동으로 설정됩니다.
추가 환경 변수가 필요하면 UserData에 추가:

```typescript
'export NOTION_API_KEY=your_key',
```

### 5. 배포

```bash
cd cdk

# 변경사항 확인
cdk diff

# 배포
cdk deploy

# 출력 예시:
# CloudFrontUrl = https://d1234567890.cloudfront.net
# AlbDnsName = stock-app-alb-123456789.us-east-1.elb.amazonaws.com
```

### 6. 접속

배포 완료 후 CloudFront URL로 접속:
```
https://d1234567890.cloudfront.net
```

## 🔧 문제 해결

### EC2 인스턴스 확인

```bash
# SSM Session Manager로 접속
aws ssm start-session --target i-1234567890abcdef0

# Streamlit 로그 확인
tail -f /var/log/cloud-init-output.log

# Streamlit 프로세스 확인
ps aux | grep streamlit

# 수동 실행
cd /home/ec2-user/stock-app
source venv/bin/activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

### ALB Health Check 확인

```bash
# Target Group 상태 확인
aws elbv2 describe-target-health --target-group-arn YOUR_TG_ARN
```

## 💰 비용 예상

- **EC2 t3.medium**: ~$30/월
- **ALB**: ~$20/월
- **CloudFront**: 데이터 전송량에 따라
- **NAT Gateway**: ~$32/월

**총 예상 비용: ~$82/월**

## 🗑️ 리소스 삭제

```bash
cd cdk
cdk destroy
```

## 📝 주요 설정

- **Region**: us-east-1
- **Instance Type**: t3.medium (2 vCPU, 4GB RAM)
- **OS**: Amazon Linux 2023
- **Python**: 3.11
- **Streamlit Port**: 8501
- **ALB Port**: 80
- **CloudFront**: HTTPS (자동 리다이렉트)

## 🔐 보안

- EC2는 Private Subnet에 배치
- ALB만 Public Subnet에 노출
- CloudFront를 통한 HTTPS 강제
- IAM Role로 Bedrock 접근 (키 불필요)
- Security Group으로 포트 제한
