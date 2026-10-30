output "state_machine_arn" {
  value = aws_sfn_state_machine.ct.arn
}

output "event_rule_name" {
  value = aws_cloudwatch_event_rule.midnight_kst.name
}

output "bucket_name" {
  # local.bucket_name_effective이 비어 있으면 fallback 이름이 실제 리소스에 적용됨
  value = aws_s3_bucket.ct.bucket
}

output "results_table_name" {
  value = aws_dynamodb_table.results.name
}

output "lambda_count_arn" {
  value = aws_lambda_function.count.arn
}

output "lambda_summary_arn" {
  value = aws_lambda_function.summarize.arn
}

output "sagemaker_role_arn" {
  value = aws_iam_role.sagemaker_processing_role.arn
}

output "ecr_repository_url" {
  value = aws_ecr_repository.pipeline.repository_url
}
