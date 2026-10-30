variable "monitored_username" {
  type        = string
  description = "IAM username to monitor; explicit, independent of Terraform actor"
}
variable "retention_days" {
  type    = number
  default = 90
  validation {
    condition     = var.retention_days >= 90 && var.retention_days <= 365
    error_message = "Keep 90-365 days to cover training/replay; archive is retained 365 days."
  }
}
# Additive v2 table: never replace the legacy timestamp-keyed table in-place.
resource "aws_dynamodb_table" "events_v2" {
  name         = "UserEventBufferV2_${local.sanitized_username_common}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
  point_in_time_recovery { enabled = true }
  stream_enabled              = true
  stream_view_type            = "NEW_IMAGE"
  deletion_protection_enabled = true
  lifecycle { prevent_destroy = true }
}
# Archive_file includes only canonical collector + shared package, built by tools/package_collector.py.
data "archive_file" "collector" {
  type        = "zip"
  source_dir  = "${path.root}/.build/collector"
  output_path = "${path.root}/.build/event_collector.zip"
}
resource "aws_s3_bucket" "failures" {
  bucket = "ueba-failures-${data.aws_caller_identity.current.account_id}-${local.sanitized_username_s3}"
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_public_access_block" "failures" {
  bucket                  = aws_s3_bucket.failures.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "failures" {
  bucket = aws_s3_bucket.failures.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_lifecycle_configuration" "failures" {
  bucket = aws_s3_bucket.failures.id
  rule {
    id     = "failure-retention"
    status = "Enabled"
    filter {}
    expiration { days = 365 }
    noncurrent_version_expiration { noncurrent_days = 365 }
  }
}
resource "aws_sqs_queue" "delivery_failures" {
  name                      = "ueba-eventbridge-delivery-${local.sanitized_username_dash}"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_sqs_queue" "execution_failures" {
  name                      = "ueba-lambda-execution-${local.sanitized_username_dash}"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_sqs_queue_policy" "delivery_failures" {
  queue_url = aws_sqs_queue.delivery_failures.url
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage",
    Resource  = aws_sqs_queue.delivery_failures.arn,
    Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.cloudtrail_events.arn } }
  }] })
}
resource "aws_iam_role_policy" "collector_failures" {
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.failures.arn}/invalid/*" },
    { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.execution_failures.arn }
  ] })
}
resource "aws_lambda_function_event_invoke_config" "collector" {
  function_name                = aws_lambda_function.event_collector.function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 21600
  destination_config {
    on_failure { destination = aws_sqs_queue.execution_failures.arn }
  }
  depends_on = [aws_iam_role_policy.collector_failures]
}
output "delivery_failure_queue" { value = aws_sqs_queue.delivery_failures.url }
output "execution_failure_queue" { value = aws_sqs_queue.execution_failures.url }
output "invalid_archive_bucket" { value = aws_s3_bucket.failures.id }
