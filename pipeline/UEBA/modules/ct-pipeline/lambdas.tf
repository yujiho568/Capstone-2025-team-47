locals {
  lambda_build_dir = "${path.module}/.build"
}

# Package ct-count
data "archive_file" "ct_count_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/ct-count"
  output_path = "${local.lambda_build_dir}/ct-count.zip"
}

resource "aws_lambda_function" "count" {
  function_name    = "ct-count${var.name_suffix}" # ← 접미사 적용
  description      = "Counts DynamoDB items and computes KST date"
  role             = aws_iam_role.lambda_count_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = data.archive_file.ct_count_zip.output_path
  source_code_hash = data.archive_file.ct_count_zip.output_base64sha256
  timeout          = 60

  environment {
    variables = {
      TABLE_NAME = split("/", var.ddb_table_arn)[length(split("/", var.ddb_table_arn)) - 1]
    }
  }
}

# Package ct-summarize
data "archive_file" "ct_summarize_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/ct-summarize"
  output_path = "${local.lambda_build_dir}/ct-summarize.zip"
}

resource "aws_lambda_function" "summarize" {
  function_name    = "ct-summarize${var.name_suffix}" # ← 접미사 적용
  description      = "Reads stats.json and upserts DynamoDB results index"
  role             = aws_iam_role.lambda_summarize_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = data.archive_file.ct_summarize_zip.output_path
  source_code_hash = data.archive_file.ct_summarize_zip.output_base64sha256
  timeout          = 60

  environment {
    variables = {
      BUCKET        = local.bucket_name_effective
      RESULTS_TABLE = "${var.results_table_name}${var.name_suffix}" # 결과 테이블도 접미사와 일치
    }
  }
}
