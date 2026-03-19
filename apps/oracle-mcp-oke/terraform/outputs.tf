#outputs.tf
output "mcp_server_repository_path" {
  description = "The full URL for pushing images to the OCIR repository."
  value       = "${lower(data.oci_identity_regions.current.regions[0].key)}.ocir.io/${data.oci_objectstorage_namespace.this.namespace}/${local.effective_mcp_container_repository_name}"
}

output "mcp_client_repository_path" {
  description = "The full URL for pushing MCP client images to the OCIR repository."
  value       = "${lower(data.oci_identity_regions.current.regions[0].key)}.ocir.io/${data.oci_objectstorage_namespace.this.namespace}/${local.effective_mcp_client_container_repository_name}"
}

output "cluster_id" {
  value = module.oke_virtual_nodes.cluster_id
}

output "oci_namespace" {
  description = "Object Storage namespace for this tenancy"
  value       = data.oci_objectstorage_namespace.this.namespace
}

output "oci_region" {
  description = "OCI region for this stack"
  value       = var.region
}

output "speech_bucket_name" {
  description = "Speech/Object Storage bucket name"
  value       = local.effective_speech_bucket_name
}

output "resource_name_prefix" {
  description = "Prefix used for generated resource names"
  value       = local.resource_name_prefix
}
