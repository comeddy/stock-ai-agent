
# MCP 서버 목록 확인
kiro-cli mcp list

# 특정 MCP 서버 
kiro-cli chat  # 채팅에서 MCP 도구 사용 가능

## 🔧 MCP 서버 관리 명령어

### ✅ 활성화된 서버

1. cdk - AWS CDK MCP Server
   - AWS CDK 관련 작업 지원
   - 명령: uvx awslabs.cdk-mcp-server@latest

2. aws-diagram - AWS Diagram MCP Server
   - AWS 아키텍처 다이어그램 생성
   - 명령: uvx awslabs.aws-diagram-mcp-server@latest

3. frontend - Frontend MCP Server
   - 프론트엔드 개발 지원 (React 등)
   - 명령: uvx awslabs.frontend-mcp-server@latest

4. aws-sentral-mcp - AWS Sentral MCP
   - AWS Salesforce 통합 (AWSentral)
   - 명령: aws-sentral-mcp

5. aws-docs - AWS Documentation MCP Server
   - AWS 문서 검색 및 조회
   - 명령: uvx awslabs.aws-documentation-mcp-server@latest

6. notion - Notion MCP Server
   - Notion API 통합

### ❌ 비활성화된 서버

- **github** - GitHub MCP Server (disabled: true)

이 프로젝트에서는 aws-docs, cdk, aws-diagram MCP 서버를 주로 사용했습니다! 🚀

# Kiro CLI 코딩 가이드

## 📚 목차
1. [프로젝트 개요](#프로젝트-개요)
2. [적용된 Kiro CLI 기능](#적용된-kiro-cli-기능)
3. [개발 워크플로우](#개발-워크플로우)
4. [코드 품질 관리](#코드-품질-관리)
5. [AWS 인프라 배포](#aws-인프라-배포)
6. [베스트 프랙티스](#베스트-프랙티스)

---

## 프로젝트 개요

**프로젝트명**: Stock AI Agent  
**목적**: 실시간 주가 분석 및 AI 기반 예측 서비스  
**기술 스택**: Streamlit, Bedrock Claude 3.5, yfinance, AWS CDK  
**배포 환경**: CloudFront → ALB → EC2 (us-east-1)

---

## 적용된 Kiro CLI 기능

### 1. **파일 시스템 작업 (`fs_read`, `fs_write`)**

#### 사용 사례
```bash
# 파일 읽기 (특정 라인)
fs_read --mode Line --path app.py --start_line 1 --end_line 50

# 파일 전체 읽기
fs_read --mode Line --path stock_agent.py

# 디렉토리 구조 확인
fs_read --mode Directory --path . --depth 2

# 패턴 검색
fs_read --mode Search --path . --pattern "bedrock" --context_lines 3
```

#### 실제 적용 예시
```python
# README.md 스크린샷 섹션 추가
fs_write(
    command="str_replace",
    path="README.md",
    old_str="# 주식 정보 AI Agent\n\nStrands Agents SDK...",
    new_str="# 주식 정보 AI Agent\n\n## 📸 스크린샷\n![메인](images/fig1.png)..."
)
```

**핵심 포인트**:
- `str_replace`는 정확한 문자열 매칭 필요 (공백, 줄바꿈 포함)
- 여러 파일 수정 시 배치 작업 가능
- 파일 생성은 `create` 명령 사용

---

### 2. **Bash 명령 실행 (`execute_bash`)**

#### 사용 사례
```bash
# AWS CLI 명령
execute_bash --command "aws s3 ls" --summary "List S3 buckets"

# 패키지 설치
execute_bash --command "pip install diagrams" --summary "Install diagrams"

# 복잡한 스크립트 실행
execute_bash --command "cd cdk && npm install && cdk deploy" --summary "Deploy CDK"
```

#### 실제 적용 예시
```bash
# S3 버킷 생성 및 코드 업로드
aws s3 mb s3://stock-ai-agent-deploy-$(date +%s) --region us-east-1
cd /path/to/project && zip -r stock-app.zip . -x "*.git*" -x "*node_modules*"
aws s3 cp stock-app.zip s3://bucket-name/

# CDK 배포
cd cdk && cdk bootstrap aws://ACCOUNT_ID/us-east-1
cdk deploy --require-approval never
```

**핵심 포인트**:
- `--summary`로 명령 목적 명시
- 긴 출력은 `| tail -20` 또는 `| head -50`으로 제한
- 에러 처리: `2>&1`로 stderr 캡처

---

### 3. **코드 검색 및 분석 (`grep`, `glob`)**

#### 사용 사례
```bash
# 민감 정보 검색
grep --pattern "AKIA|aws_access|secret" --include "*.py" --path .

# 특정 함수 찾기
grep --pattern "def get_stock_price" --include "*.py"

# 파일 패턴 검색
glob --pattern "**/*.png" --path images/
glob --pattern "cdk/**/*.ts" --max_depth 3
```

#### 실제 적용 예시
```bash
# 보안 검사: Access Key 검색
grep -r -i -E "(aws_access_key|AKIA|password)" \
  --include="*.py" --include="*.ts" \
  --exclude-dir=node_modules --exclude-dir=venv

# 이미지 파일 찾기
find . -name "*.png" -o -name "*.jpg" | grep -v node_modules
```

**핵심 포인트**:
- `--case_sensitive false`로 대소문자 무시
- `--max_files`, `--max_matches_per_file`로 출력 제한
- `.gitignore` 자동 적용

---

### 4. **AWS 리소스 관리 (`use_aws`)**

#### 사용 사례
```bash
# EC2 인스턴스 조회
use_aws --service ec2 --operation describe-instances \
  --parameters '{"Filters": [{"Name": "tag:Name", "Values": ["StockApp"]}]}'

# S3 객체 업로드
use_aws --service s3 --operation put-object \
  --parameters '{"Bucket": "my-bucket", "Key": "file.zip", "Body": "..."}'

# SSM 명령 실행
use_aws --service ssm --operation send-command \
  --parameters '{"InstanceIds": ["i-xxx"], "DocumentName": "AWS-RunShellScript"}'
```

#### 실제 적용 예시
```bash
# EC2 인스턴스 ID 조회
aws ec2 describe-instances \
  --filters "Name=tag:aws:cloudformation:stack-name,Values=StockAppStack" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text

# ALB 타겟 헬스 체크
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --query 'TargetHealthDescriptions[0].TargetHealth'

# SSM으로 Streamlit 시작
aws ssm send-command \
  --instance-ids i-xxx \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /home/ec2-user && streamlit run app.py"]'
```

**핵심 포인트**:
- `--profile` 옵션으로 AWS 프로필 지정
- JSON 파라미터는 작은따옴표로 감싸기
- `--query`로 출력 필터링

---

### 5. **다이어그램 생성 (`generate_diagram`)**

#### 사용 사례
```python
# AWS 아키텍처 다이어그램
with Diagram("Stock AI Agent", show=False, direction="LR"):
    user = User("사용자")
    cf = CloudFront("CloudFront")
    alb = ELB("ALB")
    ec2 = EC2("EC2")
    bedrock = Bedrock("Bedrock")
    
    user >> cf >> alb >> ec2 >> bedrock
```

#### 실제 적용 예시
```python
# 프로젝트 루트에 architecture.png 생성
cd /path/to/project && python3 << 'EOF'
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.network import CloudFront, ELB
from diagrams.aws.ml import Bedrock

with Diagram("Architecture", show=False, filename="architecture"):
    with Cluster("AWS"):
        cf = CloudFront("CF")
        alb = ELB("ALB")
        ec2 = EC2("EC2")
        bedrock = Bedrock("Bedrock")
    
    cf >> alb >> ec2 >> bedrock
EOF
```

**핵심 포인트**:
- Graphviz 설치 필요: `brew install graphviz`
- `show=False`로 자동 열기 방지
- `workspace_dir` 파라미터로 저장 위치 지정

---

### 6. **TODO 리스트 관리 (`todo_list`)**

#### 사용 사례
```bash
# TODO 리스트 생성
todo_list --command create \
  --todo_list_description "AgentCore 마이그레이션" \
  --tasks '[{"task_description": "Tool 정의 변환", "details": "..."}]'

# 작업 완료 표시
todo_list --command complete \
  --current_id 1770478981063 \
  --completed_indices [0, 1] \
  --context_update "에러 처리 완료"

# 작업 추가
todo_list --command add \
  --current_id 1770478981063 \
  --insert_indices [11] \
  --new_tasks '[{"task_description": "배포 테스트"}]'
```

#### 실제 적용 예시
```json
{
  "command": "create",
  "todo_list_description": "Stock AI Agent 개발",
  "tasks": [
    {
      "task_description": "Streamlit UI 구현",
      "details": "차트, 예측, 기술적 분석 탭 추가"
    },
    {
      "task_description": "CDK 인프라 구성",
      "details": "CloudFront + ALB + EC2 스택"
    }
  ]
}
```

**핵심 포인트**:
- `completed_indices`는 0-based 인덱스
- `context_update`로 진행 상황 기록
- `modified_files`로 변경된 파일 추적

---

## 개발 워크플로우

### 1. **프로젝트 초기화**
```bash
# 1. 디렉토리 생성 및 이동
mkdir stock-ai-agent && cd stock-ai-agent

# 2. 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 3. 패키지 설치
pip install streamlit boto3 yfinance strands-agents

# 4. Git 초기화
git init
echo "venv/" >> .gitignore
echo "*.pyc" >> .gitignore
```

### 2. **코드 작성 및 테스트**
```bash
# 1. 로컬 테스트
streamlit run app.py

# 2. 코드 품질 검사
grep -r "TODO" --include="*.py"
grep -r "FIXME" --include="*.py"

# 3. 민감 정보 검사
grep -r -E "(AKIA|aws_secret)" --include="*.py"
```

### 3. **AWS 배포**
```bash
# 1. S3 버킷 생성 및 코드 업로드
aws s3 mb s3://deploy-bucket-$(date +%s)
zip -r app.zip . -x "*.git*" -x "*venv*"
aws s3 cp app.zip s3://deploy-bucket/

# 2. CDK 배포
cd cdk
npm install
cdk bootstrap aws://ACCOUNT_ID/REGION
cdk deploy --require-approval never

# 3. 배포 확인
curl -I https://cloudfront-url.cloudfront.net
```

---

## 코드 품질 관리

### 1. **에러 처리 패턴**
```python
# ✅ 좋은 예시
try:
    price = yf.Ticker(ticker).info.get('currentPrice')
    if price is None:
        return {"error": "주가 정보를 찾을 수 없습니다"}
except Exception as e:
    return {"error": f"오류 발생: {str(e)}"}

# ❌ 나쁜 예시
price = yf.Ticker(ticker).info['currentPrice']  # KeyError 가능
```

### 2. **한글 주석 작성**
```python
def get_stock_price(company_name: str) -> dict:
    """주가 조회 함수
    
    Args:
        company_name: 회사명 (한글 또는 영문)
    
    Returns:
        dict: 주가 정보 (currentPrice, change, changePercent)
    
    처리 로직:
        1. 회사명을 티커 심볼로 변환
        2. yfinance로 주가 조회
        3. 전일 대비 변동률 계산
    """
    # 공백 제거 ("SK 하이닉스" → "SK하이닉스")
    cleaned_name = company_name.replace(" ", "")
    
    # 티커 매핑에서 검색
    ticker = TICKER_MAP.get(cleaned_name.lower())
    ...
```

### 3. **보안 검사 체크리스트**
```bash
# 1. Access Key 검색
grep -r "AKIA[0-9A-Z]{16}" --include="*.py"

# 2. Secret Key 검색
grep -r -i "aws_secret" --include="*.py"

# 3. 하드코딩된 계정 ID
grep -r -E "[0-9]{12}" --include="*.py" | grep -i account

# 4. 개인정보
grep -r -i -E "(email|phone|address)" --include="*.py"
```

---

## AWS 인프라 배포

### 1. **CDK 스택 구조**
```typescript
// cdk/lib/stock-app-stack.ts
export class StockAppStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // VPC 생성
    const vpc = new ec2.Vpc(this, 'StockAppVpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    // EC2 인스턴스
    const instance = new ec2.Instance(this, 'StockAppInstance', {
      vpc,
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MEDIUM
      ),
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
      userData: ec2.UserData.forLinux(),
    });

    // UserData로 Streamlit 설치 및 실행
    instance.userData.addCommands(
      'yum update -y',
      'yum install -y python3.11',
      'aws s3 cp s3://bucket/app.zip .',
      'unzip app.zip',
      'pip install -r requirements.txt',
      'streamlit run app.py --server.port 8501'
    );

    // ALB 생성
    const alb = new elbv2.ApplicationLoadBalancer(this, 'ALB', {
      vpc,
      internetFacing: true,
    });

    // CloudFront 배포
    const distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultBehavior: {
        origin: new origins.LoadBalancerV2Origin(alb),
      },
    });
  }
}
```

### 2. **배포 명령어**
```bash
# 1. CDK 초기화
cd cdk
npm install

# 2. Bootstrap (최초 1회)
cdk bootstrap aws://ACCOUNT_ID/us-east-1

# 3. 배포
cdk deploy --require-approval never

# 4. 출력 확인
cdk deploy | grep -E "(CloudFront|ALB)"

# 5. 스택 삭제 (필요 시)
cdk destroy
```

### 3. **배포 후 검증**
```bash
# 1. CloudFront URL 테스트
curl -I https://d3i1wyhxyywpz2.cloudfront.net

# 2. EC2 인스턴스 상태 확인
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=StockApp" \
  --query 'Reservations[0].Instances[0].State.Name'

# 3. ALB 타겟 헬스
aws elbv2 describe-target-health \
  --target-group-arn ARN \
  --query 'TargetHealthDescriptions[0].TargetHealth.State'

# 4. SSM으로 로그 확인
aws ssm send-command \
  --instance-ids i-xxx \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["tail -50 /var/log/streamlit.log"]'
```

---

## 베스트 프랙티스

### 1. **파일 작업**
- ✅ `fs_read`로 파일 내용 확인 후 수정
- ✅ `str_replace`는 정확한 문자열 매칭
- ✅ 여러 파일 수정 시 배치 작업
- ❌ 파일 전체를 읽지 않고 수정하지 말 것

### 2. **Bash 명령**
- ✅ `--summary`로 명령 목적 명시
- ✅ 긴 출력은 `tail` 또는 `head`로 제한
- ✅ 에러 처리: `2>&1`로 stderr 캡처
- ❌ 대화형 명령 사용 금지 (`vim`, `nano`)

### 3. **AWS 작업**
- ✅ `--query`로 필요한 데이터만 추출
- ✅ `--output text`로 파싱 간소화
- ✅ 리소스 태그로 필터링
- ❌ 하드코딩된 ARN 사용 금지

### 4. **코드 품질**
- ✅ 한글 주석으로 로직 설명
- ✅ Try-except로 에러 처리
- ✅ 타입 힌트 사용
- ❌ 민감 정보 하드코딩 금지

### 5. **배포**
- ✅ S3로 코드 배포 (GitHub 불필요)
- ✅ UserData로 자동 설치
- ✅ CloudFront로 HTTPS 제공
- ❌ EC2에 직접 SSH 접속 금지 (SSM 사용)

---

## 트러블슈팅

### 1. **Streamlit이 시작되지 않을 때**
```bash
# SSM으로 접속
aws ssm start-session --target i-xxx

# 로그 확인
tail -f /var/log/cloud-init-output.log
tail -f /var/log/streamlit.log

# 수동 시작
cd /home/ec2-user
source venv/bin/activate
streamlit run app.py --server.port 8501
```

### 2. **ALB 헬스 체크 실패**
```bash
# 타겟 상태 확인
aws elbv2 describe-target-health --target-group-arn ARN

# 보안 그룹 확인
aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=*StockApp*"

# 포트 8501 열려있는지 확인
curl http://ec2-public-ip:8501
```

### 3. **Code Defender 푸시 차단**
```bash
# 승인 요청
git-defender --request-repo \
  --url https://github.com/user/repo.git \
  --reason 3  # Personal project

# 승인 상태 확인
# https://codedefender.aws.dev/rules

# 승인 후 푸시
git push origin main
```

---

## 요약

이 가이드는 **Stock AI Agent** 프로젝트에서 실제로 사용된 Kiro CLI 기능과 워크플로우를 정리한 것입니다.

**핵심 기능**:
- 파일 시스템 작업 (`fs_read`, `fs_write`)
- Bash 명령 실행 (`execute_bash`)
- 코드 검색 (`grep`, `glob`)
- AWS 리소스 관리 (`use_aws`)
- 다이어그램 생성 (`generate_diagram`)
- TODO 관리 (`todo_list`)

**개발 프로세스**:
1. 로컬 개발 및 테스트
2. 코드 품질 검사
3. S3 업로드
4. CDK 배포
5. 배포 검증

**배포 아키텍처**:
```
사용자 → CloudFront (HTTPS) → ALB (HTTP:80) → EC2 (Streamlit) → Bedrock
```

이 가이드를 참고하여 유사한 프로젝트를 효율적으로 개발하고 배포할 수 있습니다! 🚀
