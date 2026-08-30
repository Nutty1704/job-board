resource "aws_cognito_user_pool" "dashboard" {
  name                     = "${local.name_prefix}-dashboard"
  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]
}

resource "aws_cognito_user_pool_client" "dashboard" {
  name                          = "${local.name_prefix}-dashboard"
  user_pool_id                  = aws_cognito_user_pool.dashboard.id
  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_PASSWORD_AUTH"]
  prevent_user_existence_errors = "ENABLED"
}

resource "aws_cloudwatch_log_group" "dashboard_api" {
  name              = "/aws/lambda/${local.name_prefix}-dashboard-api"
  retention_in_days = 7
}

resource "aws_lambda_function" "dashboard_api" {
  function_name     = "${local.name_prefix}-dashboard-api"
  role              = aws_iam_role.dashboard_api.arn
  runtime           = "nodejs20.x"
  handler           = "index.handler"
  timeout           = 15
  memory_size       = 256
  s3_bucket         = var.dashboard_lambda_s3_bucket
  s3_key            = var.dashboard_lambda_s3_key
  s3_object_version = var.dashboard_lambda_s3_object_version

  environment {
    variables = {
      JOB_MATCHES_TABLE   = aws_dynamodb_table.job_matches.name
      PROJECT_DATA_BUCKET = aws_s3_bucket.project_data.bucket
    }
  }
}

resource "aws_apigatewayv2_api" "dashboard" {
  name          = "${local.name_prefix}-dashboard"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_authorizer" "dashboard" {
  api_id           = aws_apigatewayv2_api.dashboard.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.dashboard.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.dashboard.id}"
  }
}

resource "aws_apigatewayv2_integration" "dashboard" {
  api_id                 = aws_apigatewayv2_api.dashboard.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.dashboard_api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "dashboard" {
  api_id             = aws_apigatewayv2_api.dashboard.id
  route_key          = "GET /jobs/{proxy+}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.dashboard.id
  target             = "integrations/${aws_apigatewayv2_integration.dashboard.id}"
}

resource "aws_apigatewayv2_route" "dashboard_list" {
  api_id             = aws_apigatewayv2_api.dashboard.id
  route_key          = "GET /jobs"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.dashboard.id
  target             = "integrations/${aws_apigatewayv2_integration.dashboard.id}"
}

resource "aws_apigatewayv2_stage" "dashboard" {
  api_id      = aws_apigatewayv2_api.dashboard.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "dashboard" {
  statement_id  = "AllowApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dashboard_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.dashboard.execution_arn}/*/*"
}
