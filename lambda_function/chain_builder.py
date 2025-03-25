import os
import yaml
from pathlib import Path
from typing import Dict, Any, List
from operator import itemgetter
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence, RunnablePassthrough
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain.prompts import PromptTemplate

# LangSmithトレーシングの設定
LANGSMITH_TRACING: bool = os.getenv("LANGSMITH_TRACING", "False").lower() == "true"

# LangSmithトレーシングを明示的に無効化
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_ENDPOINT"] = ""
os.environ["LANGCHAIN_API_KEY"] = ""
os.environ["LANGCHAIN_PROJECT"] = ""

def get_llm_from_config(config: Dict[str, Any]) -> Any:
    """
    YAMLの設定から適切なLLMインスタンスを生成します。
    
    Args:
        config: YAMLの設定辞書
        
    Returns:
        LLMインスタンス
    """
    model_config = config.get("model", {})
    provider = model_config.get("provider", "openai")
    model_name = model_config.get("name", "gpt-4o")
    temperature = model_config.get("temperature", 0.7)

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            openai_api_key=api_key,
            streaming=False
        )
    elif provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")
        return ChatAnthropic(
            model=model_name,
            temperature=temperature,
            anthropic_api_key=api_key,
            streaming=False
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

def build_chain_from_yaml(yaml_path: str) -> RunnableSequence:
    """
    YAMLファイルを読み込み、RunnableSequenceを構築します。
    
    Args:
        yaml_path: YAMLファイルのパス
        
    Returns:
        RunnableSequence: 構築されたチェーン
    """
    # YAMLファイルの読み込み
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # ステップの取得
    steps = config.get("steps", [])
    if not steps:
        raise ValueError(f"No steps defined in {yaml_path}.")

    # LLMインスタンスの生成
    llm = get_llm_from_config(config)

    # 最初のステップ
    first_step = steps[0]
    input_vars = first_step.get("input_variables", [])
    output_key = first_step["output_key"]
    
    # プロンプトの準備
    prompt_file = first_step["prompt_file"]
    prompt_text = Path(prompt_file).read_text(encoding="utf-8")
    
    # スニペットの読み込み
    snippet_map = first_step.get("snippets", {})
    partial_dict = {}
    if snippet_map is not None:
        for snippet_key, snippet_path in snippet_map.items():
            snippet_content = Path(snippet_path).read_text(encoding="utf-8")
            partial_dict[snippet_key] = snippet_content
    
    # プロンプトテンプレートの構築
    prompt = PromptTemplate(
        template=prompt_text,
        input_variables=input_vars,
        partial_variables=partial_dict
    )
    
    # 最初のチェーン
    first_chain = prompt | llm | StrOutputParser()
    
    # 一つのステップしかない場合
    if len(steps) == 1:
        return RunnablePassthrough() | {output_key: first_chain}
    
    # 複数ステップの場合、最初のステップの出力を次のステップへ
    chain_so_far = RunnablePassthrough() | {
        "original_input": RunnablePassthrough(),
        output_key: first_chain
    }
    
    # 2番目以降のステップの追加
    for step in steps[1:]:
        input_vars = step.get("input_variables", [])
        output_key = step["output_key"]
        
        # プロンプトの準備
        prompt_file = step["prompt_file"]
        prompt_text = Path(prompt_file).read_text(encoding="utf-8")
        
        # スニペットの読み込み
        snippet_map = step.get("snippets", {})
        partial_dict = {}
        if snippet_map is not None:
            for snippet_key, snippet_path in snippet_map.items():
                snippet_content = Path(snippet_path).read_text(encoding="utf-8")
                partial_dict[snippet_key] = snippet_content
        
        # 入力変数を前ステップの出力から取得するマッピング
        chain_input = {var: itemgetter(var) for var in input_vars}
        
        # プロンプトテンプレートの構築
        prompt = PromptTemplate(
            template=prompt_text,
            input_variables=input_vars,
            partial_variables=partial_dict
        )
        
        # ステップのチェーン
        step_chain = chain_input | prompt | llm | StrOutputParser()
        
        # 全体のチェーンに追加
        chain_so_far = chain_so_far | {
            "original_input": itemgetter("original_input"),
            **{k: itemgetter(k) for k in chain_so_far.output_schema.schema()["properties"].keys() if k != "original_input"},
            output_key: step_chain
        }
    
    # original_input キーを除去
    final_chain = chain_so_far | (lambda x: {k: v for k, v in x.items() if k != "original_input"})
    
    return final_chain 
