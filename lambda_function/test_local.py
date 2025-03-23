#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import argparse
from dotenv import load_dotenv
from lambda_function import lambda_handler

# .envファイルから環境変数を読み込む
load_dotenv()

def main():
    """
    ローカル環境でLambda関数をテストするためのスクリプト
    
    使用方法:
    python test_local.py --chain <chain_name> --input <input_json>
    
    例:
    python test_local.py --chain summarize_analyze --input '{"text": "テスト用のテキストです。要約と分析を行ってください。"}'
    """
    parser = argparse.ArgumentParser(description='Test Lambda function locally')
    parser.add_argument('--chain', required=True, help='Chain name to test')
    parser.add_argument('--input', required=True, help='JSON input string')
    
    args = parser.parse_args()
    
    try:
        # 入力JSONを解析
        input_data = json.loads(args.input)
        
        # イベントを構築
        event = {
            "chain_name": args.chain,
            "inputs": input_data
        }
        
        # Lambda関数を呼び出し
        print(f"Testing Lambda with event: {json.dumps(event, ensure_ascii=False)}")
        result = lambda_handler(event, None)
        
        # 結果を表示
        print("\nResult:")
        if isinstance(result, dict) and "body" in result:
            if isinstance(result["body"], str):
                body = json.loads(result["body"])
                print(json.dumps(body, ensure_ascii=False, indent=2))
            else:
                print(json.dumps(result["body"], ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON input: {args.input}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main() 
