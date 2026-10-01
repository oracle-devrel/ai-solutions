terraform {
  required_version = ">= 1.5.7"

  required_providers {
    oci = {
      source = "oracle/oci"
      # Routing profile support is available in provider 9.7.0 and later.
      version = ">= 9.7.0, < 10.0.0"
    }
  }
}

variable "compartment_id" {
  type        = string
  description = "Compartment that owns the routing profile."
}

variable "display_name" {
  type        = string
  default     = "gpt-oss-approved-regions"
  description = "Routing profile display name."
}

variable "model_id" {
  type        = string
  default     = "openai.gpt-oss-120b"
  description = "On-demand model allowed by this routing profile."
}

variable "target_regions" {
  type        = list(string)
  description = "Allowed serving regions in the same realm where model_id is available; separate from the profile's creation region."
}

variable "oci_cli_profile" {
  type        = string
  default     = "DEFAULT"
  description = "Named profile in ~/.oci/config used by the OCI Terraform provider; its region determines the routing profile's creation region."
}

variable "tenancy_id" {
  type        = string
  default     = ""
  description = "Tenancy OCID that owns the IAM policy. Required when create_api_key_policy is true."
}

variable "create_api_key_policy" {
  type        = bool
  default     = true
  description = "Create the compartment-scoped policy required for OCI Generative AI API-key inference."
}

variable "api_key_policy_name" {
  type        = string
  default     = "genai-routing-profile-api-key-access"
  description = "Display name for the generated IAM policy."
}

variable "policy_compartment_id" {
  type        = string
  default     = ""
  description = "Compartment in which API-key access is granted. Defaults to compartment_id. Set this to an existing routing profile's owning compartment when different."
}

locals {
  policy_compartment_id = var.policy_compartment_id != "" ? var.policy_compartment_id : var.compartment_id
}

provider "oci" {
  config_file_profile = var.oci_cli_profile
}

resource "oci_generative_ai_routing_profile" "demo" {
  compartment_id = var.compartment_id
  display_name   = var.display_name
  description    = "Restricts ${var.model_id} inference to approved OCI regions."

  model_routing_policy {
    allowed_models = [var.model_id]
  }

  region_routing_policy {
    allowed_regions = var.target_regions
  }
}

# API keys authenticate as the generativeaiapikey principal type. Dynamic groups
# are for OCI resource principals and are intentionally not used for this local
# API-key demo. The policy is scoped to this compartment, not the entire tenancy.
resource "oci_identity_policy" "genai_api_key_access" {
  count          = var.create_api_key_policy ? 1 : 0
  compartment_id = var.tenancy_id
  name           = var.api_key_policy_name
  description    = "Allows OCI Generative AI API keys to invoke routed inference in the demo compartment."

  statements = [
    "allow any-user to use generative-ai-family in compartment id ${local.policy_compartment_id} where ALL {request.principal.type='generativeaiapikey'}",
    "allow any-user to read generative-ai-routing-profile in compartment id ${local.policy_compartment_id} where ALL {request.principal.type='generativeaiapikey'}",
  ]

  lifecycle {
    precondition {
      condition     = var.tenancy_id != ""
      error_message = "Set tenancy_id to create the IAM policy, or set create_api_key_policy=false."
    }
  }
}

output "routing_profile_id" {
  description = "Set OCI_ROUTING_PROFILE_ID to this OCID. The app uses it as the model identifier and derives the inference endpoint region from it."
  value       = oci_generative_ai_routing_profile.demo.id
}

output "api_key_policy_id" {
  description = "OCID of the optional API-key access policy."
  value       = try(oci_identity_policy.genai_api_key_access[0].id, null)
}
