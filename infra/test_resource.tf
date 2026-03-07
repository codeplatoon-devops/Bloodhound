# ------------------------------------------------------------
# Bloodhound Teardown Validation Resource
#
# This Terraform resource defines a temporary EC2 instance used
# exclusively for validating Bloodhound's teardown pipeline.
#
# The validation process verifies that Bloodhound can:
#   1. Detect an AWS resource during a scan
#   2. Include the resource in the teardown plan
#   3. Execute the deletion successfully
#
# This resource is NOT created during normal Terraform deployments.
# It is only created when the variable:
#
#   enable_validation_resources = true
#
# is passed during the validation script execution.
#
# Example:
#
# terraform apply -var="enable_validation_resources=true"
#
# After validation completes, the resource is destroyed and
# removed from Terraform state.
# ------------------------------------------------------------

resource "aws_instance" "bloodhound_teardown_test" {

  # ----------------------------------------------------------
  # Conditional resource creation
  #
  # Terraform will only create this instance when the
  # validation script enables validation infrastructure.
  #
  # Normal Terraform deployments use:
  #
  # enable_validation_resources = false
  #
  # which results in:
  #
  # count = 0  → resource not created
  # ----------------------------------------------------------
  count = var.enable_validation_resources ? 1 : 0

  # ----------------------------------------------------------
  # Small disposable instance used purely for validation.
  #
  # Amazon Linux 2 is lightweight and inexpensive.
  # ----------------------------------------------------------
  ami           = "ami-0c02fb55956c7d316"
  instance_type = "t3.micro"

  # ----------------------------------------------------------
  # Lifecycle rule
  #
  # Ensures Terraform creates a replacement resource before
  # destroying an existing one. This prevents edge cases
  # during repeated validation runs.
  # ----------------------------------------------------------
  lifecycle {
    create_before_destroy = true
  }

  # ----------------------------------------------------------
  # Resource tags
  #
  # Tags help engineers quickly identify validation resources
  # in the AWS console and prevent confusion with production
  # infrastructure.
  #
  # Keys containing ":" must be quoted in Terraform maps.
  # ----------------------------------------------------------
  tags = {
    Name        = "bloodhound-teardown-test"
    Environment = "validation"

    # Indicates this instance exists only for validation
    "bloodhound:test" = "true"

    # Identifies which validation created the resource
    "bloodhound:test_type" = "teardown_validation"
  }

}

# ------------------------------------------------------------
# Terraform Output
#
# The validation script reads this value to determine which
# EC2 instance should be monitored and later verified as
# deleted by Bloodhound.
#
# Because the resource uses "count", the instance becomes
# a list and must be referenced with index [0].
# ------------------------------------------------------------

output "bloodhound_test_instance_id" {
  value = aws_instance.bloodhound_teardown_test[0].id
}