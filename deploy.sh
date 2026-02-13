#!/bin/bash
set -euo pipefail

REGION="us-east-1"
REPO_NAME="stock-app"
CLUSTER_NAME="stock-app-cluster"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}"
IMAGE_TAG="${1:-latest}"

echo "=== Stock App Deploy ==="
echo "Account: ${ACCOUNT_ID}"
echo "Region:  ${REGION}"
echo "Image:   ${ECR_URI}:${IMAGE_TAG}"
echo ""

# 1. ECR Login
echo "[1/4] ECR 로그인..."
aws ecr get-login-password --region "${REGION}" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# 2. Docker Build
echo "[2/4] Docker 이미지 빌드..."
docker build -t "${ECR_URI}:${IMAGE_TAG}" .

# 3. Docker Push
echo "[3/4] ECR에 이미지 Push..."
docker push "${ECR_URI}:${IMAGE_TAG}"

# 4. ECS Service Update
echo "[4/4] ECS 서비스 업데이트..."
SERVICE_NAME=$(aws ecs list-services --region "${REGION}" --cluster "${CLUSTER_NAME}" \
  --query 'serviceArns[0]' --output text | awk -F'/' '{print $NF}')

aws ecs update-service \
  --region "${REGION}" \
  --cluster "${CLUSTER_NAME}" \
  --service "${SERVICE_NAME}" \
  --force-new-deployment \
  --no-cli-pager

echo ""
echo "=== 배포 완료 ==="
echo "서비스 상태 확인: aws ecs describe-services --region ${REGION} --cluster ${CLUSTER_NAME} --services ${SERVICE_NAME} --query 'services[0].deployments'"
echo "로그 확인: aws logs tail /ecs/stock-app --region ${REGION} --follow"
