resource "aws_sfn_state_machine" "ct" {
  name     = "ct-pipeline-state-machine${var.name_suffix}" # ← 접미사 적용
  role_arn = aws_iam_role.sfn_role.arn

  definition = jsonencode({
    Comment        = "CloudTrail nightly pipeline"
    StartAt        = "CountItems"
    TimeoutSeconds = 10800
    States = {
      CountItems = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.count.arn
          "Payload.$"  = "$"
        }
        ResultSelector = {
          "count.$"     = "$.Payload.count"
          "date_path.$" = "$.Payload.date_path"
          "date_dash.$" = "$.Payload.date_dash"
        }
        ResultPath = "$.countResult"
        Next       = "CheckCount"
      }

      CheckCount = {
        Type = "Choice"
        Choices = [
          { Variable = "$.countResult.count", NumericLessThan = 3000, Next = "Done" }
        ]
        Default = "ExportDDB"
      }

      ExportDDB = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:dynamodb:exportTableToPointInTime"
        Parameters = {
          TableArn = var.ddb_table_arn
          # ↓ 버킷 이름에 fallback 적용
          S3Bucket       = "${local.bucket_name_effective}"
          "S3Prefix.$"   = "States.Format('raw/{}/{}', $.countResult.date_path, States.UUID())"
          S3SseAlgorithm = "AES256"
          ExportFormat   = "DYNAMODB_JSON"
        }
        ResultPath = "$.export"
        Next       = "InitExportPoll"
      }

      InitExportPoll = {
        Type       = "Pass"
        Parameters = { "attempts" : 0, "maxAttempts" : 60 }
        ResultPath = "$.exportPoll"
        Next       = "ExportWait"
      }

      ExportWait = { Type = "Wait", Seconds = 10, Next = "DescribeExport" }

      DescribeExport = {
        Type       = "Task"
        Resource   = "arn:aws:states:::aws-sdk:dynamodb:describeExport"
        Parameters = { "ExportArn.$" = "$.export.ExportDescription.ExportArn" }
        ResultPath = "$.exportDescribe"
        Next       = "CheckExportStatus"
      }

      CheckExportStatus = {
        Type = "Choice"
        Choices = [
          { Variable : "$.exportDescribe.ExportDescription.ExportStatus", StringEquals : "COMPLETED", Next : "MakeJobName" },
          { Variable : "$.exportDescribe.ExportDescription.ExportStatus", StringEquals : "FAILED", Next : "FailProcessing" },
          { Variable : "$.exportDescribe.ExportDescription.ExportStatus", StringEquals : "CANCELED", Next : "FailProcessing" }
        ]
        Default = "HasDataOrContinue"
      }

      HasDataOrContinue = {
        Type = "Choice"
        Choices = [
          { Variable : "$.exportPoll.attempts", NumericGreaterThanEqualsPath : "$.exportPoll.maxAttempts", Next : "ExportTimeoutFail" }
        ]
        Default = "IncPoll"
      }

      IncPoll = {
        Type = "Pass"
        Parameters = {
          "attempts.$" : "States.MathAdd($.exportPoll.attempts, 1)"
          "maxAttempts.$" : "$.exportPoll.maxAttempts"
        }
        ResultPath = "$.exportPoll"
        Next       = "ExportWait"
      }

      ExportTimeoutFail = { Type : "Fail", Error : "ExportTimeout", Cause : "DynamoDB Export did not produce S3 objects within the allowed time window." }

      MakeJobName = {
        Type       = "Pass"
        Parameters = { "jobName.$" : "States.Format('ct-{}-{}', $.countResult.date_dash, States.UUID())" }
        ResultPath = "$.job"
        Next       = "ProcessingJob"
      }

      ProcessingJob = {
        Type     = "Task"
        Resource = "arn:aws:states:::sagemaker:createProcessingJob"
        Parameters = {
          "ProcessingJobName.$" = "$.job.jobName"
          AppSpecification      = { ImageUri = var.processing_image_uri }
          RoleArn               = aws_iam_role.sagemaker_processing_role.arn
          StoppingCondition     = { MaxRuntimeInSeconds = 7200 }

          ProcessingInputs = [
            {
              InputName = "raw"
              S3Input = {
                "S3Uri.$"   = "States.Format('s3://{}/{}', $.exportDescribe.ExportDescription.S3Bucket, $.exportDescribe.ExportDescription.S3Prefix)"
                LocalPath   = "/opt/ml/processing/input"
                S3DataType  = "S3Prefix"
                S3InputMode = "File"
              }
            }
          ]

          ProcessingOutputConfig = {
            Outputs = [
              {
                OutputName = "models"
                S3Output = {
                  S3Uri        = "s3://${local.bucket_name_effective}/models/" # ← fallback 적용
                  LocalPath    = "/opt/ml/processing/models"
                  S3UploadMode = "EndOfJob"
                }
              },
              {
                OutputName = "results"
                S3Output = {
                  S3Uri        = "s3://${local.bucket_name_effective}/results/" # ← fallback 적용
                  LocalPath    = "/opt/ml/processing/results"
                  S3UploadMode = "EndOfJob"
                }
              }
            ]
          }

          Environment = {
            BUCKET            = "${local.bucket_name_effective}" # ← fallback 적용
            "DATE.$"          = "$.countResult.date_path"
            "MODEL_VERSION.$" = "$.job.jobName"
            PYTHONHASHSEED    = "0"

            EVENT_TIME_FIELD = "timestamp"
            EVENT_NAME_FIELD = "eventName"

            GAP_MINUTES        = tostring(var.gap_minutes)
            WIN_DOC2VEC        = tostring(var.win_doc2vec)
            STRIDE_DOC2VEC     = tostring(var.stride_doc2vec)
            VEC_SIZE           = tostring(var.doc2vec_vec_size)
            WIN_SEG            = tostring(var.win_seg)
            STRIDE_SEG         = tostring(var.stride_seg)
            MAX_SEQ_PER_SEG    = tostring(var.max_seq_per_seg)
            OCSVM_NU           = tostring(var.ocsvm_nu)
            DBSCAN_MIN_SAMPLES = tostring(var.dbscan_min_samples)
            DBSCAN_EPS_PCTL    = tostring(var.dbscan_eps_percentile)
            DBSCAN_K           = tostring(var.dbscan_k_neighbors)
          }

          ProcessingResources = {
            ClusterConfig = {
              InstanceCount  = 1
              InstanceType   = var.processing_instance_type
              VolumeSizeInGB = var.processing_volume_gb
            }
          }
        }
        ResultPath = "$.proc"
        Next       = "WaitBeforeDescribe"
        Catch = [
          { "ErrorEquals" : ["SageMaker.AmazonSageMakerException", "States.TaskFailed"], "ResultPath" : "$.processingError", "Next" : "FailProcessing" }
        ]
      }

      WaitBeforeDescribe = { Type : "Wait", Seconds : 10, Next : "DescribeProcessingJob" }

      DescribeProcessingJob = {
        Type       = "Task"
        Resource   = "arn:aws:states:::aws-sdk:sagemaker:describeProcessingJob"
        Parameters = { "ProcessingJobName.$" = "$.job.jobName" }
        ResultPath = "$.describeResult"
        Next       = "CheckProcessingStatus"
      }

      CheckProcessingStatus = {
        Type = "Choice"
        Choices = [
          { Variable : "$.describeResult.ProcessingJobStatus", StringEquals : "Completed", Next : "Summarize" },
          { Variable : "$.describeResult.ProcessingJobStatus", StringEquals : "Failed", Next : "FailProcessing" },
          { Variable : "$.describeResult.ProcessingJobStatus", StringEquals : "Stopped", Next : "FailProcessing" }
        ]
        Default = "WaitBeforeDescribe"
      }

      Summarize = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.summarize.arn
          "Payload.$"  = "$"
        }
        ResultPath = "$.summarizeResult"
        Next       = "Done"
      }

      FailProcessing = { Type : "Fail", Error : "ProcessingJobFailed", Cause : "SageMaker Processing job did not complete successfully." }
      Done           = { Type : "Succeed" }
    }
  })
}
