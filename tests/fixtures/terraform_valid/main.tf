terraform {
  required_version = ">= 1.0.0"
}

locals {
  project_name = "relqon-validation"
}

output "project_name" {
  description = "Project name used by the Relqon Terraform validation fixture."
  value       = local.project_name
}
