variable "tenancy_ocid" {
  description = "The OCID of your tenancy."
  type        = string
}

variable "compartment_ocid" {
  description = "The OCID of the compartment to create resources in."
  type        = string
}

variable "region" {
  description = "The OCI region where resources will be created."
  type        = string
  default     = "us-ashburn-1"
}

variable "cluster_name" {
  default = "oke-virtual-cluster"
}

variable "kubernetes_version" {
  default = "v1.33.1"
}

variable "vcn_id" {
  description = "The OCID of the VCN to use for the OKE cluster."
  type        = string
}

variable "control_plane_subnet_id" {
  description = "The OCID of the subnet to use for the control plane."
  type        = string
}

variable "load_balancer_subnet_id" {
  description = "The OCID of the subnet to use for the load balancer."
  type        = string
}

variable "virtual_nodes_subnet_id" {
  description = "The OCID of the subnet to use for the virtual nodes."
  type        = string
}

variable "pods_cidr" {
  default = "10.244.0.0/16"
}

variable "services_cidr" {
  default = "10.96.0.0/16"
}

variable "api_endpoint_nsg_ids" {
  description = "A list of Network Security Group OCIDs to apply to the K8s API endpoint."
  type        = list(string)
  default     = []
}
