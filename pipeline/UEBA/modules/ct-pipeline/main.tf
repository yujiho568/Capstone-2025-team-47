# 접미사 반영/버킷 이름 fallback용 로컬 변수 (파일 상단에 추가 권장)
locals {
  results_table_name_effective = "${var.results_table_name}${var.name_suffix}"
  bucket_name_effective        = "ct-pipeline-bucket-${var.bucket_suffix}"
}

# Results index DynamoDB table (pk, sk)
resource "aws_dynamodb_table" "results" {
  name         = local.results_table_name_effective
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
}

# S3 bucket to store raw/models/results
resource "aws_s3_bucket" "ct" {
  bucket        = local.bucket_name_effective
  force_destroy = false
  lifecycle { prevent_destroy = true }
}

resource "aws_s3_bucket_versioning" "ct" {
  bucket = aws_s3_bucket.ct.id
  versioning_configuration { status = "Enabled" }
}
