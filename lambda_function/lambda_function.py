import json
import os
import traceback
import logging
from registry.loader import get_chain_by_name

# ロガーの設定
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    AWS Lambda ハンドラー関数
    
    入力例:
    {
      "chain_name": "summarize_analyze",
      "inputs": {
        "text": "要約したい長い文章"
      }
    }
    
    出力例:
    {
      "statusCode": 200,
      "body": {
        "summary": "要約結果",
        "analysis": "分析結果"
      }
    }
    
    Args:
        event: Lambda イベント
        context: Lambda コンテキスト
        
    Returns:
        dict: レスポンス（statusCode, bodyを含む）
    """
    try:
        # リクエストのログ記録（機密情報を除く）
        logger.info(f"Received request for chain: {event.get('chain_name', 'unknown')}")
        
        # チェーン名の取得
        chain_name = event.get("chain_name")
        if not chain_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing 'chain_name' in request"})
            }

        # チェーンの取得
        chain = get_chain_by_name(chain_name)
        if chain is None:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"Chain '{chain_name}' not found"})
            }

        # 入力の取得
        inputs = event.get("inputs", {})
        if not inputs:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing or empty 'inputs' in request"})
            }
            
        # チェーンの実行
        try:
            # RunnableSequenceの実行
            result = chain.invoke(inputs)
            logger.info(f"Chain execution succeeded: {result}")
        except Exception as e:
            # エラーの詳細をログに記録
            logger.error(f"Chain execution error: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "statusCode": 500,
                "body": json.dumps({"error": f"Chain execution failed: {str(e)}"})
            }

        # レスポンスの構築
        response_body = result if isinstance(result, dict) else {"result": str(result)}

        return {
            "statusCode": 200,
            "body": json.dumps(response_body, ensure_ascii=False)
        }

    except Exception as e:
        # 予期しないエラーの処理
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        } 
