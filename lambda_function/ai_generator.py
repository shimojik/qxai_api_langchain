#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import subprocess
import yaml
from pathlib import Path

TEMPLATE_YAML = """\
name: {chain_name}
description: "このチェーンの目的を記述してください"
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
    """
    新しいチェーン設定とプロンプトファイルを生成するスクリプト
    
    使用方法:
    python ai_generator.py <chain_name>
    """
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
