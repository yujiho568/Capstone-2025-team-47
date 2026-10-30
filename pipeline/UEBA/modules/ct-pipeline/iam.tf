# (중복 제거) 여기서는 aws_region data 선언하지 않습니다. main.tf 쪽 선언을 사용합니다.

# Lambda execution roles
resource "aws_iam_role" "lambda_count_role" {
  name               = "ct-count-role${var.name_suffix}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role" "lambda_summarize_role" {
  name               = "ct-summarize-role${var.name_suffix}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# 기존 aws_iam_role_policy.lambda_count_policy 삭제하고 아래 두 블록 추가

data "aws_iam_policy_document" "lambda_count" {
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:Scan"]
    resources = [var.ddb_table_arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_count_policy" {
  name   = "ct-count-policy${var.name_suffix}"
  role   = aws_iam_role.lambda_count_role.id
  policy = data.aws_iam_policy_document.lambda_count.json
}

resource "aws_iam_role_policy" "lambda_summarize_policy" {
  name = "ct-summarize-policy${var.name_suffix}"
  role = aws_iam_role.lambda_summarize_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [

      { Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:GetItem"], Resource = aws_dynamodb_table.results.arn },
      { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], Resource = "*" }
    ]
  })
}

# Lambda summarize -> S3 results/* 읽기
resource "aws_iam_role_policy" "lambda_summarize_s3_read" {
  name = "ct-summarize-s3-read${var.name_suffix}"
  role = aws_iam_role.lambda_summarize_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect : "Allow",
        Action : ["s3:ListBucket"],
        Resource : "arn:aws:s3:::${local.bucket_name_effective}",
        Condition : {
          StringLike : { "s3:prefix" : ["results/*"] }
        }
      },
      {
        Effect : "Allow",
        Action : ["s3:GetObject", "s3:GetObjectVersion"],
        Resource : "arn:aws:s3:::${local.bucket_name_effective}/results/*"
      }
    ]
  })
}

# SageMaker Processing execution role
resource "aws_iam_role" "sagemaker_processing_role" {
  name               = "ct-sagemaker-processing-role${var.name_suffix}"
  assume_role_policy = data.aws_iam_policy_document.sagemaker_assume.json
}

data "aws_iam_policy_document" "sagemaker_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "sagemaker_processing_policy" {
  name = "ct-sagemaker-processing-policy${var.name_suffix}"
  role = aws_iam_role.sagemaker_processing_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      { Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = "arn:aws:s3:::${local.bucket_name_effective}" },
      { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], Resource = "*" }
    ]
  })
}

# Step Functions role to orchestrate everything
resource "aws_iam_role" "sfn_role" {
  name               = "ct-sfn-role${var.name_suffix}"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

# 기존 aws_iam_role_policy.sfn_policy 삭제하고 아래 두 블록 추가

data "aws_iam_policy_document" "sfn" {
  # Lambda invoke
  statement {
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.count.arn,
      aws_lambda_function.summarize.arn
    ]
  }

  # DynamoDB Export
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:ExportTableToPointInTime", "dynamodb:DescribeExport"]
    resources = [var.ddb_table_arn]
  }

  # S3 List (bucket ARN)
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${local.bucket_name_effective}"]
  }

  # S3 Get/Put (object ARN)
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:PutObjectAcl", "s3:AbortMultipartUpload"]
    resources = ["arn:aws:s3:::${local.bucket_name_effective}/raw/*"]
  }

  # SageMaker Processing
  statement {
    effect = "Allow"
    actions = [
      "sagemaker:CreateProcessingJob",
      "sagemaker:DescribeProcessingJob",
      "sagemaker:StopProcessingJob"
    ]
    resources = ["*"]
  }

  # Pass SageMaker role
  statement {
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.sagemaker_processing_role.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["sagemaker.amazonaws.com"]
    }
  }

  # Logs
  statement {
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn_policy" {
  name   = "ct-sfn-policy${var.name_suffix}"
  role   = aws_iam_role.sfn_role.id
  policy = data.aws_iam_policy_document.sfn.json
}

# EventBridge -> Step Functions permission
resource "aws_iam_role" "events_to_sfn_role" {
  name = "ct-events-to-sfn-role${var.name_suffix}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "events.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "events_to_sfn_policy" {
  name = "ct-events-to-sfn-policy${var.name_suffix}"
  role = aws_iam_role.events_to_sfn_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect   = "Allow",
      Action   = ["states:StartExecution"],
      Resource = aws_sfn_state_machine.ct.arn
    }]
  })
}

# SageMaker 실행 역할에 ECR pull 권한 부여
resource "aws_iam_role_policy" "sagemaker_ecr_pull" {
  name = "ct-sagemaker-ecr-pull${var.name_suffix}"
  role = aws_iam_role.sagemaker_processing_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # 토큰은 계정/리전 상관없이 리소스 * 로 줍니다.
      {
        Effect : "Allow",
        Action : ["ecr:GetAuthorizationToken"],
        Resource : "*"
      },
      # 이미지/레이어 관련 권한은 해당 리포지토리 ARN 참조
      {
        Effect : "Allow",
        Action : [
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:DescribeRepositories"
        ],
        Resource : aws_ecr_repository.pipeline.arn
      }
    ]
  })
}

# SageMaker Processing 역할의 S3 접근 (입력은 raw/ 읽기, 출력은 models/, results/ 쓰기)
resource "aws_iam_role_policy" "sagemaker_s3_access" {
  name = "ct-sagemaker-s3-access${var.name_suffix}"
  role = aws_iam_role.sagemaker_processing_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # 버킷 리스트 권한 (prefix 제한)
      {
        Effect : "Allow",
        Action : ["s3:ListBucket"],
        Resource : "arn:aws:s3:::${local.bucket_name_effective}",
        Condition : {
          StringLike : {
            "s3:prefix" : [
              "raw/*",
              "models/*",
              "results/*"
            ]
          }
        }
      },
      # 입력(raw) 읽기
      {
        Effect : "Allow",
        Action : ["s3:GetObject", "s3:GetObjectVersion"],
        Resource : "arn:aws:s3:::${local.bucket_name_effective}/raw/*"
      },
      # 출력(models, results) 쓰기
      {
        Effect : "Allow",
        Action : ["s3:PutObject", "s3:AbortMultipartUpload"],
        Resource : [
          "arn:aws:s3:::${local.bucket_name_effective}/models/*",
          "arn:aws:s3:::${local.bucket_name_effective}/results/*"
        ]
      }
    ]
  })
}

# Step Functions 가 DynamoDB Export 상태를 조회할 수 있도록 권한 부여
resource "aws_iam_role_policy" "sfn_ddb_exports" {
  name = "ct-sfn-ddb-exports${var.name_suffix}"
  role = aws_iam_role.sfn_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # Export 생성(이미 있을 수도 있음)
      {
        Effect : "Allow",
        Action : [
          "dynamodb:ExportTableToPointInTime"
        ],
        Resource : [
          var.ddb_table_arn
        ]
      },
      # Export 상태 조회 (DescribeExport) — export ARN 패턴까지 허용
      {
        Effect : "Allow",
        Action : [
          "dynamodb:DescribeExport"
        ],
        Resource : [
          "${var.ddb_table_arn}/export/*"
        ]
      }
    ]
  })
}
