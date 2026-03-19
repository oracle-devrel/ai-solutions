# Get a list of availability domains in the region
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_identity_regions" "current" {
  filter {
    name   = "name"
    values = [var.region]
  }
}

data "oci_core_services" "all_services" {}

data "oci_objectstorage_namespace" "this" {}
