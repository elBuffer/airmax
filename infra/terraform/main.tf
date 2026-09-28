terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.expected_account_id]
}

locals {
  # One workspace per stage keeps each stage in its own state file.
  stage  = terraform.workspace
  prefix = "${var.owner_name}-airmax-${local.stage}"

  # Production switches change only through a reviewed commit, never a command-line flag.
  ingestion_enabled = true
  schedule_enabled  = true
}

data "aws_iam_role" "lambda" {
  name = "lambda-execution-role"

  lifecycle {
    precondition {
      condition     = contains(["dev", "qa", "prd"], local.stage)
      error_message = "Select a stage workspace first: terraform workspace select -or-create=true dev|qa|prd"
    }
  }
}

resource "aws_s3_bucket" "raw" {
  bucket        = "${local.prefix}-raw"
  force_destroy = local.stage != "prd"
}

resource "aws_s3_bucket" "results" {
  bucket        = "${local.prefix}-results"
  force_destroy = local.stage != "prd"
}

resource "aws_s3_bucket_public_access_block" "buckets" {
  for_each = { raw = aws_s3_bucket.raw.id, results = aws_s3_bucket.results.id }
  bucket   = each.value

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_sqs_queue" "production_ingestion" {
  count = local.stage == "prd" ? 1 : 0
  name  = var.production_queue_name
}

resource "aws_sqs_queue" "ingestion" {
  count                      = local.stage == "prd" ? 0 : 1
  name                       = "${local.prefix}-ingestion"
  visibility_timeout_seconds = 180
}

locals {
  ingestion_queue_arn = local.stage == "prd" ? data.aws_sqs_queue.production_ingestion[0].arn : aws_sqs_queue.ingestion[0].arn
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = toset(["ingestion", "transformation", "website"])
  name              = "/aws/lambda/${local.prefix}-${each.key}"
  retention_in_days = local.stage == "prd" ? 14 : 1
}

resource "aws_lambda_function" "ingestion" {
  function_name    = "${local.prefix}-ingestion"
  role             = data.aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "airmax_ingestion.handler.lambda_handler"
  filename         = "${path.module}/ingestion.zip"
  source_code_hash = filebase64sha256("${path.module}/ingestion.zip")
  timeout          = local.stage == "prd" ? 25 : 120
  depends_on       = [aws_cloudwatch_log_group.lambda["ingestion"]]

  environment {
    variables = {
      AIRMAX_STORE      = "s3"
      AIRMAX_RAW_BUCKET = aws_s3_bucket.raw.id
    }
  }
}

resource "aws_lambda_event_source_mapping" "ingestion" {
  count                              = local.stage == "prd" ? 1 : 0
  event_source_arn                   = local.ingestion_queue_arn
  function_name                      = aws_lambda_function.ingestion.arn
  batch_size                         = 100
  maximum_batching_window_in_seconds = 5
  enabled                            = local.ingestion_enabled

  scaling_config {
    maximum_concurrency = 2
  }
}

resource "aws_lambda_function" "transformation" {
  function_name    = "${local.prefix}-transformation"
  role             = data.aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "airmax_transformation.handler.lambda_handler"
  filename         = "${path.module}/transformation.zip"
  source_code_hash = filebase64sha256("${path.module}/transformation.zip")
  memory_size      = 1024
  timeout          = 300
  ephemeral_storage { size = 1024 }
  depends_on = [aws_cloudwatch_log_group.lambda["transformation"]]

  environment {
    variables = {
      AIRMAX_STORE          = "s3"
      AIRMAX_RAW_BUCKET     = aws_s3_bucket.raw.id
      AIRMAX_RESULTS_BUCKET = aws_s3_bucket.results.id
    }
  }
}

resource "aws_cloudwatch_event_rule" "transformation" {
  count               = local.stage == "prd" ? 1 : 0
  name                = "${local.prefix}-transformation"
  schedule_expression = "rate(5 minutes)"
  state               = local.schedule_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "transformation" {
  count = local.stage == "prd" ? 1 : 0
  rule  = aws_cloudwatch_event_rule.transformation[0].name
  arn   = aws_lambda_function.transformation.arn
}

resource "aws_lambda_permission" "eventbridge" {
  count         = local.stage == "prd" ? 1 : 0
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.transformation.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.transformation[0].arn
}

resource "aws_lambda_function" "website" {
  function_name    = "${local.prefix}-website"
  role             = data.aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "airmax_website.handler.lambda_handler"
  filename         = "${path.module}/website.zip"
  source_code_hash = filebase64sha256("${path.module}/website.zip")
  timeout          = 10
  depends_on       = [aws_cloudwatch_log_group.lambda["website"]]

  environment {
    variables = {
      AIRMAX_STORE          = "s3"
      AIRMAX_RESULTS_BUCKET = aws_s3_bucket.results.id
    }
  }
}

resource "aws_lambda_function_url" "website" {
  function_name      = aws_lambda_function.website.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "public_url" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.website.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "public_url_invoke" {
  statement_id             = "AllowPublicFunctionUrlInvoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.website.function_name
  principal                = "*"
  invoked_via_function_url = true
}

output "website_url" {
  value = aws_lambda_function_url.website.function_url
}
