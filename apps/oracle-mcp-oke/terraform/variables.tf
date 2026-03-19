# variables.tf

variable "tenancy_ocid" {
  description = "The OCID of your tenancy."
}

variable "region" {
  description = "The OCI region where resources will be created."
  default     = "us-ashburn-1"
}

variable "compartment_id" {
  description = "The OCID of the compartment to create resources in."
}

variable "resource_name_prefix" {
  description = "Prefix used for generated repository and bucket names."
  type        = string
  default     = "mcp"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]*$", var.resource_name_prefix))
    error_message = "resource_name_prefix must start with a lowercase letter or digit and contain only lowercase letters, digits, and hyphens."
  }
}

variable "mcp_container_repository_name" {
  description = "Optional base name for the MCP server OCIR repository. The final name always includes the shared prefix and compartment suffix."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.mcp_container_repository_name == null || trimspace(var.mcp_container_repository_name) == "" || can(regex("^[a-z0-9][a-z0-9-]*$", var.mcp_container_repository_name))
    error_message = "mcp_container_repository_name must be lowercase letters, digits, and hyphens when provided."
  }
}

variable "mcp_client_container_repository_name" {
  description = "Optional base name for the MCP client OCIR repository. The final name always includes the shared prefix and compartment suffix."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.mcp_client_container_repository_name == null || trimspace(var.mcp_client_container_repository_name) == "" || can(regex("^[a-z0-9][a-z0-9-]*$", var.mcp_client_container_repository_name))
    error_message = "mcp_client_container_repository_name must be lowercase letters, digits, and hyphens when provided."
  }
}

variable "kubernetes_version" {
  description = "The version of Kubernetes to use for the OKE cluster."
  default     = "v1.33.1"
}

variable "cluster_name" {
  description = "The name of the OKE cluster."
  default     = "oke-cluster"
}

variable "control_subnet_cidr_block" {
  description = "The CIDR block for the control subnet."
  default     = "10.0.0.0/28"
}

variable "data_subnet_cidr_block" {
  description = "The CIDR block for the data subnet."
  default     = "10.0.16.0/20"
}

variable "load_balancer_subnet_cidr_block" {
  description = "The CIDR block for the public subnet."
  default     = "10.0.32.0/24"
}

variable "speech_bucket_name" {
  description = "Optional base name for the Speech Object Storage bucket. The final name always includes the shared prefix and compartment suffix."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.speech_bucket_name == null || trimspace(var.speech_bucket_name) == "" || can(regex("^[a-z0-9][a-z0-9-]*$", var.speech_bucket_name))
    error_message = "speech_bucket_name must be lowercase letters, digits, and hyphens when provided."
  }
}
