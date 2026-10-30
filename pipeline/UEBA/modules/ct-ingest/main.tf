# 1. 현재 Terraform을 수행 중인 사용자 정보
data "aws_caller_identity" "current" {}

# 2. Provider 설정

# 3. 현재 실행 중인 사용자의 IAM userName 추출 + 리소스별 sanitize
locals {
  caller_username = var.monitored_username

  # DynamoDB, IAM용: 안전치환 (이미 잘 동작 중)
  sanitized_username_common = replace(local.caller_username, "/[^a-zA-Z0-9_.-]/", "_")

  # Lambda/EventBridge/CloudTrail용: 대시만 허용
  sanitized_username_dash = replace(local.caller_username, "/[^a-zA-Z0-9-]/", "-")

  # ✅ S3 버킷용: 사용자명을 직접 쓰지 않고, md5 앞 8자리 해시로 안전 접미사 생성
  #    → 전역 유니크 보조 + 허용문자 보장
  sanitized_username_s3 = "u${substr(md5(local.caller_username), 0, 8)}"
}


# 4. DynamoDB 테이블 (UserEventBuffer_${IAM계정이름(sanitized)})
resource "aws_dynamodb_table" "user_event_buffer" {
  name         = "UserEventBuffer_${local.sanitized_username_common}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "timestamp"

  attribute {
    name = "userId"
    type = "S"
  }
  attribute {
    name = "timestamp"
    type = "S"
  }
  stream_enabled   = true
  stream_view_type = "NEW_IMAGE"
  lifecycle { prevent_destroy = true }
}

# 6. IAM Role for Lambda (이름에 사용자명 접미사)
resource "aws_iam_role" "lambda_exec" {
  name = "lambda_exec_role-${local.sanitized_username_common}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# 7. IAM Policy for DynamoDB access (이름에 사용자명 접미사)
resource "aws_iam_policy" "lambda_dynamodb_policy" {
  name = "lambda_dynamodb_access-${local.sanitized_username_common}"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem"
        ],
        Resource = [aws_dynamodb_table.events_v2.arn]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_dynamodb_attach" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_dynamodb_policy.arn
}

# 8. IAM Policy for CloudWatch Logs access (이름에 사용자명 접미사)
resource "aws_iam_policy" "lambda_logging_policy" {
  name = "lambda_logging_policy-${local.sanitized_username_common}"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logging_attach" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_logging_policy.arn
}

# 9. Lambda Function: EventCollectorLambda (이름에 사용자명 접미사)
resource "aws_lambda_function" "event_collector" {
  filename         = data.archive_file.collector.output_path
  function_name    = "EventCollectorLambda-${local.sanitized_username_dash}"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "event_collector.handler"
  runtime          = "python3.11"
  timeout          = 60
  source_code_hash = data.archive_file.collector.output_base64sha256

  depends_on = [aws_iam_role_policy_attachment.lambda_dynamodb_attach, aws_iam_role_policy_attachment.lambda_logging_attach, aws_iam_role_policy.collector_failures]
  environment {
    variables = {
      USER_EVENT_TABLE = aws_dynamodb_table.events_v2.name
      RETENTION_DAYS   = tostring(var.retention_days)
      FAILURE_BUCKET   = aws_s3_bucket.failures.id
      PYTHONPATH       = "/var/task"
    }
  }
}

# 10. EventBridge Rule (CloudTrail 관리 이벤트 전체 + userName 필터링)
resource "aws_cloudwatch_event_rule" "cloudtrail_events" {
  name        = "CloudTrailUserActivityRule-${local.sanitized_username_dash}"
  description = "Route all CloudTrail API calls by current Terraform user"

  # 읽기/쓰기 모든 관리 이벤트 포함
  state = "ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS"

  event_pattern = jsonencode({
    "detail-type" = ["AWS API Call via CloudTrail"],
    "detail" = {
      "userIdentity" = {
        # 필터는 원래 userName 그대로 사용 (정확한 매칭)
        "userName" = [tostring(local.caller_username)]
      }
    }
  })
}

# 11. Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.event_collector.arn
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cloudtrail_events.arn
}

# 12. EventBridge Target
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.cloudtrail_events.name
  target_id = "SendToEventCollectorLambda"
  arn       = aws_lambda_function.event_collector.arn
  retry_policy {
    maximum_retry_attempts       = 6
    maximum_event_age_in_seconds = 3600
  }
  dead_letter_config { arn = aws_sqs_queue.delivery_failures.arn }
  depends_on = [aws_sqs_queue_policy.delivery_failures, aws_lambda_function_event_invoke_config.collector, aws_lambda_permission.allow_eventbridge]
}

# 13. S3 버킷 (CloudTrail 로그 저장용) — 전역 유니크 + 사용자명 접미사(소문자/제약 준수)
resource "aws_s3_bucket" "trail_bucket" {
  bucket = "ueba-cloudtrail-logs-${data.aws_caller_identity.current.account_id}-${local.sanitized_username_s3}"
  lifecycle { prevent_destroy = true }
}


# 14. S3 버킷 정책 (CloudTrail 로그 저장 허용)
resource "aws_s3_bucket_policy" "trail_bucket_policy" {
  bucket = aws_s3_bucket.trail_bucket.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid       = "AWSCloudTrailAclCheck",
        Effect    = "Allow",
        Principal = { Service = "cloudtrail.amazonaws.com" },
        Action    = "s3:GetBucketAcl",
        Resource  = aws_s3_bucket.trail_bucket.arn
      },
      {
        Sid       = "AWSCloudTrailWrite",
        Effect    = "Allow",
        Principal = { Service = "cloudtrail.amazonaws.com" },
        Action    = "s3:PutObject",
        Resource  = "${aws_s3_bucket.trail_bucket.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*",
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

# 15. CloudTrail 설정 (이름에 사용자명 접미사)
resource "aws_cloudtrail" "main" {
  name                          = "ueba-cloudtrail-${local.sanitized_username_dash}"
  s3_bucket_name                = aws_s3_bucket.trail_bucket.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_logging                = true
  enable_log_file_validation    = true

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }

  depends_on = [aws_s3_bucket_policy.trail_bucket_policy]
}
