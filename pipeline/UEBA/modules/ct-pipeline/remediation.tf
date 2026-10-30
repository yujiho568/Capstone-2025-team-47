############################################
# Remediation Lambda + EventBridge Rule
############################################

variable "user_pool_id" {
  description = "Cognito User Pool ID (있으면 Cognito 사용자 글로벌 로그아웃 수행)"
  type        = string
  default     = ""
}

variable "remediation_lambda_timeout" {
  type    = number
  default = 30
}

variable "remediation_lambda_memory" {
  type    = number
  default = 512
}

# --- Remediation Lambda용 IAM Role ---
resource "aws_iam_role" "remediation_role" {
  name = "ct-remediation-role${var.name_suffix}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })
}

# CloudWatch Logs 권한
resource "aws_iam_role_policy" "remediation_logs" {
  name = "ct-remediation-logs${var.name_suffix}"
  role = aws_iam_role.remediation_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect   = "Allow",
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      Resource = "*"
    }]
  })
}

# IAM & Cognito 제재 권한
# --- Remediation Lambda 코드(zip from directory) ---
data "archive_file" "remediation_zip" {
  type        = "zip"
  source_dir  = "${path.module}/remediation_lambda"
  output_path = "${path.module}/build/remediation.zip"
}

resource "aws_lambda_function" "remediation" {
  function_name    = "ct-remediation${var.name_suffix}"
  role             = aws_iam_role.remediation_role.arn
  runtime          = "python3.11"
  handler          = "index.handler"
  filename         = data.archive_file.remediation_zip.output_path
  source_code_hash = data.archive_file.remediation_zip.output_base64sha256
  timeout          = var.remediation_lambda_timeout
  memory_size      = var.remediation_lambda_memory
  architectures    = ["x86_64"]

  environment {
    variables = {
      USER_POOL_ID = var.user_pool_id
      # 필요 시 정책명도 충돌 방지를 위해 접미사 적용 가능:
      # QUARANTINE_POLICY_NAME = "QuarantineDenyAll${var.name_suffix}"
      QUARANTINE_POLICY_NAME = "QuarantineDenyAll"
    }
  }

  depends_on = [
    aws_iam_role_policy.remediation_logs
  ]
}

output "remediation_lambda_arn" {
  value = aws_lambda_function.remediation.arn
}

# --- EventBridge: 이상 탐지 이벤트 → Remediation Lambda ---
resource "aws_cloudwatch_event_rule" "anomaly" {
  name        = "ct-anomaly-detected${var.name_suffix}"
  description = "Disabled: remediation requires separately reviewed scoped-role design"
  state       = "DISABLED"
  event_pattern = jsonencode({
    "source" : ["ct.realtime"],
    "detail-type" : ["Security.AnomalyDetected"]
  })
}

resource "aws_cloudwatch_event_target" "anomaly_to_remediation" {
  rule      = aws_cloudwatch_event_rule.anomaly.name
  target_id = "remediation${var.name_suffix}"
  arn       = aws_lambda_function.remediation.arn
}

# EventBridge가 Lambda를 호출할 수 있게 허용
resource "aws_lambda_permission" "allow_events_to_invoke_remediation" {
  statement_id  = "AllowExecutionFromEventBridge${var.name_suffix}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.remediation.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.anomaly.arn
}

output "anomaly_rule_name" {
  value = aws_cloudwatch_event_rule.anomaly.name
}

# --- 실시간 Lambda에 PutEvents 권한 부여 ---
resource "aws_iam_role_policy" "lambda_realtime_events" {
  name = "ct-realtime-put-events${var.name_suffix}"
  role = aws_iam_role.lambda_realtime_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect   = "Allow",
      Action   = ["events:PutEvents"],
      Resource = "*"
    }]
  })
}
