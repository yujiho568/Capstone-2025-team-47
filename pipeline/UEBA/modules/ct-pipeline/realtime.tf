############################################
# Realtime Inference (Lambda on container)
############################################

variable "event_table_name" {
  description = "DynamoDB table name that stores incoming events (with userId partition and timestamp sort key)."
  type        = string
  default     = "UserEventBuffer"
}

variable "rt_lambda_timeout" {
  type    = number
  default = 30
}

variable "rt_lambda_memory" {
  type    = number
  default = 1024
}

# DDB table (must have Streams enabled with NEW_IMAGE)
data "aws_dynamodb_table" "events" {
  name = var.event_table_name
}

# ECR repo for realtime lambda container
resource "aws_ecr_repository" "realtime" {
  name                 = "ct-realtime-infer${var.name_suffix}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  encryption_configuration { encryption_type = "AES256" }
}

output "realtime_ecr_url" {
  value = aws_ecr_repository.realtime.repository_url
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_realtime_role" {
  name = "ct-realtime-role${var.name_suffix}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect : "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })
}

# CloudWatch Logs
resource "aws_iam_role_policy" "lambda_realtime_logs" {
  name = "ct-realtime-logs${var.name_suffix}"
  role = aws_iam_role.lambda_realtime_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect : "Allow",
      Action : [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      Resource : "*"
    }]
  })
}

# S3: read models/**, write results/realtime/**, list bucket
resource "aws_iam_role_policy" "lambda_realtime_s3" {
  name = "ct-realtime-s3${var.name_suffix}"
  role = aws_iam_role.lambda_realtime_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect : "Allow",
        Action : ["s3:ListBucket"],
        Resource : "arn:aws:s3:::${local.bucket_name_effective}"
      },
      {
        Effect : "Allow",
        Action : ["s3:GetObject", "s3:GetObjectVersion"],
        Resource : [
          "arn:aws:s3:::${local.bucket_name_effective}/models/*"
        ]
      },
      {
        Effect : "Allow",
        Action : ["s3:PutObject", "s3:GetObject"],
        Resource : [
          "arn:aws:s3:::${local.bucket_name_effective}/results/realtime/*"
        ]
      }
    ]
  })
}

# DynamoDB: Query (user history), DescribeTable (optional)
resource "aws_iam_role_policy" "lambda_realtime_ddb" {
  name = "ct-realtime-ddb${var.name_suffix}"
  role = aws_iam_role.lambda_realtime_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect : "Allow",
        Action : [
          "dynamodb:Query",
          "dynamodb:GetItem",
          "dynamodb:DescribeTable"
        ],
        Resource : [
          data.aws_dynamodb_table.events.arn
        ]
      }
    ]
  })
}

# ECR pull for Lambda container
resource "aws_iam_role_policy" "lambda_realtime_ecr" {
  name = "ct-realtime-ecr${var.name_suffix}"
  role = aws_iam_role.lambda_realtime_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      { Effect : "Allow", Action : ["ecr:GetAuthorizationToken"], Resource : "*" },
      {
        Effect : "Allow",
        Action : [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability"
        ],
        Resource : aws_ecr_repository.realtime.arn
      }
    ]
  })
}

# Lambda (container image)
resource "aws_lambda_function" "realtime" {
  function_name = "ct-realtime-infer${var.name_suffix}"
  role          = aws_iam_role.lambda_realtime_role.arn

  package_type = "Image"
  image_uri    = var.realtime_image_uri

  timeout       = var.rt_lambda_timeout
  memory_size   = var.rt_lambda_memory
  architectures = ["x86_64"]

  environment {
    variables = {
      BUCKET         = local.bucket_name_effective
      EVENT_TABLE    = var.event_table_name
      MODEL_VERSION  = var.model_version
      EMIT_ANOMALIES = "false"
      PYTHONHASHSEED = "0"
      # 필요시: DOC2VEC_ROOT/OCSVM_ROOT/DBSCAN_ROOT 기본값은 코드에 하드코딩되어 있음
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_realtime_logs,
    aws_iam_role_policy.lambda_realtime_s3,
    aws_iam_role_policy.lambda_realtime_ddb,
    aws_iam_role_policy.lambda_realtime_ecr,
    aws_ecr_repository_policy.lambda_pull
  ]
}

output "realtime_lambda_arn" {
  value = aws_lambda_function.realtime.arn
}

# Streams → Lambda event source mapping (테이블에 Streams(NEW_IMAGE) 켜져 있어야 함)
resource "aws_lambda_event_source_mapping" "realtime_from_ddb_stream" {
  function_name                      = aws_lambda_function.realtime.arn
  event_source_arn                   = data.aws_dynamodb_table.events.stream_arn
  starting_position                  = "LATEST"
  batch_size                         = 10
  maximum_batching_window_in_seconds = 1
  enabled                            = true
  function_response_types            = ["ReportBatchItemFailures"]
  maximum_retry_attempts             = 3
  maximum_record_age_in_seconds      = 3600
  bisect_batch_on_function_error     = true
  destination_config {
    on_failure { destination_arn = aws_s3_bucket.stream_failures.arn }
  }
  filter_criteria {
    filter { pattern = jsonencode({ eventName = ["INSERT"], dynamodb = { NewImage = { eventID = { S = [{ exists = true }] } } } }) }
  }
  depends_on = [aws_iam_role_policy.stream_failure_archive, aws_iam_role_policy.lambda_realtime_ddb_streams]
}

output "realtime_ddb_stream_arn" {
  value = data.aws_dynamodb_table.events.stream_arn
}

# 현재 리전/계정 ID
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# Lambda 실행 역할에 DynamoDB Streams 읽기 권한 부여
resource "aws_iam_role_policy" "lambda_realtime_ddb_streams" {
  name = "ct-realtime-ddb-streams${var.name_suffix}"
  role = aws_iam_role.lambda_realtime_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect : "Allow",
        Action : [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams"
        ],
        # 스트림 버전(타임스탬프)이 바뀌어도 동작하도록 와일드카드 사용
        Resource : "arn:aws:dynamodb:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:table/${var.event_table_name}/stream/*"
      }
    ]
  })
}
