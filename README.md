# QXAI API LangChain

LangChainをAWS Lambdaで動かすAPIシステムです。YAMLによるチェーン定義と、スニペットを部分的に挿入できるフレキシブルなプロンプト構造を特徴としています。

## 概要

このプロジェクトは、LangChainフレームワークを利用してAWS Lambda上で動作するAPIを構築します。複数のプロンプトステップを柔軟に組み合わせ、再利用可能なスニペットを活用することで、拡張性の高いAIアプリケーションを実現します。

### 主な特徴

- **YAMLベースのチェーン定義**: 複数のステップを持つチェーンを宣言的に定義
- **スニペット挿入機能**: 共通スタイルやトーンなどを部分的に挿入可能
- **AWS Lambda互換**: サーバーレスアーキテクチャでスケーラブルに運用
- **セキュリティ対策**: 本番環境を想定したセキュリティ設計

## プロジェクト構成

```
qxai_api_langchain/
├── lambda_function/        # Lambda関数一式
│   ├── lambda_function.py  # エントリーポイント
│   ├── chain_builder.py    # チェーンビルダー
│   ├── registry/           # チェーン管理モジュール
│   ├── chains/             # チェーン定義（YAML）
│   ├── prompts/            # プロンプトテンプレート
│   ├── snippets/           # 再利用可能なスニペット
│   ├── README.md           # Lambda関数のドキュメント
│   └── SECURITY.md         # セキュリティガイドライン
├── devnotes/               # 開発記録
└── .env                    # 環境変数（Gitで管理しない）
```

## 開始方法

### 前提条件

- Python 3.9以上
- AWS CLI（デプロイ時）
- OpenAIのAPIキー

### インストール

```bash
# リポジトリのクローン
git clone https://github.com/yourusername/qxai_api_langchain.git
cd qxai_api_langchain

# 依存パッケージのインストール
pip install -r lambda_function/requirements.txt

# 環境変数の設定
cp example.env .env
# .envファイルをエディタで開き、APIキーを設定
```

### ローカルテスト

```bash
cd lambda_function
python test_local.py --chain summarize_analyze --input '{"text": "テストしたいテキスト"}'
```

### デプロイ

詳細なデプロイ手順は `lambda_function/README.md` を参照してください。

## 使用例

1. チェーン定義（YAML）の例:

```yaml
name: summarize_analyze
description: "テキストを要約し、その要約を分析する"
steps:
  - name: summarize
    prompt_file: prompts/summarize.md
    input_variables: ["text"]
    output_key: "summary"
    snippets:
      style_snippet: "snippets/style.md"
      tone_snippet: "snippets/tone.md"
  - name: analyze
    prompt_file: prompts/analyze.md
    input_variables: ["summary"]
    output_key: "analysis"
    snippets:
      style_snippet: "snippets/strict_style.md"
```

2. APIリクエスト例:

```json
{
  "chain_name": "summarize_analyze",
  "inputs": {
    "text": "要約したいテキスト"
  }
}
```

3. APIレスポンス例:

```json
{
  "summary": "要約されたテキスト",
  "analysis": "要約の分析結果"
}
```

## 新しいチェーンの追加

```bash
cd lambda_function
python ai_generator.py new_chain_name
# エディタが開いてチェーン設定を編集
```

## ライセンス

MIT

## 貢献

プルリクエスト大歓迎です。大きな変更を加える場合は、まずissueを作成して議論してください。 
