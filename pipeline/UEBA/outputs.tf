output "state_machine_arn" { value = module.ct_pipeline.state_machine_arn }
output "event_rule_name" { value = module.ct_pipeline.event_rule_name }
output "bucket_name" { value = module.ct_pipeline.bucket_name }
output "results_table_name" { value = module.ct_pipeline.results_table_name }
output "lambda_count_arn" { value = module.ct_pipeline.lambda_count_arn }
output "lambda_summary_arn" { value = module.ct_pipeline.lambda_summary_arn }
output "sagemaker_role_arn" { value = module.ct_pipeline.sagemaker_role_arn }
output "ecr_repository_url" { value = module.ct_pipeline.ecr_repository_url }
