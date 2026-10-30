# S3 failure destination preserves complete Streams invocation payload, unlike SQS
# stream failure metadata. Regional/provider support must be confirmed before deploy.
resource "aws_s3_bucket" "stream_failures" {
  bucket = "${local.bucket_name_effective}-stream-failures"
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_public_access_block" "stream_failures" {
  bucket                  = aws_s3_bucket.stream_failures.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "stream_failures" {
  bucket = aws_s3_bucket.stream_failures.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_lifecycle_configuration" "stream_failures" {
  bucket = aws_s3_bucket.stream_failures.id
  rule {
    id     = "replay-window"
    status = "Enabled"
    filter {}
    expiration { days = 365 }
    noncurrent_version_expiration { noncurrent_days = 365 }
  }
}
resource "aws_iam_role_policy" "stream_failure_archive" {
  role = aws_iam_role.lambda_realtime_role.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.stream_failures.arn}/*" },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.stream_failures.arn }
  ] })
}
resource "aws_ecr_repository_policy" "lambda_pull" {
  repository = aws_ecr_repository.realtime.name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid       = "LambdaImageRetrieval", Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" },
    Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
    Condition = { ArnLike = { "aws:SourceArn" = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:ct-realtime-infer${var.name_suffix}" } }
  }] })
}
