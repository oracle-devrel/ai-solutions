output "vcn_id" {
  description = "The OCID of the created VCN."
  value       = oci_core_vcn.this.id
}

output "subnets" {
  description = "A map of the created subnets, with subnet OCIDs as values."
  value       = { for k, v in oci_core_subnet.this : k => v }
}