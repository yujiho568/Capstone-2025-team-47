# KST 00:00 = 15:00 UTC previous day
resource "aws_cloudwatch_event_rule" "midnight_kst" {
  name                = "ct-midnight-kst${var.name_suffix}"
  schedule_expression = "cron(0 15 * * ? *)"
}

resource "aws_cloudwatch_event_target" "sfn_target" {
  rule      = aws_cloudwatch_event_rule.midnight_kst.name
  target_id = "ct-pipeline-sfn${var.name_suffix}" # ← 같은 Rule 내에서 unique 해야 하므로 접미사 권장
  arn       = aws_sfn_state_machine.ct.arn
  role_arn  = aws_iam_role.events_to_sfn_role.arn
}
