variables {
  project     = "ECommerceStore"
  environment = "development"
  name_prefix = "ecommerce"
  location    = "northeurope"
  tags        = { owner = "portfolio" }
}

run "development_metadata" {
  command = plan
  assert {
    condition     = output.name_prefix == "ecommerce-dev" && output.tags.environment == "development"
    error_message = "Development names and ownership tags must use the development boundary."
  }
  assert {
    condition     = output.tags.managedBy == "Terraform" && output.tags.lifecycle == "disposable" && output.tags.costProfile == "minimal" && output.tags.owner == "portfolio"
    error_message = "Mandatory ownership and cost tags must coexist with additional metadata."
  }
}

run "portfolio_metadata" {
  command = plan
  variables {
    environment  = "portfolio"
    cost_profile = "interview"
  }
  assert {
    condition     = output.name_prefix == "ecommerce-portfolio" && output.tags.environment == "portfolio" && output.tags.costProfile == "interview"
    error_message = "The reusable module must isolate portfolio metadata from development."
  }
}

run "reject_case_insensitive_ownership_override" {
  command = plan
  variables { tags = { Environment = "production" } }
  expect_failures = [var.tags]
}

run "reject_interview_cost_profile_for_development" {
  command = plan
  variables { cost_profile = "interview" }
  expect_failures = [var.cost_profile]
}

run "reject_invalid_name" {
  command = plan
  variables { name_prefix = "INVALID-NAME" }
  expect_failures = [var.name_prefix]
}
