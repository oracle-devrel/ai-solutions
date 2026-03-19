output "cluster_id" {
  description = "The OCID of the created cluster."
  value       = oci_containerengine_cluster.oke_cluster.id
}

output "virtual_node_pool_id" {
  description = "The OCID of the virtual node pool."
  value       = oci_containerengine_virtual_node_pool.virtual_node_pool.id
}
