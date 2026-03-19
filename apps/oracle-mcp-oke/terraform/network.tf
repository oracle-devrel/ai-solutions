#network.tf

# network config follows standards from documentation: https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengnetworkconfig-virtualnodes.htm
# ------------ Network Configuration ------------

module "network" {
  source                 = "./modules/vcn"
  compartment_id         = var.compartment_id
  region                 = var.region
  vcn_cidr               = "10.0.0.0/16"
  create_nat_gateway     = true
  create_service_gateway = true

  subnets = {
    "control_plane" = {
      cidr_block = var.control_subnet_cidr_block
      is_public  = true
      dns_label  = "control"
    },
    "data_plane" = {
      cidr_block          = var.data_subnet_cidr_block
      is_public           = false
      dns_label           = "data"
      use_service_gateway = true
    },
    "load_balancer" = {
      cidr_block = var.load_balancer_subnet_cidr_block
      is_public  = true
      dns_label  = "lb"
    }
  }

  security_lists = {
    control_plane = {
      ingress_rules = [
        {
          protocol    = "6", tcp_min = 6443, tcp_max = 6443,
          source      = "0.0.0.0/0",
          description = "External access to Kubernetes API endpoint."
        },
        {
          protocol    = "6", tcp_min = 12250, tcp_max = 12250,
          source      = var.data_subnet_cidr_block,
          description = "Virtual node to control plane communication."
        },
        {
          protocol    = "1", icmp_type = 3, icmp_code = 4,
          source      = var.data_subnet_cidr_block,
          description = "Path Discovery."
        }
      ]
      egress_rules = [
        {
          protocol    = "6", tcp_min = 443, tcp_max = 443,
          dest_type   = "SERVICE_CIDR_BLOCK",
          destination = data.oci_core_services.all_services.services[0].cidr_block,
          description = "Allow Kubernetes API endpoint to communicate with regional OCI service endpoints."
        },
        {
          protocol    = "6",
          destination = var.data_subnet_cidr_block,
          description = "Allow Kubernetes API endpoint to communicate with virtual nodes."
        },
        {
          protocol    = "1", icmp_type = 3, icmp_code = 4,
          destination = var.data_subnet_cidr_block,
          description = "Path Discovery."
        }
      ]
    }
    data_plane = {
      ingress_rules = [
        {
          protocol    = "all",
          source      = var.data_subnet_cidr_block,
          description = "Pod-to-pod communication."
        },
        {
          protocol    = "6",
          source      = var.load_balancer_subnet_cidr_block,
          description = "Traffic from load balancer to pod and health check node port traffic for external-traffic-policy=local."
        },
        {
          protocol    = "17", min = 10256, max = 10256,
          source      = var.load_balancer_subnet_cidr_block,
          description = "Traffic from load balancer to health check port for external-traffic-policy=cluster."
        },
        {
          protocol    = "1", icmp_type = 3, icmp_code = 4,
          source      = var.control_subnet_cidr_block,
          description = "Path discovery from API server."
        },
        {
          protocol    = "6",
          source      = var.control_subnet_cidr_block,
          description = "API server to virtual node communication."
        }
      ]
      egress_rules = [
        {
          protocol    = "all",
          destination = "0.0.0.0/0",
          description = "Pod access to internet"
        }
      ]
    }
    load_balancer = {
      ingress_rules = [
        {
          protocol    = "6", tcp_min = 80, tcp_max = 80,
          source      = "0.0.0.0/0",
          description = "Incoming http traffic to load balancer"
        },
        {
          protocol    = "6", tcp_min = 443, tcp_max = 443,
          source      = "0.0.0.0/0",
          description = "Incoming https traffic to load balancer"
        }
      ]
      egress_rules = [
        {
          protocol    = "all",
          destination = var.data_subnet_cidr_block,
          description = "Traffic to pod and health check node port traffic for external-traffic-policy=local."
        },
        {
          protocol    = "17", min = 30000, max = 32767,
          destination = var.data_subnet_cidr_block,
          description = "Traffic to health check port for external-traffic-policy=cluster."
        },
        {
          protocol    = "17", min = 10256, max = 10256,
          destination = var.data_subnet_cidr_block,
          description = "Traffic to health check port for external-traffic-policy=cluster."
        },
      ]
    }
  }
}

