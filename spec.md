以下に、これまでの内容を踏まえて**「複数種類の共通スニペットを部分的に挿入できる」**形で、かつ**AWS Lambdaで直接呼び出せる**最終サンプル実装をまとめます。  
「実際にデプロイして動くプロダクション用のひな型」をイメージしてください。

---

# 全体像

1. **YAML**でChain（複数ステップ）と「スニペットファイル」のマッピングを定義  
2. **Markdown**で各ステップ本体のプロンプトに `{style_snippet}` や `{tone_snippet}` のような**変数プレースホルダ**を用意  
3. Pythonのコード（**Lambda関数**）で  
   - YAMLを読み込む  
   - 指定されたスニペットファイル群をロードし、**partial_variables**として埋め込む  
   - 入力変数と合わせて**PromptTemplate**を構築し、**SequentialChain**を実行  
4. **イベント（`event`）**で `{ "chain_name": ..., "inputs": {...} }` を受け取り、**結果をJSONで返す**  

この設計なら、**複数スニペット**をそれぞれ**好きな位置**に挿入できるし、**複数ステップの連鎖**も可能です。

---

# ディレクトリ構成例

Lambda にデプロイする際は、以下のようなファイルをまとめて zip 化するか、AWS SAM / CDKなどでデプロイします。

```
lambda_function/
├── lambda_function.py
├── chain_builder.py
├── registry/
│   └── loader.py
├── chains/
│   ├── summarize_analyze.yaml
│   └── ...
├── prompts/
│   ├── summarize.md
│   ├── analyze.md
│   └── ...
├── snippets/
│   ├── style.md
│   ├── tone.md
│   └── ...
├── requirements.txt
└── ...
```

> ※ Lambda で `.env` は使えない（環境変数は Lambda コンソール/設定で渡す）ので、OpenAIキーなどは**Lambdaの環境変数**に設定してください（`OPENAI_API_KEY` など）。

---

## 1. `chains/summarize_analyze.yaml` の例

```yaml
name: summarize_analyze
description: "テキストを要約し、その要約を分析する"
steps:
  - name: summarize
    prompt_file: prompts/summarize.md
    input_variables: ["text"]       # ユーザー入力
    output_key: "summary"

    # ★ ここで部分的にスニペットを挿入したい場合
    snippets:
      style_snippet: "snippets/style.md"   # {style_snippet} の中身
      tone_snippet: "snippets/tone.md"     # {tone_snippet} の中身

  - name: analyze
    prompt_file: prompts/analyze.md
    input_variables: ["summary"]    # 前ステップ出力
    output_key: "analysis"

    # ★ ここでは別のスニペット、あるいは未指定でもOK
    snippets:
      style_snippet: "snippets/strict_style.md"
```

- `snippets` は任意のキー:ファイルパスで、**プロンプト中の `{キー}` に挿入**される想定。  
- もちろん未指定でもOK（共通スニペットを使わないステップもある）。

---

## 2. `prompts/summarize.md`（プロンプトの一例）

```md
{style_snippet}

以下のテキストを200文字以内で要約してください。
文章のスタイルは上記に従ってください。

{tone_snippet}

テキスト:
{text}
```

> - `{style_snippet}` と `{tone_snippet}` は YAMLの `snippets` で指定したファイルから部分的に挿入される。  
> - `{text}` はユーザーの入力変数。

---

## 3. `snippets/style.md`, `snippets/tone.md`（例）

### `snippets/style.md`
```md
あなたは優秀なライターとして、わかりやすく簡潔に書いてください。
```

### `snippets/tone.md`
```md
会話調で書くのを好みますが、敬体での文体も問題ありません。
```

（他にも `strict_style.md` を置いて別の指示をするなど、好みで増やせます）

---

## 4. `chain_builder.py`（**部分テンプレートの組み立て**）

```python
import os
import yaml
from pathlib import Path
from typing import Dict
from langchain.chains import SequentialChain, LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate

# Lambda環境変数からOpenAIキー読み込み
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# シングルトンで一度だけLLMインスタンスを生成
llm = ChatOpenAI(
    model="gpt-3.5-turbo",
    temperature=0.7,
    openai_api_key=OPENAI_API_KEY
)

def build_chain_from_yaml(yaml_path: str) -> SequentialChain:
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    steps = config.get("steps", [])
    if not steps:
        raise ValueError(f"No steps defined in {yaml_path}.")

    chain_list = []
    input_vars_set = set()   # 全体の入力変数を把握
    output_vars = []         # 全ステップの出力変数

    for step in steps:
        # === 1) プロンプト本体読み込み ===
        prompt_file = step["prompt_file"]
        prompt_text = Path(prompt_file).read_text(encoding="utf-8")

        # === 2) スニペットを partial_variables で組み込む ===
        snippet_map: Dict[str, str] = step.get("snippets", {})  # YAMLに定義した "snippets" 
        partial_dict = {}
        for snippet_key, snippet_path in snippet_map.items():
            snippet_content = Path(snippet_path).read_text(encoding="utf-8")
            partial_dict[snippet_key] = snippet_content

        # === 3) PromptTemplate の構築 ===
        input_vars = step.get("input_variables", [])
        output_key = step["output_key"]

        # partial_variablesを使うことで、{snippet_key} 部分は固定的に埋め込まれる
        prompt_template = PromptTemplate(
            input_variables=input_vars,
            template=prompt_text,
            partial_variables=partial_dict
        )

        llm_chain = LLMChain(
            llm=llm,
            prompt=prompt_template,
            output_key=output_key
        )

        chain_list.append(llm_chain)
        # 集約
        input_vars_set.update(input_vars)
        output_vars.append(output_key)

    # === 4) シーケンシャルチェーンにまとめる ===
    seq_chain = SequentialChain(
        chains=chain_list,
        input_variables=list(input_vars_set),
        output_variables=output_vars,
        verbose=False
    )
    return seq_chain
```

ここでの **ポイント**:

- `step["snippets"]` で複数のキーを受け取り、ファイルを読む → `partial_variables` に設定  
- Prompt内の `{style_snippet}`, `{tone_snippet}` などは**固定文字列として自動置換**され、**LLM呼び出し時の入力変数**（たとえば `{text}`）とは別物として扱える  
- 「snippetの位置」は**Markdownのプレースホルダ置き場**次第で柔軟に変えられる

---

## 5. `registry/loader.py`（Chainをキャッシュして使い回し）

```python
from pathlib import Path
from chain_builder import build_chain_from_yaml

_chain_cache = {}

def get_chain_by_name(chain_name: str):
    """
    chain_name.yaml を読み込んでビルドしたChainを返す。
    一度読み込んだものはキャッシュして再利用（パフォーマンス向上）。
    """
    if chain_name in _chain_cache:
        return _chain_cache[chain_name]

    path = Path(f"chains/{chain_name}.yaml")
    if not path.exists():
        return None

    chain = build_chain_from_yaml(str(path))
    _chain_cache[chain_name] = chain
    return chain
```

---

## 6. `lambda_function.py`（AWS Lambdaの本体）

```python
import json
import os
from registry.loader import get_chain_by_name

def lambda_handler(event, context):
    """
    入力例:
    {
      "chain_name": "summarize_analyze",
      "inputs": {
        "text": "要約したい長い文章"
      }
    }
    """
    try:
        chain_name = event.get("chain_name")
        if not chain_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing 'chain_name' in request"})
            }

        chain = get_chain_by_name(chain_name)
        if chain is None:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"Chain '{chain_name}' not found"})
            }

        inputs = event.get("inputs", {})
        # Chain を実行
        result = chain.run(inputs)

        # LLMChain の出力が str or dict かで分岐
        if isinstance(result, str):
            response_body = {"result": result}
        else:
            # SequentialChain なら複数のoutput_variablesがdictで返る可能性がある
            response_body = result

        return {
            "statusCode": 200,
            "body": json.dumps(response_body, ensure_ascii=False)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
```

- **event** で受け取った `chain_name` と `inputs` を用いて、指定のChainを**1回だけ**実行→結果をJSONで返却。  
- **OpenAI APIキー** は Lambda の「環境変数」に `OPENAI_API_KEY=sk-xxxxx` として設定しておく。`chain_builder.py` で `os.environ["OPENAI_API_KEY"]` を読み込む。

---

## 7. スニペット差し替えシナリオ

- デフォルトは `snippets/style.md` + `snippets/tone.md`。  
- より「厳格な」スタイルなら `snippets/strict_style.md` や `snippets/polite_tone.md` などを**YAMLで指定**して切り替え。  
- プロンプト中の `{style_snippet}` `{tone_snippet}` を**そのまま活用**できるため、**プロンプトファイルを一切改修せず**に雰囲気を変えられる。

---

## 呼び出し例 (Lambda直Invoke)

### AWS CLI経由

```bash
aws lambda invoke \
  --function-name MyLLMFunction \
  --payload '{
    "chain_name": "summarize_analyze",
    "inputs": {
      "text": "ここに要約したい文章を入れる"
    }
  }' \
  --cli-binary-format raw-in-base64-out \
  output.json
```

- 結果が `output.json` に書かれる。
- 中身は `{"summary":"...","analysis":"..."}` のようなJSONが返る想定。

### テストイベント
Lambdaコンソールのテストでも同様に:

```json
{
  "chain_name": "summarize_analyze",
  "inputs": {
    "text": "ここに要約したい文章を入れる"
  }
}


---

以下のスクリプト例では、ユーザーが「`python ai_generator.py chain_name`」と入力すると、

1. **chains/chain_name.yaml** がテンプレートをもとに自動生成される（既存なら上書きせず中断か確認）。  
2. そのファイルが自動的にエディタで開く。  
3. ユーザーが YAML を編集し、エディタを終了すると（またはEnterで抜けると）…  
4. スクリプトが最終的に YAML を読み込み、**`prompt_file` や `snippets`** の指定があれば空のファイルを自動生成（すでに存在する場合は作らない）  

という流れになります。  
**ポイントは「YAML編集後に必要なファイルを自動作成し、初期テンプレだけ埋めてあげる」** ことで、新しい機能（チェーン）を追加するたびの初期設定を最小限にする仕組みです。

---

# `ai_generator.py` のコード例

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import subprocess
import yaml
from pathlib import Path

TEMPLATE_YAML = """\
name: {chain_name}
description: "Describe the purpose of this chain"
steps:
  - name: step1
    prompt_file: prompts/{chain_name}_step1.md
    input_variables: [input1]
    output_key: step1_output

    snippets:
      style_snippet: "snippets/style.md"
      # tone_snippet: "snippets/tone.md"

  # 例: 2つ目のステップが必要なら追加
  # - name: step2
  #   prompt_file: prompts/{chain_name}_step2.md
  #   input_variables: [step1_output]
  #   output_key: step2_output
"""

DEFAULT_PROMPT_CONTENT = """\
ここにプロンプト内容を書いてください。
変数一覧: {variables}
"""

def main():
    if len(sys.argv) < 2:
        print("Usage: python ai_generator.py <chain_name>")
        sys.exit(1)

    chain_name = sys.argv[1]
    chain_yaml_path = Path(f"chains/{chain_name}.yaml")

    if chain_yaml_path.exists():
        # 既に存在する場合、上書きしていいか確認
        ans = input(f"'{chain_yaml_path}' already exists. Overwrite? [y/N]: ")
        if ans.lower() != 'y':
            print("Canceled.")
            sys.exit(0)
    else:
        # 新規ファイルをテンプレートで作成
        chain_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(chain_yaml_path, "w", encoding="utf-8") as f:
            f.write(TEMPLATE_YAML.format(chain_name=chain_name))

    # 1) YAML ファイルをエディタで開く
    # 環境変数 $EDITOR か、なければ 'vi' を使う
    editor = os.environ.get('EDITOR', 'vi')
    subprocess.run([editor, str(chain_yaml_path)])

    # 2) エディタ終了後、YAML を読み込み
    with open(chain_yaml_path, "r", encoding="utf-8") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Error: Invalid YAML format. {e}")
            sys.exit(1)

    if not config or "steps" not in config:
        print("No 'steps' found in YAML. Please check your file.")
        sys.exit(0)

    # 3) 各ステップの prompt_file, snippets の値をもとに、ファイルを自動生成
    steps = config["steps"]
    for step in steps:
        prompt_file = step.get("prompt_file")
        if prompt_file:
            prompt_path = Path(prompt_file)
            # ディレクトリがなければ作成
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            # ファイルが存在しない場合だけテンプレ生成
            if not prompt_path.exists():
                # input_variables の中身を文字列化して、デフォルトプロンプトに埋める
                variables = step.get("input_variables", [])
                prompt_content = DEFAULT_PROMPT_CONTENT.format(variables=variables)
                with open(prompt_path, "w", encoding="utf-8") as pf:
                    pf.write(prompt_content)
                print(f"Created prompt file: {prompt_file}")

        # snippets の指定があればファイルもチェック
        snippets = step.get("snippets", {})
        for snippet_key, snippet_file in snippets.items():
            snippet_path = Path(snippet_file)
            snippet_path.parent.mkdir(parents=True, exist_ok=True)
            if not snippet_path.exists():
                with open(snippet_path, "w", encoding="utf-8") as sf:
                    sf.write(f"<!-- {snippet_key} snippet for {chain_name} -->\n")
                print(f"Created snippet file: {snippet_file}")

    print(f"\nFinished generating chain '{chain_name}'.")
    print("YAML and related prompt/snippet files are ready!")
    print(f"Check and edit '{chain_yaml_path}' and the newly created files if needed.\n")

if __name__ == "__main__":
    main()
```

---

## スクリプトの動作解説

1. **起動**:  
   `python ai_generator.py chain_name` と入力すると、`chain_name.yaml` が `chains/` 以下に作成（or 上書き確認）されます。

2. **テンプレート書き込み**:  
   - すでにファイルがある場合は上書きするか確認。  
   - なければ `TEMPLATE_YAML` のひな型を書き込み。

3. **エディタ起動**:  
   - `$EDITOR` が指定されていればそれを優先、なければ `vi` で開く。  
   - エディタで `chains/chain_name.yaml` を編集し、ステップやスニペットをカスタマイズ。

4. **ファイル読込**:  
   - エディタを閉じると、YAMLの内容がロードされ、`steps:` を取得。

5. **自動生成**:  
   - `prompt_file: prompts/...` にファイルが指定されていれば、すでに存在しない場合に作成。  
   - `snippets: { style_snippet: "snippets/..." }` にファイルが指定されていれば、それも作成。  
   - 作るだけなので、中身は初期テンプレ。詳細は後から好きに編集する。

6. **終了**:  
   - メッセージを出して終了。

---

# 使い方

```bash
cd lambda_function/  # or project root, wherever it is
python ai_generator.py my_new_chain
```

- ファイル `chains/my_new_chain.yaml` が作られ、エディタが起動。  
- テンプレートは例えばこんなイメージ：

  ```yaml
  name: my_new_chain
  description: "Describe the purpose of this chain"
  steps:
    - name: step1
      prompt_file: prompts/my_new_chain_step1.md
      input_variables: [input1]
      output_key: step1_output

      snippets:
        style_snippet: "snippets/style.md"
        # tone_snippet: "snippets/tone.md"
  ```

- YAMLを編集して保存・終了すると、自動的に `prompts/my_new_chain_step1.md` と `snippets/style.md` がまだなければ生成される。

---

## 最後に

- このスクリプトは「**新しいChainの初期設定を最小化**」するためのもの。  
- **実運用では**さらに：  
  - 既存ファイルの上書きロジック（要るか要らないか）  
  - バージョニング（git hook連携）  
  - READMEやドキュメント生成（Swagger的な）  
  - 生成後に自動で `lambda_handler.py` のテストイベントを作る

なども拡張できる。  

ただ、**「シンプルな雛形以上になりすぎるとかえって複雑」**になるので、まずはこのスクリプトが**エディタ連動でサクッと初期ファイルを整備**するところから始めてみるのがベストかと。  

これで「1コマンド → YAML → エディタ終了 → 必要ファイルが生成」となり、新しいChain機能の追加体験が快適になるはずです。  
