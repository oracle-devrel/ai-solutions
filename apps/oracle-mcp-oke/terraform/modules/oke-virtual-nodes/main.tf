# Terraform module for creating an OKE cluster with virtual nodes (without networking components)
# OKE Cluster
resource "oci_containerengine_cluster" "oke_cluster" {
  compartment_id     = var.compartment_ocid
  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version
  vcn_id             = var.vcn_id
  type               = "ENHANCED_CLUSTER"

  cluster_pod_network_options {
    cni_type = "OCI_VCN_IP_NATIVE"
  }

  endpoint_config {
    is_public_ip_enabled = true
    subnet_id            = var.control_plane_subnet_id
    nsg_ids              = var.api_endpoint_nsg_ids
  }

  options {
    service_lb_subnet_ids = [var.load_balancer_subnet_id]

    kubernetes_network_config {
      pods_cidr     = var.pods_cidr
      services_cidr = var.services_cidr
    }
  }
}

# Virtual Node Pool
resource "oci_containerengine_virtual_node_pool" "virtual_node_pool" {
  compartment_id = var.compartment_ocid
  cluster_id     = oci_containerengine_cluster.oke_cluster.id
  display_name   = "${var.cluster_name}-pool"
  size           = 2 # Number of virtual nodes

  #Required
  pod_configuration {
    #Required
    shape     = "Pod.Standard.E4.Flex"
    subnet_id = var.virtual_nodes_subnet_id
  }

  placement_configurations {
    availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
    subnet_id           = var.virtual_nodes_subnet_id
    fault_domain        = data.oci_identity_fault_domains.fds.fault_domains[*].name
  }
}

# Data source for availability domains
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_identity_fault_domains" "fds" {
  compartment_id      = var.tenancy_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
}
