from pathlib import Path
import sys
import os

# 親ディレクトリをパスに追加して、chain_builder モジュールをインポートできるようにする
parent_dir = str(Path(__file__).parent.parent.absolute())
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from chain_builder import build_chain_from_yaml

# チェーンキャッシュ
_chain_cache = {}

def get_chain_by_name(chain_name: str):
    """
    chain_name.yaml を読み込んでビルドしたChainを返します。
    一度読み込んだものはキャッシュして再利用することでパフォーマンスを向上させます。
    
    Args:
        chain_name: チェーン名（YAMLファイル名から拡張子を除いたもの）
        
    Returns:
        Chain: 構築されたチェーン、ファイルが存在しない場合はNone
    """
    # キャッシュに存在する場合はそれを返す
    if chain_name in _chain_cache:
        return _chain_cache[chain_name]

    # chains/{chain_name}.yaml のパスを構築
    path = Path(f"chains/{chain_name}.yaml")
    if not path.exists():
        # 絶対パスで試す
        base_dir = Path(__file__).parent.parent
        path = base_dir / f"chains/{chain_name}.yaml"
        if not path.exists():
            return None

    # チェーンを構築してキャッシュに保存
    chain = build_chain_from_yaml(str(path))
    _chain_cache[chain_name] = chain
    return chain 
