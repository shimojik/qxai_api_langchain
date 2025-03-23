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

# スニペットと入力変数を指定のフォーマットで配置
DEFAULT_PROMPT_CONTENT = """\
{snippets_placeholder}

{variables_placeholder}
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

    # 環境変数 $EDITOR か、なければ 'code' を使う
    editor = os.environ.get('EDITOR', 'code')
    
    # 1) YAML ファイルをエディタで開く
    print(f"\nステップ1: YAMLファイル '{chain_yaml_path}' を編集してください")
    subprocess.run([editor, str(chain_yaml_path)])
    input("YAMLファイルの編集が完了したらEnterキーを押してください...")

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
    prompt_files = []  # 生成したプロンプトファイルを保存するリスト
    snippet_files = []  # 生成したスニペットファイルを保存するリスト
    
    # まずスニペットを処理して、存在しないものは作成する
    for step in steps:
        snippets = step.get("snippets", {})
        if not snippets:
            continue
            
        for snippet_key, snippet_file in snippets.items():
            snippet_path = Path(snippet_file)
            snippet_path.parent.mkdir(parents=True, exist_ok=True)
            
            if not snippet_path.exists():
                with open(snippet_path, "w", encoding="utf-8") as sf:
                    sf.write(f"新しいスニペットです")
                print(f"Created snippet file: {snippet_file}")
            
            if snippet_path not in snippet_files:
                snippet_files.append(snippet_path)
    
    # 次にプロンプトファイルを処理する
    for step in steps:
        prompt_file = step.get("prompt_file")
        if not prompt_file:
            continue
            
        prompt_path = Path(prompt_file)
        # ディレクトリがなければ作成
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        
        # このステップのスニペットとinput_variablesを取得
        snippets = step.get("snippets", {})
        variables = step.get("input_variables", [])
        
        # スニペットと変数のプレースホルダーを作成
        snippets_placeholder = "\n".join([f"{{{key}}}" for key in snippets.keys()]) if snippets else "ここにプロンプト内容を書いてください。"
        variables_placeholder = "\n".join([f"{{{var}}}" for var in variables]) if variables else "変数が指定されていません。"
        
        # ファイルが存在しない場合だけテンプレ生成
        if not prompt_path.exists():
            prompt_content = DEFAULT_PROMPT_CONTENT.format(
                snippets_placeholder=snippets_placeholder,
                variables_placeholder=variables_placeholder
            )
            
            with open(prompt_path, "w", encoding="utf-8") as pf:
                pf.write(prompt_content)
            print(f"Created prompt file: {prompt_file}")
        
        # 生成済みも含めてリストに追加
        prompt_files.append((prompt_path, step.get("name", f"step{len(prompt_files)+1}")))

    # 4) プロンプトファイルとスニペットファイルを対話形式で順に開く
    if prompt_files:
        print("\nプロンプトファイルを順番に開きます。各ファイル編集後にEnterキーを押してください。")
        for i, (prompt_file, step_name) in enumerate(prompt_files):
            print(f"\nステップ{i+1} ({step_name}): プロンプトファイル '{prompt_file}' を編集してください")
            subprocess.run([editor, str(prompt_file)])
            if i < len(prompt_files) - 1:
                input("このファイルの編集が完了したらEnterキーを押してください...")
    
    if snippet_files and input("\nスニペットファイルも開きますか？ [y/N]: ").lower() == 'y':
        print("\nスニペットファイルを順番に開きます。各ファイル編集後にEnterキーを押してください。")
        for i, snippet_file in enumerate(snippet_files):
            print(f"\nスニペット{i+1}: '{snippet_file}' を編集してください")
            subprocess.run([editor, str(snippet_file)])
            if i < len(snippet_files) - 1:
                input("このファイルの編集が完了したらEnterキーを押してください...")

    print(f"\nFinished generating chain '{chain_name}'.")
    print("YAML and related prompt/snippet files are ready!")
    print(f"すべてのファイルが正常に生成・編集されました。\n")

if __name__ == "__main__":
    main()
