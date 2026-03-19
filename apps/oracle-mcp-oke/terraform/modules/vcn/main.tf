# Create the Virtual Cloud Network (VCN)
data "oci_core_services" "all_services" {}

resource "oci_core_vcn" "this" {
  compartment_id = var.compartment_id
  display_name   = var.vcn_name
  cidr_block     = var.vcn_cidr
  dns_label      = var.vcn_dns_label
}

# Create an Internet Gateway if requested
resource "oci_core_internet_gateway" "this" {
  count          = var.create_internet_gateway ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.vcn_name}_igw"
}

# Create a NAT Gateway if requested
resource "oci_core_nat_gateway" "this" {
  count          = var.create_nat_gateway ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.vcn_name}_nat_gateway"
}

# Create a Service Gateway if requested
resource "oci_core_service_gateway" "this" {
  count          = var.create_service_gateway ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.vcn_name}_service_gateway"
  # This fetches the specific service object needed for the gateway
  services {
    service_id = data.oci_core_services.all_services.services[0].id
  }
}

# Create a Route Table to route traffic to the Internet Gateway
resource "oci_core_route_table" "this" {
  for_each       = var.subnets
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.vcn_name}_rt_${each.key}"

  # For default traffic to IGW or NAT GW
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = each.value.is_public && var.create_internet_gateway ? oci_core_internet_gateway.this[0].id : (var.create_nat_gateway ? oci_core_nat_gateway.this[0].id : null)
  }
  # For traffic to OCI Services via Service GW 
  dynamic "route_rules" {
    # Only create this block if the subnet is flagged to use the SGW
    for_each = each.value.use_service_gateway && var.create_service_gateway ? [1] : []
    content {
      destination_type  = "SERVICE_CIDR_BLOCK"
      destination       = data.oci_core_services.all_services.services[0].cidr_block
      network_entity_id = oci_core_service_gateway.this[0].id
    }
  }
}

resource "oci_core_security_list" "custom" {
  for_each = var.security_lists

  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.vcn_name}_sl_${each.key}"

  dynamic "ingress_security_rules" {
    for_each = each.value.ingress_rules
    content {
      protocol = ingress_security_rules.value.protocol
      source   = ingress_security_rules.value.source

      dynamic "tcp_options" {
        for_each = ingress_security_rules.value.protocol == "6" && ingress_security_rules.value.tcp_min != null ? [1] : []
        content {
          min = ingress_security_rules.value.tcp_min
          max = ingress_security_rules.value.tcp_max
        }
      }

      dynamic "icmp_options" {
        for_each = ingress_security_rules.value.protocol == "1" ? [1] : []
        content {
          type = ingress_security_rules.value.icmp_type
          code = ingress_security_rules.value.icmp_code
        }
      }
    }
  }

  dynamic "egress_security_rules" {
    for_each = each.value.egress_rules
    content {
      protocol         = egress_security_rules.value.protocol
      destination      = egress_security_rules.value.destination
      destination_type = lookup(egress_security_rules.value, "dest_type", "CIDR_BLOCK")

      dynamic "tcp_options" {
        for_each = egress_security_rules.value.protocol == "6" && egress_security_rules.value.tcp_min != null ? [1] : []
        content {
          min = egress_security_rules.value.tcp_min
          max = egress_security_rules.value.tcp_max
        }
      }

      dynamic "icmp_options" {
        for_each = egress_security_rules.value.protocol == "1" ? [1] : []
        content {
          type = egress_security_rules.value.icmp_type
          code = egress_security_rules.value.icmp_code
        }
      }
    }
  }
}


# Create a public subnet
resource "oci_core_subnet" "this" {
  for_each       = var.subnets
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.vcn_name}_subnet_${each.key}"
  dns_label      = each.value.dns_label
  cidr_block     = each.value.cidr_block

  security_list_ids = [
    lookup(oci_core_security_list.custom, each.key, null) != null
    ? oci_core_security_list.custom[each.key].id
    : null
  ]

  route_table_id             = oci_core_route_table.this[each.key].id
  prohibit_public_ip_on_vnic = !each.value.is_public
}
