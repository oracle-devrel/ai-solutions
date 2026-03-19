locals {
  resource_name_prefix                      = lower(trimspace(var.resource_name_prefix))
  generated_name_suffix                     = substr(var.compartment_id, max(length(var.compartment_id) - 5, 0), 5)
  mcp_container_repository_base_name        = var.mcp_container_repository_name != null && trimspace(var.mcp_container_repository_name) != "" ? trimspace(var.mcp_container_repository_name) : "audio-repo"
  mcp_client_container_repository_base_name = var.mcp_client_container_repository_name != null && trimspace(var.mcp_client_container_repository_name) != "" ? trimspace(var.mcp_client_container_repository_name) : "client-repo"
  speech_bucket_base_name                   = var.speech_bucket_name != null && trimspace(var.speech_bucket_name) != "" ? trimspace(var.speech_bucket_name) : "audio-bucket"

  effective_mcp_container_repository_name        = "${local.resource_name_prefix}-${local.mcp_container_repository_base_name}-${local.generated_name_suffix}"
  effective_mcp_client_container_repository_name = "${local.resource_name_prefix}-${local.mcp_client_container_repository_base_name}-${local.generated_name_suffix}"
  effective_speech_bucket_name                   = "${local.resource_name_prefix}-${local.speech_bucket_base_name}-${local.generated_name_suffix}"
}
