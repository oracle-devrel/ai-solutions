# Terraform Infrastructure (OCI OKE MCP Stack)

This folder contains all Terraform code for provisioning infrastructure used by the MCP server + MCP client deployment.

## Files

- `main.tf` - core resources (OKE, workload policies, OCIR repos)
- `bucket.tf` - Terraform-managed Object Storage bucket
- `naming.tf` - generated resource naming (prefix + compartment-based suffix)
- `network.tf` - VCN/subnet/security wiring
- `data.tf` - OCI data sources (including Object Storage namespace)
- `provider.tf` - provider and version constraints
- `variables.tf` - input variables
- `outputs.tf` - outputs consumed by deployment flow
- `terraform.tfvars.example` - user-specific placeholder template

## First-time setup

```bash
cd /selfhosted-mcp-oke/terraform
cp terraform.tfvars.example terraform.tfvars
```

Update `terraform.tfvars` with your tenancy-specific values.

Minimum:

```hcl
tenancy_ocid   = "<TENANCY_OCID>"
compartment_id = "<COMPARTMENT_OCID>"
region         = "<OCI_REGION>"
resource_name_prefix                 = "mcp"
mcp_container_repository_name        = "audio-repo"
mcp_client_container_repository_name = "client-repo"
speech_bucket_name                   = "audio-bucket"
```

By default, Terraform generates stable names such as `mcp-audio-repo-hronz`, `mcp-client-repo-hronz`, and `mcp-audio-bucket-hronz` using `resource_name_prefix`, a base name, and the last 5 characters of the compartment OCID.

Those naming values are already present in `terraform.tfvars.example`, so when you copy it they are included automatically. If you want custom base names instead, edit them in `terraform.tfvars`:

```hcl
mcp_container_repository_name        = "team-audio-repo"
mcp_client_container_repository_name = "team-client-repo"
speech_bucket_name                   = "team-audio-bucket"
```

Those values are treated as base names, so the final names still include the shared prefix and compartment suffix. The generated bucket name is exposed as a Terraform output, and the bucket itself is created by Terraform during `terraform apply`.

## Run

```bash
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

## Useful outputs

```bash
terraform output -raw mcp_server_repository_path
terraform output -raw mcp_client_repository_path
terraform output -raw cluster_id
terraform output -raw oci_namespace
terraform output -raw speech_bucket_name
terraform output -raw resource_name_prefix
```

## Destroy

```bash
terraform destroy -var-file=terraform.tfvars -auto-approve
```

> Note: Destroy removes resources managed by this stack. It does **not** delete your tenancy or Object Storage namespace.

## If you deploy to a different compartment

Changing `compartment_id` does not automatically wipe a previous compartment by itself.
What Terraform changes/destroys depends on the current state + new configuration.

Always run:

```bash
terraform plan -var-file=terraform.tfvars
```

and verify planned actions before `apply` or `destroy`.
