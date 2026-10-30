output "user_event_table_arn" {
  value = aws_dynamodb_table.events_v2.arn
}

output "user_event_table_name" {
  value = aws_dynamodb_table.events_v2.name
}

output "trail_bucket_name" {
  value = aws_s3_bucket.trail_bucket.bucket
}

output "event_collector_lambda_name" {
  value = aws_lambda_function.event_collector.function_name
}

output "user_event_stream_arn" {
  value = aws_dynamodb_table.events_v2.stream_arn
}
