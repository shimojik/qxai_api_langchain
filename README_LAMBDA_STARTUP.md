# Lambda デプロイ手順

このドキュメントでは、LangChain を使用した AI 処理を AWS Lambda にデプロイする手順を説明します。

## 前提条件

- AWS CLI がインストールされ、適切に設定されていること
- Docker がインストールされていること
- Python 3.9 以上がインストールされていること

## 1. プロジェクトの構成

プロジェクトは以下のような構成になっています：

```
qxai_api_langchain/
├── lambda_function/
│   ├── lambda_function.py      # Lambda ハンドラー関数
│   ├── chain_builder.py        # チェーン構築ロジック
│   ├── registry/
│   │   └── loader.py           # チェーン登録とロード用モジュール
│   ├── chains/                 # チェーン設定ファイル
│   │   └── summarize_analyze.yaml
│   ├── prompts/                # プロンプトテンプレート
│   │   └── summarize_analyze_step1.md
│   ├── snippets/               # 再利用可能なプロンプト断片
│   └── requirements.txt        # 依存パッケージ
├── .env                        # 環境変数（APIキーなど）
├── Dockerfile.lambda           # Lambda 用 Dockerfile
├── deploy.sh                   # デプロイスクリプト
└── lambda-trust-policy.json    # Lambda 実行ロールのポリシー
```

## 2. 環境変数の設定

`.env` ファイルに必要な API キーを設定します：

```bash
# OpenAI APIキー
OPENAI_API_KEY=your_openai_api_key

# アプリケーションAPIキー
APP_API_KEY=your_app_api_key
```

## 3. チェーンの設定

Lambda関数で処理したいチェーンを定義します。各チェーンは以下のディレクトリに設定します：

1. `lambda_function/chains/`: チェーン設定（YAML）
2. `lambda_function/prompts/`: プロンプトテンプレート
3. `lambda_function/snippets/`: 再利用可能なプロンプト断片（オプション）

### チェーン設定例（YAML）

```yaml
# lambda_function/chains/summarize_analyze.yaml
name: summarize_analyze
description: "テキストの要約と分析を行うシンプルなチェーン"
steps:
  - name: summarize
    prompt_file: prompts/summarize_analyze_step1.md
    input_variables: [text]
    output_key: summary
```

### プロンプト例

```markdown
# lambda_function/prompts/summarize_analyze_step1.md
以下のテキストを、重要な情報を損なわないように簡潔に要約してください。

{text}
```

## 4. Dockerfile の作成

Lambda関数用の Dockerfile を作成します：

```dockerfile
FROM public.ecr.aws/lambda/python:3.9

# ワークディレクトリを設定
WORKDIR ${LAMBDA_TASK_ROOT}

# 必要なファイルをコピー
COPY lambda_function/* ./

# 必要なディレクトリをコピー
COPY lambda_function/chains ./chains/
COPY lambda_function/prompts ./prompts/
COPY lambda_function/registry ./registry/
COPY lambda_function/snippets ./snippets/

# 必要なライブラリをインストール
RUN pip install --no-cache-dir -r requirements.txt

# Lambda関数ハンドラの設定
CMD [ "lambda_function.lambda_handler" ]
```

## 5. デプロイスクリプトの作成

`deploy.sh` スクリプトを作成してデプロイを自動化します：

```bash
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
if [ -z "$OPENAI_API_KEY" ] || [ -z "$APP_API_KEY" ]; then
  echo "警告: 必要なAPI鍵が設定されていません。.env.productionまたは.envファイルを確認してください。"
  echo "必要な環境変数: OPENAI_API_KEY, APP_API_KEY"
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
ENV_VARS="{\"Variables\":{\"OPENAI_API_KEY\":\"${OPENAI_API_KEY}\",\"APP_API_KEY\":\"${APP_API_KEY}\"}}"

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
```

スクリプトに実行権限を付与します：

```bash
chmod +x deploy.sh
```

## 6. デプロイの実行

デプロイスクリプトを実行してLambda関数をデプロイします：

```bash
./deploy.sh
```

## 7. 動作確認

テスト用のイベントJSONを作成して実行します：

```json
// test-event.json
{
  "chain_name": "summarize_analyze",
  "inputs": {
    "text": "これはLambda関数のテストです。正常に動作しているか確認しています。"
  }
}
```

Lambda関数を呼び出してテストします：

```bash
aws lambda invoke \
  --function-name qxai_api_langchain \
  --payload file://test-event.json \
  --cli-binary-format raw-in-base64-out \
  response.json
```

レスポンスを確認します：

```bash
cat response.json
```

JSONレスポンスをデコードして読みやすく表示：

```bash
python3 -c "import json; response = json.load(open('response.json')); body = json.loads(response['body']); print(json.dumps(body, ensure_ascii=False, indent=2))"
```

## トラブルシューティング

### モジュールのインポートエラー

エラーメッセージ: `Unable to import module 'lambda_function': No module named 'lambda_function'`

解決策: Dockerfileを修正して、ファイルの場所とインポートパスが正しく設定されていることを確認します。

### デプロイタイムアウト

エラーメッセージ: `proxyconnect tcp: dial tcp 192.168.65.1:3128: i/o timeout`

解決策: ネットワーク接続を確認し、再度デプロイを試みてください。

## 注意事項

- 本番環境では、APIキーなどの機密情報を環境変数として安全に管理してください。
- Lambda関数のタイムアウト値は、処理内容に応じて適切に設定してください。
- 必要に応じてメモリ割り当てを増やして、処理速度を向上させることができます。 
