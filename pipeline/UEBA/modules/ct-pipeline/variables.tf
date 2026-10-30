# 접미사(이름류: ECR/IAM/Lambda/StepFunctions/EventBridge/DynamoDB 등)
variable "name_suffix" {
  type        = string
  description = "Suffix for resource names (letters/numbers/dash only). Example: -john-doe"
  default     = ""

  validation {
    condition     = var.name_suffix == "" || can(regex("^-?[A-Za-z0-9-]*$", var.name_suffix))
    error_message = "name_suffix must use only letters, numbers, and dashes (e.g., -john-doe)."
  }
}

# S3 버킷용 안전 접미사(소문자/숫자/.-)
variable "bucket_suffix" {
  type        = string
  description = "Lowercase-safe suffix for S3 buckets (lowercase letters, numbers, dot, dash). Example: u1a2b3c4-123456789012"
  default     = ""

  validation {
    condition     = var.bucket_suffix == "" || can(regex("^[a-z0-9.-]+$", var.bucket_suffix))
    error_message = "bucket_suffix must contain only lowercase letters, numbers, dots, and dashes."
  }
}

# CloudTrail 이벤트를 저장하는 DynamoDB 테이블 ARN (필수)
variable "ddb_table_arn" {
  description = "ARN of the DynamoDB table storing CloudTrail events"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:dynamodb:[a-z0-9-]+:\\d{12}:table\\/.+", var.ddb_table_arn))
    error_message = "ddb_table_arn must be a valid DynamoDB table ARN (arn:aws:dynamodb:region:account-id:table/NAME)."
  }
}

# 파이프라인 이미지용 ECR 레포지토리 이름(기본값 제공)
variable "ecr_repo_name" {
  description = "Name of the ECR repository to create for the pipeline image"
  type        = string
  default     = "ct-pipeline"

  validation {
    # ECR repo name 규칙: 소문자/숫자/._/-/슬래시 허용
    condition     = can(regex("^[a-z0-9._/-]+$", var.ecr_repo_name))
    error_message = "ecr_repo_name must contain only lowercase letters, numbers, dot, underscore, dash, or slash."
  }
}

# 결과 인덱스용 DynamoDB 테이블 이름(모듈에서 name_suffix 붙여 최종 생성)
variable "results_table_name" {
  description = "DynamoDB table name for results index (created by this module)"
  type        = string
  default     = "ct-results-index"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+$", var.results_table_name))
    error_message = "results_table_name must contain only letters, numbers, underscore, dot, and dash."
  }
}

# SageMaker Processing 설정
variable "processing_instance_type" {
  description = "Instance type for SageMaker Processing"
  type        = string
  default     = "ml.m5.xlarge"
}

variable "processing_volume_gb" {
  description = "EBS volume size for SageMaker Processing (GB)"
  type        = number
  default     = 50
}

# 파이프라인 파라미터
variable "doc2vec_vec_size" {
  type    = number
  default = 64
}

variable "gap_minutes" {
  type    = number
  default = 30
}

variable "win_doc2vec" {
  type    = number
  default = 20
}

variable "stride_doc2vec" {
  type    = number
  default = 1
}

variable "win_seg" {
  type    = number
  default = 20
}

variable "stride_seg" {
  type    = number
  default = 5
}

variable "max_seq_per_seg" {
  type    = number
  default = 5
}

variable "ocsvm_nu" {
  type    = number
  default = 0.05
}

variable "dbscan_min_samples" {
  type    = number
  default = 10
}

variable "dbscan_eps_percentile" {
  type    = number
  default = 90
}

variable "dbscan_k_neighbors" {
  type    = number
  default = 10
}

variable "model_version" { type = string }
variable "realtime_image_uri" { type = string }
variable "processing_image_uri" { type = string }
