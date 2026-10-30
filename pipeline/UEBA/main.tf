# (기존) caller, name_suffix/bucket_suffix locals 유지
data "aws_caller_identity" "current" {}

locals {
  # AWS 계정 주체 ARN (예: arn:aws:iam::123456789012:user/alice 또는 ...:role/xyz)
  raw_arn = data.aws_caller_identity.current.arn

  # user/인 경우 캡처 그룹(사용자명), 아니면 마지막 슬래시 뒤 토큰(role 이름 등)
  caller_username = var.monitored_username

  name_suffix   = "-${replace(local.caller_username, "/[^a-zA-Z0-9-]/", "-")}"
  bucket_suffix = lower(replace("u${substr(md5(local.caller_username), 0, 8)}", "/[^a-z0-9.-]/", "-"))
}

# 1) Ingest(CloudTrail 수집) 모듈
module "ct_ingest" {
  source             = "./modules/ct-ingest"
  monitored_username = var.monitored_username
  # 이 모듈은 변수 없이 locals로 이름을 정하므로 추가 인자는 필요 없음
  # (필요 시 변수 받을 수 있게 바꾸면 여기에 전달)
}

# 2) Pipeline 모듈 — Ingest 출력값을 연결
module "ct_pipeline" {
  source = "./modules/ct-pipeline"

  name_suffix   = local.name_suffix
  bucket_suffix = local.bucket_suffix
  # ★ ingest가 만든 테이블 ARN을 주입
  ddb_table_arn    = module.ct_ingest.user_event_table_arn
  event_table_name = module.ct_ingest.user_event_table_name

  processing_instance_type = "ml.m5.xlarge"
  processing_volume_gb     = 30
  model_version            = var.model_version
  realtime_image_uri       = var.realtime_image_uri
  processing_image_uri     = var.processing_image_uri
}

variable "monitored_username" { type = string }
variable "model_version" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{1,100}$", var.model_version))
    error_message = "Use a unique immutable model bundle version."
  }
}
variable "realtime_image_uri" { type = string }
variable "processing_image_uri" { type = string }
