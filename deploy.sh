#!/bin/bash
set -e

# 設定
AWS_REGION="ap-northeast-1"
ECR_REPOSITORY_NAME="qxai-api-langchain"
FUNCTION_NAME="qxai_api_langchain"
IMAGE_TAG="latest"
AWS_PROFILE="default"  # AWSプロファイルを指定

# 環境変数ファイルの優先順位：.env.production > .env
if [ -f .env.production ]; then
  echo "環境変数を.env.productionファイルから読み込んでいます..."
  export $(grep -v '^#' .env.production | xargs)
elif [ -f .env ]; then
  echo "環境変数を.envファイルから読み込んでいます..."
  export $(grep -v '^#' .env | xargs)
fi

# API キーが設定されていない場合は警告
if [ -z "$OPENAI_API_KEY" ] || [ -z "$APP_API_KEY" ] || [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "警告: 必要なAPI鍵が設定されていません。.env.productionまたは.envファイルを確認してください。"
  echo "必要な環境変数: OPENAI_API_KEY, APP_API_KEY, ANTHROPIC_API_KEY"
  exit 1
fi

# AWS アカウントIDを取得
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile ${AWS_PROFILE} --no-cli-pager)
if [ $? -ne 0 ]; then
  echo "AWS認証情報の取得に失敗しました。AWS CLIの設定を確認してください。"
  exit 1
fi

# ECRリポジトリの存在確認、なければ作成
aws ecr describe-repositories --repository-names ${ECR_REPOSITORY_NAME} --profile ${AWS_PROFILE} --no-cli-pager > /dev/null 2>&1 || \
aws ecr create-repository --repository-name ${ECR_REPOSITORY_NAME} --profile ${AWS_PROFILE} --no-cli-pager

# ECRログイン
echo "ECRにログインしています..."
aws ecr get-login-password --region ${AWS_REGION} --profile ${AWS_PROFILE} --no-cli-pager | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Dockerfileが存在しない場合は作成
if [ ! -f Dockerfile.lambda ]; then
  echo "Dockerfile.lambdaを作成しています..."
  cat > Dockerfile.lambda << EOF
FROM public.ecr.aws/lambda/python:3.9

# 必要なファイルをコピー
COPY lambda_function/ ${LAMBDA_TASK_ROOT}/

# 必要なライブラリをインストール
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Lambda関数ハンドラの設定
CMD [ "lambda_function.lambda_handler" ]
EOF
fi

# Lambda信頼ポリシーファイルが存在しない場合は作成
if [ ! -f lambda-trust-policy.json ]; then
  echo "Lambda信頼ポリシーファイルを作成しています..."
  cat > lambda-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
fi

# Dockerイメージのビルド
echo "Dockerイメージをビルドしています..."
docker buildx build --platform linux/amd64 -t ${ECR_REPOSITORY_NAME}:${IMAGE_TAG} -f Dockerfile.lambda .

# イメージにタグ付け
docker tag ${ECR_REPOSITORY_NAME}:${IMAGE_TAG} ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}

# ECRにプッシュ
echo "イメージをECRにプッシュしています..."
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}

# Lambda実行ロールの確認
ROLE_NAME="lambda-apigateway-role"
ROLE_ARN=$(aws iam get-role --role-name ${ROLE_NAME} --query 'Role.Arn' --output text --profile ${AWS_PROFILE} --no-cli-pager 2>/dev/null || echo "")

if [ -z "$ROLE_ARN" ]; then
  echo "Lambda実行ロールを作成しています..."
  aws iam create-role \
    --role-name ${ROLE_NAME} \
    --assume-role-policy-document file://lambda-trust-policy.json \
    --profile ${AWS_PROFILE} \
    --no-cli-pager

  # 基本的なLambda実行ポリシーをアタッチ
  aws iam attach-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    --profile ${AWS_PROFILE} \
    --no-cli-pager
  
  ROLE_ARN=$(aws iam get-role --role-name ${ROLE_NAME} --query 'Role.Arn' --output text --profile ${AWS_PROFILE} --no-cli-pager)
fi

# 環境変数の準備
ENV_VARS="{\"Variables\":{\"OPENAI_API_KEY\":\"${OPENAI_API_KEY}\",\"APP_API_KEY\":\"${APP_API_KEY}\",\"ANTHROPIC_API_KEY\":\"${ANTHROPIC_API_KEY}\"}}"

# Lambda関数の存在確認
FUNCTION_EXISTS=$(aws lambda list-functions --query "Functions[?FunctionName=='${FUNCTION_NAME}'].FunctionName" --output text --profile ${AWS_PROFILE} --no-cli-pager)

if [ -z "$FUNCTION_EXISTS" ]; then
  # Lambda関数の作成
  echo "Lambda関数を作成しています..."
  aws lambda create-function \
    --function-name ${FUNCTION_NAME} \
    --package-type Image \
    --code ImageUri=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:${IMAGE_TAG} \
    --role ${ROLE_ARN} \
    --architectures x86_64 \
    --timeout 300 \
    --memory-size 1024 \
    --environment "${ENV_VARS}" \
    --profile ${AWS_PROFILE} \
    --no-cli-pager
else
  # Lambda関数の更新
  echo "Lambda関数を更新しています..."
  aws lambda update-function-code \
    --function-name ${FUNCTION_NAME} \
    --image-uri ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:${IMAGE_TAG} \
    --profile ${AWS_PROFILE} \
    --no-cli-pager
  
  # Lambda関数の設定を更新
  echo "Lambda関数の設定を更新しています..."
  # 30秒間待機
  echo "Lambda関数の更新を反映するため、30秒間待機しています..."
  sleep 30

  aws lambda update-function-configuration \
    --function-name ${FUNCTION_NAME} \
    --environment "${ENV_VARS}" \
    --profile ${AWS_PROFILE} \
    --no-cli-pager
fi

echo "デプロイが完了しました！"
echo "Lambda関数名: ${FUNCTION_NAME}"
echo "イメージURI: ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}" 
