# Rails から AWS Lambda を呼び出す実装ガイド

このドキュメントでは、Rails アプリケーションから AWS Lambda 関数 (`qxai_api_langchain`) を呼び出すための設定と実装方法を説明します。

## 1. 必要な Gem の追加

`Gemfile` に AWS SDK for Lambda を追加します。

```ruby
# Gemfile
gem 'aws-sdk-lambda', '~> 1.0'
```

追加後、bundle install を実行します。

```bash
bundle install
```

## 2. AWS 認証情報の設定

### 環境変数の設定

AWS の認証情報を環境変数として設定します。開発環境では `.env` ファイル、本番環境では適切な方法（環境変数、credentials.yml.enc など）で管理してください。

```bash
# .env または環境変数
AWS_REGION=ap-northeast-1
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
```

### AWS 設定のイニシャライザ

`config/initializers/aws.rb` を作成して AWS SDK の設定を行います。

```ruby
# config/initializers/aws.rb
require 'aws-sdk-core'

Aws.config.update({
  region: ENV['AWS_REGION'] || 'ap-northeast-1',
  credentials: Aws::Credentials.new(
    ENV['AWS_ACCESS_KEY_ID'],
    ENV['AWS_SECRET_ACCESS_KEY']
  )
})
```

## 3. Lambda 呼び出し用のサービスクラスの実装

`app/services/lambda_service.rb` に Lambda 関数を呼び出すためのサービスクラスを実装します。

```ruby
# app/services/lambda_service.rb
require 'aws-sdk-lambda'
require 'json'

class LambdaService
  attr_reader :client, :function_name

  # 初期化
  def initialize(function_name: 'qxai_api_langchain', region: 'ap-northeast-1')
    @function_name = function_name
    @client = Aws::Lambda::Client.new(region: region)
  end

  # Lambdaを呼び出してレスポンスを取得
  def invoke(chain_name, inputs = {})
    # リクエストのペイロードを構築
    payload = {
      chain_name: chain_name,
      inputs: inputs
    }.to_json

    # Lambdaを同期的に呼び出す
    response = client.invoke({
      function_name: function_name,
      invocation_type: 'RequestResponse', # 同期呼び出し
      payload: payload
    })

    # レスポンスを処理
    response_payload = JSON.parse(response.payload.read)
    
    if response.function_error
      Rails.logger.error("Lambda error: #{response.function_error}, Payload: #{response_payload}")
      raise "Lambda実行エラー: #{response_payload['errorMessage']}"
    end

    # レスポンスボディをJSONとしてパース
    body = JSON.parse(response_payload['body'])
    
    # 結果を返す
    return body
  end
end
```

## 4. コントローラでの使用例

### APIコントローラの例

```ruby
# app/controllers/api/v1/ai_controller.rb
module Api
  module V1
    class AiController < ApplicationController
      def summarize
        # リクエストパラメータの取得
        text = params[:text]
        
        # パラメータのバリデーション
        unless text.present?
          return render json: { error: 'テキストが指定されていません' }, status: :bad_request
        end
        
        begin
          # Lambda サービスのインスタンス化
          lambda_service = LambdaService.new
          
          # Lambda 関数の呼び出し
          result = lambda_service.invoke('summarize_analyze', { text: text })
          
          # 結果を返す
          render json: { summary: result['summary'] }
        rescue => e
          Rails.logger.error("AI処理エラー: #{e.message}")
          render json: { error: 'AI処理中にエラーが発生しました' }, status: :internal_server_error
        end
      end
    end
  end
end
```

### ルーティングの設定

```ruby
# config/routes.rb
Rails.application.routes.draw do
  namespace :api do
    namespace :v1 do
      post 'ai/summarize', to: 'ai#summarize'
    end
  end
end
```

## 5. モデルでの使用例

特定のモデルに AI 処理を統合する例：

```ruby
# app/models/document.rb
class Document < ApplicationRecord
  # コールバックを使用して保存時に自動で要約を生成
  before_save :generate_summary, if: -> { content_changed? && content.present? }
  
  private
  
  def generate_summary
    return if content.blank?
    
    begin
      lambda_service = LambdaService.new
      result = lambda_service.invoke('summarize_analyze', { text: content })
      self.summary = result['summary']
    rescue => e
      Rails.logger.error("要約生成エラー: #{e.message}")
      # エラーが発生してもモデルの保存は続行
    end
  end
end
```

## 6. バックグラウンド処理での使用例

処理に時間がかかる場合、Active Job を使用してバックグラウンドで処理を行う例：

```ruby
# app/jobs/ai_processing_job.rb
class AiProcessingJob < ApplicationJob
  queue_as :ai_tasks
  
  def perform(record_id, text, chain_name = 'summarize_analyze')
    record = Document.find_by(id: record_id)
    return unless record
    
    begin
      lambda_service = LambdaService.new
      result = lambda_service.invoke(chain_name, { text: text })
      
      # 結果を保存
      record.update(summary: result['summary'])
    rescue => e
      Rails.logger.error("AI処理ジョブエラー: #{e.message}")
      # 必要に応じてリトライやエラー通知などを実装
    end
  end
end

# 使用例 (コントローラやモデルから)
AiProcessingJob.perform_later(document.id, document.content)
```

## 7. エラーハンドリングとロギング

Lambda 関数呼び出しに関するエラーハンドリングとロギングの拡張例：

```ruby
# config/initializers/lambda_errors.rb
module LambdaErrors
  class InvocationError < StandardError; end
  class TimeoutError < StandardError; end
  class ValidationError < StandardError; end
end

# app/services/enhanced_lambda_service.rb
class EnhancedLambdaService < LambdaService
  def invoke(chain_name, inputs = {})
    # 処理開始時間を記録
    start_time = Time.current
    
    begin
      # 親クラスのメソッドを呼び出し
      result = super
      
      # 処理時間をログ記録
      duration = Time.current - start_time
      Rails.logger.info("Lambda invocation successful: chain=#{chain_name}, duration=#{duration.round(2)}s")
      
      return result
    rescue => e
      # 例外の種類に応じた適切なエラーに変換
      case e.message
      when /timeout/i
        raise LambdaErrors::TimeoutError, "Lambda実行がタイムアウトしました: #{e.message}"
      when /validation/i
        raise LambdaErrors::ValidationError, "入力パラメータが不正です: #{e.message}"
      else
        raise LambdaErrors::InvocationError, "Lambda実行中にエラーが発生しました: #{e.message}"
      end
    end
  end
end
```

## 8. テスト方法

Rails での Lambda サービスのテスト例 (RSpec):

```ruby
# spec/services/lambda_service_spec.rb
require 'rails_helper'

RSpec.describe LambdaService do
  let(:service) { LambdaService.new }
  let(:lambda_client) { instance_double(Aws::Lambda::Client) }
  let(:lambda_response) do
    double('response',
      payload: StringIO.new('{"statusCode":200,"body":"{\"summary\":\"テスト要約文\"}"}'),
      function_error: nil
    )
  end
  
  before do
    allow(Aws::Lambda::Client).to receive(:new).and_return(lambda_client)
    allow(lambda_client).to receive(:invoke).and_return(lambda_response)
  end
  
  describe '#invoke' do
    it '正常に Lambda 関数を呼び出して結果を返すこと' do
      result = service.invoke('summarize_analyze', { text: 'テストテキスト' })
      
      expect(result).to include('summary')
      expect(result['summary']).to eq('テスト要約文')
      
      expect(lambda_client).to have_received(:invoke).with(
        hash_including(
          function_name: 'qxai_api_langchain',
          invocation_type: 'RequestResponse'
        )
      )
    end
    
    context 'エラー発生時' do
      let(:error_response) do
        double('error_response',
          payload: StringIO.new('{"errorMessage":"テストエラー"}'),
          function_error: 'Unhandled'
        )
      end
      
      it 'エラーをスローすること' do
        allow(lambda_client).to receive(:invoke).and_return(error_response)
        
        expect {
          service.invoke('summarize_analyze', { text: 'テストテキスト' })
        }.to raise_error(/Lambda実行エラー/)
      end
    end
  end
end
```

## 9. 本番環境での考慮事項

### タイムアウト設定

Lambda関数の実行には制限時間があります。長時間処理が必要な場合は、タイムアウト設定を適切に行い、非同期実行を検討してください。

```ruby
# タイムアウト設定例
Aws.config.update({
  http_open_timeout: 15, # 接続タイムアウト (秒)
  http_read_timeout: 60  # 読み取りタイムアウト (秒)
})
```

### リトライと耐障害性

ネットワークエラーなどの一時的な障害に対応するためのリトライロジックを実装することを検討してください。

```ruby
# リトライ実装例
def invoke_with_retry(chain_name, inputs, max_retries: 3, backoff: 2)
  retries = 0
  begin
    invoke(chain_name, inputs)
  rescue Aws::Lambda::Errors::ServiceError => e
    if retries < max_retries
      retries += 1
      sleep(backoff ** retries) # 指数バックオフ
      retry
    else
      raise
    end
  end
end
```

### モニタリング

CloudWatch と連携して、Lambda 関数の呼び出しを監視します。

```ruby
# 監視情報を追加した呼び出し例
def monitored_invoke(chain_name, inputs, context = {})
  start_time = Time.current
  result = invoke(chain_name, inputs)
  duration = (Time.current - start_time) * 1000 # ミリ秒単位
  
  # カスタムメトリクスの記録（例: New Relic, Datadog など）
  record_metric('lambda.invoke.duration', duration, { chain: chain_name })
  record_metric('lambda.invoke.count', 1, { chain: chain_name, status: 'success' })
  
  result
rescue => e
  record_metric('lambda.invoke.count', 1, { chain: chain_name, status: 'error' })
  raise
end
```

## 10. 環境ごとの設定

異なる環境（開発、ステージング、本番）で異なる Lambda 関数を使用する設定例：

```yaml
# config/lambda_functions.yml
default: &default
  function_name: qxai_api_langchain
  region: ap-northeast-1

development:
  <<: *default
  function_name: qxai_api_langchain_dev

test:
  <<: *default
  function_name: qxai_api_langchain_test

staging:
  <<: *default
  function_name: qxai_api_langchain_staging

production:
  <<: *default
  function_name: qxai_api_langchain_prod
```

```ruby
# config/initializers/lambda_config.rb
lambda_config = YAML.load_file(Rails.root.join('config', 'lambda_functions.yml'))[Rails.env]

Rails.application.config.lambda_function = {
  name: lambda_config['function_name'],
  region: lambda_config['region']
}
```

```ruby
# app/services/lambda_service.rb (修正版)
def initialize(function_name: nil, region: nil)
  config = Rails.application.config.lambda_function
  @function_name = function_name || config[:name]
  @client = Aws::Lambda::Client.new(region: region || config[:region])
end
``` 
