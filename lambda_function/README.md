# LangChain Lambda

LangChainをAWS Lambdaで動かすためのシステムです。スニペットを部分的に挿入できるフレキシブルなプロンプト構造と、YAMLベースのチェーン定義を特徴としています。

## 機能

- YAMLでChain（複数ステップ）と「スニペットファイル」のマッピングを定義
- Markdownでプロンプト本体を定義し、スニペットをプレースホルダで挿入
- 柔軟なチェーン実行システム
- シンプルなAPIインターフェース

## 構成

```
lambda_function/
├── lambda_function.py       # Lambda関数のエントリーポイント
├── chain_builder.py         # チェーンの構築ロジック
├── registry/                # チェーン登録・管理モジュール
│   └── loader.py
├── chains/                  # チェーン定義（YAML）
│   └── summarize_analyze.yaml
├── prompts/                 # プロンプトテンプレート（Markdown）
│   ├── summarize.md
│   └── analyze.md
├── snippets/                # 挿入可能なスニペット（Markdown）
│   ├── style.md
│   ├── tone.md
│   └── strict_style.md
└── requirements.txt
```

## セットアップ

### ローカル環境

1. 依存パッケージのインストール:

```bash
pip install -r requirements.txt
```

2. 環境変数の設定:

```bash
export OPENAI_API_KEY="your-openai-api-key"
```

もしくは、`.env`ファイルを作成して環境変数を設定:

```
OPENAI_API_KEY=your-openai-api-key
```

### ローカルテスト

付属の`test_local.py`スクリプトを使用してローカルでテストできます:

```bash
python test_local.py --chain summarize_analyze --input '{"text": "テスト用のテキストです"}'
```

## AWSへのデプロイ

### 前提条件

- AWS CLIがインストールされ、適切に設定されていること
- デプロイするためのIAM権限があること

### デプロイ手順

1. デプロイパッケージの作成:

```bash
# 依存パッケージをパッケージディレクトリにインストール
pip install -r requirements.txt --target ./package

# プロジェクトファイルをコピー
cp -r lambda_function.py chain_builder.py registry chains prompts snippets ./package/

# パッケージをZIPファイルに圧縮
cd package
zip -r ../lambda_deployment_package.zip .
cd ..
```

2. Lambda関数のデプロイ:

```bash
# 新規作成の場合
aws lambda create-function \
  --function-name langchain-function \
  --runtime python3.11 \
  --handler lambda_function.lambda_handler \
  --role arn:aws:iam::ACCOUNT_ID:role/lambda-execution-role \
  --zip-file fileb://lambda_deployment_package.zip

# 更新の場合
aws lambda update-function-code \
  --function-name langchain-function \
  --zip-file fileb://lambda_deployment_package.zip
```

3. 環境変数の設定:

```bash
aws lambda update-function-configuration \
  --function-name langchain-function \
  --environment Variables={OPENAI_API_KEY=your-openai-api-key}
```

4. メモリとタイムアウトの設定:

```bash
aws lambda update-function-configuration \
  --function-name langchain-function \
  --timeout 60 \
  --memory-size 512
```

### デプロイ後のテスト

AWS CLIを使用して関数を呼び出す:

```bash
aws lambda invoke \
  --function-name langchain-function \
  --payload '{"chain_name": "summarize_analyze", "inputs": {"text": "テスト用のテキストです"}}' \
  --cli-binary-format raw-in-base64-out \
  output.json

# 結果の確認
cat output.json
```

## セキュリティ上の注意点

- APIキーは必ずLambdaの環境変数として設定し、コードに直接記述しない
- IAMロールは最小権限の原則に従って設定する
- 必要に応じてVPC内にLambdaをデプロイする
- APIゲートウェイと組み合わせる場合は適切な認証・認可を設定する

## 新しいチェーンの追加

新しいチェーンを追加するには、以下の手順を実行します:

1. `ai_generator.py`スクリプトを使用してテンプレートを生成:

```bash
python ai_generator.py new_chain_name
```

2. 生成されたYAMLファイルを編集
3. 必要なプロンプトファイルとスニペットファイルを編集

## トラブルシューティング

- Lambdaのログはcloudwatchで確認できます
- ローカルでのテスト時に問題がある場合は、`test_local.py`に`--debug`オプションを追加することで詳細なログを表示できます

## ライセンス

MIT 
