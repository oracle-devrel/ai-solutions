data "oci_artifacts_container_repositories" "existing" {
  compartment_id = var.compartment_id
  display_name   = var.container_repository_name
  state          = "AVAILABLE"
}

locals {
  existing_repository = try(data.oci_artifacts_container_repositories.existing.container_repository_collection[0].items[0], null)
}

resource "oci_artifacts_container_repository" "container_repo" {
  count          = local.existing_repository == null ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = var.container_repository_name
  is_public      = false
}

output "container_repository_id" {
  value = local.existing_repository != null ? local.existing_repository.id : oci_artifacts_container_repository.container_repo[0].id
}
