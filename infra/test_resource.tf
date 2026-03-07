# ------------------------------------------------------------
# Bloodhound Teardown Validation Resource
#
# This Terraform resource defines a temporary EC2 instance used
# exclusively for validating Bloodhound's teardown pipeline.
# ------------------------------------------------------------


# ------------------------------------------------------------
# Lookup Latest Amazon Linux 2 AMI
#
# Hardcoding AMI IDs eventually breaks because AWS retires
# images over time. Instead Terraform dynamically retrieves
# the newest Amazon Linux 2 image published by AWS.
# ------------------------------------------------------------
data "aws_ami" "amazon_linux_2" {

  most_recent = true

  owners = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }

}


# ------------------------------------------------------------
# Lookup available subnets
#
# Some AWS accounts do not have a default subnet automatically
# selected for EC2 launches. This data source retrieves a list
# of subnets so Terraform can attach the validation instance.
# ------------------------------------------------------------
data "aws_subnets" "default" {}


# ------------------------------------------------------------
# Temporary EC2 instance used for teardown validation
# ------------------------------------------------------------
resource "aws_instance" "bloodhound_teardown_test" {

  # Create only during validation runs
  count = var.enable_validation_resources ? 1 : 0

  # Instance configuration
  ami           = data.aws_ami.amazon_linux_2.id
  instance_type = "t3.micro"

  # Attach instance to a discovered subnet
  subnet_id = data.aws_subnets.default.ids[0]

  # ----------------------------------------------------------
  # Lifecycle rule
  # ----------------------------------------------------------
  lifecycle {
    create_before_destroy = true
  }

  # ----------------------------------------------------------
  # Resource tags
  # ----------------------------------------------------------
  tags = {
    Name        = "bloodhound-teardown-test"
    Environment = "validation"

    "bloodhound:test"      = "true"
    "bloodhound:test_type" = "teardown_validation"
  }

}


# ------------------------------------------------------------
# Terraform Output
# ------------------------------------------------------------
output "bloodhound_test_instance_id" {
  value = try(aws_instance.bloodhound_teardown_test[0].id, null)
}