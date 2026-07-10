/*
infra/iam.tf

IAM role + policies for BloodhoundLambdaV2.

Intent:
- allow scanning (Describe APIs) + Cost Explorer reads
- allow teardown actions (terminate/delete) when enabled by env flags
- allow lambda self-invoke for slash commands (async worker invocation)
*/

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_role" {
  name               = "${local.name_prefix}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "basic_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "bloodhound" {
  # Read scanning permissions
  statement {
    actions = [
      "ec2:Describe*",
      "rds:Describe*",
      "rds:ListTagsForResource",
      "elasticloadbalancing:Describe*",
      "ce:GetCostAndUsage",
      "ssm:GetParameter"
    ]
    resources = ["*"]
  }

  # Spending-controls / guardrails proof (budgets, SCPs, IAM principals).
  statement {
    actions = [
      "sts:GetCallerIdentity",
      "budgets:DescribeBudgets",
      "budgets:ViewBudget",
      "budgets:DescribeBudgetActionsForAccount",
      "budgets:DescribeBudgetActionsForBudget",
      "budgets:DescribeBudgetAction",
      "organizations:DescribePolicy",
      "organizations:DescribeOrganizationalUnit",
      "organizations:DescribeAccount",
      "iam:ListGroups",
      "iam:ListUsers"
    ]
    resources = ["*"]
  }

  # Cost-guard management ("/guard" command): edit the SCP + the IAM group policy in
  # sync, and manage group membership. Powerful — paired with Slack allowlist gating
  # (GUARD_ALLOWED_USER_IDS) and a toggleable-service safelist in the app layer.
  statement {
    actions = [
      "organizations:ListPolicies",
      "organizations:UpdatePolicy",
      "organizations:ListTargetsForPolicy",
      "organizations:AttachPolicy",
      "organizations:DetachPolicy",
      "iam:ListPolicies",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicyVersions",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicyVersion",
      "iam:ListAttachedGroupPolicies",
      "iam:AttachGroupPolicy",
      "iam:DetachGroupPolicy",
      "iam:GetGroup",
      "iam:AddUserToGroup",
      "iam:RemoveUserFromGroup"
    ]
    resources = ["*"]
  }

  # Teardown permissions (delete/terminate)
  statement {
    actions = [
      "ec2:TerminateInstances",
      "ec2:DeleteVolume",
      "ec2:ReleaseAddress",
      "ec2:DeleteNatGateway",
      "rds:DeleteDBInstance",
      "elasticloadbalancing:DeleteLoadBalancer"
    ]
    resources = ["*"]
  }

  # Allow async self-invoke for slash commands.
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "bloodhound_policy" {
  name   = "${local.name_prefix}-policy"
  policy = data.aws_iam_policy_document.bloodhound.json
}

resource "aws_iam_role_policy_attachment" "bloodhound_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.bloodhound_policy.arn
}


