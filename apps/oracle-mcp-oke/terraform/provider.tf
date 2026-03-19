terraform {
  required_version = ">= 1.10.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 7.14.0"
    }
  }
}

provider "oci" {
  region = var.region
}

# Identity operations must run in the tenancy’s home region (ORD → us-chicago-1).
provider "oci" {
  alias  = "home"
  region = "us-chicago-1"
}