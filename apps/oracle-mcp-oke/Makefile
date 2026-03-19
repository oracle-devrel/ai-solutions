# Makefile for OKE Deployment

TF_VAR_FILE     ?= terraform.tfvars
TF_DIR          ?= $(CURDIR)/terraform
TENANCY_OCID     ?=ocid1.tenancy.oc1..
COMPARTMENT_OCID ?=ocid1.compartment.oc1..
DOCKER_USER     ?=<oci_namespace>/????@oracle.com
DOCKER_EMAIL    ?=???@oracle.com
DOCKER_PASS     ?=
REGION          ?=
OCI_NAMESPACE   ?=
KUBECONFIG_PATH ?= $(HOME)/.kube/config
MANIFEST_FILE   ?= $(CURDIR)/mcp-audio/k8s/manifest.yaml
LB_READY_TIMEOUT ?= 420
IMAGE_VERSION   ?= latest
CLIENT_IMAGE_VERSION ?= latest
HOSTED_IMAGE_TAG ?= hosted-v1
RESOURCE_NAME_PREFIX ?= mcp-eu
MCP_CONTAINER_REPOSITORY_NAME ?=mcp-server
MCP_CLIENT_CONTAINER_REPOSITORY_NAME ?=mcp-client
SPEECH_BUCKET_NAME ?=mcp-audio-bucket
SKIP_BUCKET_CLEANUP ?= false
MCP_NAMESPACE   := mcp
SED_INPLACE = sed -i'' -e  #SED_INPLACE = sed -i -e for LINUX
OCIR_PUSH_RETRY_ATTEMPTS ?= 6
OCIR_PUSH_RETRY_DELAY ?= 10



# PHONY TARGETS
# ------------------------------------------------------------------------------
# .PHONY ensures that make will not confuse these targets with actual files.
.PHONY: all plan apply kubeconfig create-secret create-runtime-secrets build-push deploy destroy clean update-tfvars update-manifest kubectl create-namespace create-docker-credentials docker-build docker-push docker-build-client docker-push-client docker-hosted-build-server docker-hosted-push-server docker-hosted-build-client docker-hosted-push-client docker-hosted-push deploy destroy-manifest destroy-terraform empty-speech-bucket mcp-server sync-client-mcp-public-url print-service-urls quick-redeploy print-dynamic-values terraform-init-resilient \
    dev-client-setup dev-client-run dev-server-setup dev-server-run dev-server-run-bg dev-client-run-bg destroy-k8s destroy-all-fresh deploy-fresh-guided validate-fresh check-required-vars

define docker_push_with_retry
	@set -e; \
	IMAGE_REF="$(1)"; \
	ATTEMPT=1; \
	MAX_ATTEMPTS=$(OCIR_PUSH_RETRY_ATTEMPTS); \
	DELAY=$(OCIR_PUSH_RETRY_DELAY); \
	while [ $$ATTEMPT -le $$MAX_ATTEMPTS ]; do \
		echo "INFO: docker push attempt $$ATTEMPT/$$MAX_ATTEMPTS -> $$IMAGE_REF"; \
		if docker push "$$IMAGE_REF"; then \
			echo "INFO: docker push succeeded -> $$IMAGE_REF"; \
			exit 0; \
		fi; \
		if [ $$ATTEMPT -lt $$MAX_ATTEMPTS ]; then \
			echo "WARN: docker push failed for $$IMAGE_REF. Retrying in $${DELAY}s (possible OCIR/IAM propagation delay)..."; \
			sleep $$DELAY; \
		fi; \
		ATTEMPT=$$((ATTEMPT + 1)); \
	done; \
	echo "ERROR: docker push failed after $$MAX_ATTEMPTS attempts -> $$IMAGE_REF"; \
	exit 1
endef

# MAIN TARGET
# ------------------------------------------------------------------------------
# This is the default target that runs when you just type 'make'.
all: update-tfvars init plan apply update-manifest kubectl create-namespace create-docker-credentials create-runtime-secrets docker-build docker-push docker-build-client docker-push-client deploy mcp-server
destroy-all: destroy-manifest destroy-terraform 

# TFVARS TARGET
# ------------------------------------------------------------------------------
# Populates the terraform.tfvars file with required values from Makefile variables.
check-required-vars:
	@echo "INFO: Checking Makefile variables (required vs optional)..."
	@TFVARS_PATH="$(TF_DIR)/$(TF_VAR_FILE)"; \
	TF_TENANCY=$$(awk -F'=' '/^[[:space:]]*tenancy_ocid[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	TF_COMPARTMENT=$$(awk -F'=' '/^[[:space:]]*compartment_id[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	TF_REGION=$$(awk -F'=' '/^[[:space:]]*region[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	FINAL_TENANCY="$(TENANCY_OCID)"; \
	FINAL_COMPARTMENT="$(COMPARTMENT_OCID)"; \
	FINAL_REGION="$(REGION)"; \
	if [ -z "$$FINAL_TENANCY" ] || [ "$$FINAL_TENANCY" = "<TENANCY_OCID>" ]; then FINAL_TENANCY="$$TF_TENANCY"; fi; \
	if [ -z "$$FINAL_COMPARTMENT" ] || [ "$$FINAL_COMPARTMENT" = "<COMPARTMENT_OCID>" ]; then FINAL_COMPARTMENT="$$TF_COMPARTMENT"; fi; \
	if [ -z "$$FINAL_REGION" ] || [ "$$FINAL_REGION" = "<OCI_REGION>" ]; then FINAL_REGION="$$TF_REGION"; fi; \
	if [ -z "$$FINAL_TENANCY" ] || [ "$$FINAL_TENANCY" = "<TENANCY_OCID>" ]; then echo "ERROR: TENANCY_OCID is required"; exit 1; fi; \
	if [ -z "$$FINAL_COMPARTMENT" ] || [ "$$FINAL_COMPARTMENT" = "<COMPARTMENT_OCID>" ]; then echo "ERROR: COMPARTMENT_OCID is required"; exit 1; fi; \
	if [ -z "$$FINAL_REGION" ] || [ "$$FINAL_REGION" = "<OCI_REGION>" ]; then echo "ERROR: REGION is required"; exit 1; fi; \
	echo "INFO: Required variables are set: TENANCY_OCID, COMPARTMENT_OCID, REGION"
	@echo "INFO: Optional variables: DOCKER_USER, DOCKER_PASS, DOCKER_EMAIL, IMAGE_VERSION, CLIENT_IMAGE_VERSION, RESOURCE_NAME_PREFIX, MCP_CONTAINER_REPOSITORY_NAME, MCP_CLIENT_CONTAINER_REPOSITORY_NAME, SPEECH_BUCKET_NAME, KUBECONFIG_PATH"

update-tfvars: check-required-vars
	@echo "INFO: Updating $(TF_VAR_FILE) file..."
	@TFVARS_PATH="$(TF_DIR)/$(TF_VAR_FILE)"; \
	EXISTING_TENANCY=$$(awk -F'=' '/^[[:space:]]*tenancy_ocid[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	EXISTING_COMPARTMENT=$$(awk -F'=' '/^[[:space:]]*compartment_id[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	EXISTING_REGION=$$(awk -F'=' '/^[[:space:]]*region[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	EXISTING_PREFIX=$$(awk -F'=' '/^[[:space:]]*resource_name_prefix[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	EXISTING_SERVER_BASE=$$(awk -F'=' '/^[[:space:]]*mcp_container_repository_name[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	EXISTING_CLIENT_BASE=$$(awk -F'=' '/^[[:space:]]*mcp_client_container_repository_name[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	EXISTING_BUCKET_BASE=$$(awk -F'=' '/^[[:space:]]*speech_bucket_name[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH" 2>/dev/null || true); \
	EFFECTIVE_TENANCY="$(TENANCY_OCID)"; \
	EFFECTIVE_COMPARTMENT="$(COMPARTMENT_OCID)"; \
	EFFECTIVE_REGION="$(REGION)"; \
	EFFECTIVE_PREFIX="$(RESOURCE_NAME_PREFIX)"; \
	EFFECTIVE_SERVER_BASE="$(MCP_CONTAINER_REPOSITORY_NAME)"; \
	EFFECTIVE_CLIENT_BASE="$(MCP_CLIENT_CONTAINER_REPOSITORY_NAME)"; \
	EFFECTIVE_BUCKET_BASE="$(SPEECH_BUCKET_NAME)"; \
	if [ -z "$$EFFECTIVE_TENANCY" ] || [ "$$EFFECTIVE_TENANCY" = "<TENANCY_OCID>" ]; then EFFECTIVE_TENANCY="$$EXISTING_TENANCY"; fi; \
	if [ -z "$$EFFECTIVE_COMPARTMENT" ] || [ "$$EFFECTIVE_COMPARTMENT" = "<COMPARTMENT_OCID>" ]; then EFFECTIVE_COMPARTMENT="$$EXISTING_COMPARTMENT"; fi; \
	if [ -z "$$EFFECTIVE_REGION" ] || [ "$$EFFECTIVE_REGION" = "<OCI_REGION>" ]; then EFFECTIVE_REGION="$$EXISTING_REGION"; fi; \
	if [ -z "$$EFFECTIVE_PREFIX" ]; then EFFECTIVE_PREFIX="$${EXISTING_PREFIX:-mcp}"; fi; \
	if [ -z "$$EFFECTIVE_SERVER_BASE" ]; then EFFECTIVE_SERVER_BASE="$$EXISTING_SERVER_BASE"; fi; \
	if [ -z "$$EFFECTIVE_CLIENT_BASE" ]; then EFFECTIVE_CLIENT_BASE="$$EXISTING_CLIENT_BASE"; fi; \
	if [ -z "$$EFFECTIVE_BUCKET_BASE" ]; then EFFECTIVE_BUCKET_BASE="$$EXISTING_BUCKET_BASE"; fi; \
	echo "tenancy_ocid       = \"$$EFFECTIVE_TENANCY\"" > "$$TFVARS_PATH"; \
	echo "compartment_id     = \"$$EFFECTIVE_COMPARTMENT\"" >> "$$TFVARS_PATH"; \
	echo "region             = \"$$EFFECTIVE_REGION\"" >> "$$TFVARS_PATH"; \
	echo "resource_name_prefix                 = \"$$EFFECTIVE_PREFIX\"" >> "$$TFVARS_PATH"; \
	if [ -n "$$EFFECTIVE_SERVER_BASE" ]; then echo "mcp_container_repository_name        = \"$$EFFECTIVE_SERVER_BASE\"" >> "$$TFVARS_PATH"; fi; \
	if [ -n "$$EFFECTIVE_CLIENT_BASE" ]; then echo "mcp_client_container_repository_name = \"$$EFFECTIVE_CLIENT_BASE\"" >> "$$TFVARS_PATH"; fi; \
	if [ -n "$$EFFECTIVE_BUCKET_BASE" ]; then echo "speech_bucket_name                   = \"$$EFFECTIVE_BUCKET_BASE\"" >> "$$TFVARS_PATH"; fi

# TERRAFORM TARGETS
# ------------------------------------------------------------------------------
# Initializes and validates the terraform configuration.
terraform-init-resilient:
	@echo "INFO: Initializing Terraform (readonly lockfile first, then auto-fallback if lock update is needed)..."
	@ATTEMPT=1; MAX_ATTEMPTS=3; \
	while [ $$ATTEMPT -le $$MAX_ATTEMPTS ]; do \
		echo "INFO: terraform init attempt $$ATTEMPT/$$MAX_ATTEMPTS"; \
		if TF_REGISTRY_DISCOVERY_RETRY=5 TF_REGISTRY_CLIENT_TIMEOUT=30 terraform -chdir=$(TF_DIR) init ; then \
			exit 0; \
		fi; \
		echo "WARN: terraform init with -lockfile=readonly failed."; \
		echo "INFO: Trying terraform init without readonly lockfile to allow provider lock updates..."; \
		if TF_REGISTRY_DISCOVERY_RETRY=5 TF_REGISTRY_CLIENT_TIMEOUT=30 terraform -chdir=$(TF_DIR) init; then \
			echo "INFO: terraform init succeeded after allowing lockfile update."; \
			exit 0; \
		fi; \
		if [ $$ATTEMPT -lt $$MAX_ATTEMPTS ]; then \
			echo "WARN: terraform init failed (possible transient registry/network issue). Retrying in 5s..."; \
			sleep 5; \
		fi; \
		ATTEMPT=$$((ATTEMPT + 1)); \
	done; \
	echo "ERROR: terraform init failed after $$MAX_ATTEMPTS attempts."; \
	echo "ERROR: If this is a network issue, verify connectivity to https://registry.terraform.io/.well-known/terraform.json"; \
	exit 1

init:
	@$(MAKE) terraform-init-resilient

# Shows the execution plan for terraform.
plan: init update-tfvars
	@echo "INFO: Planning Terraform infrastructure changes..."
	terraform -chdir=$(TF_DIR) plan -var-file=$(TF_VAR_FILE)

# Applies the terraform configuration to build infrastructure.
apply: init update-tfvars
	@echo "INFO: Applying Terraform configuration..."
	terraform -chdir=$(TF_DIR) apply -var-file=$(TF_VAR_FILE) -auto-approve


# MANIFEST UPDATE TARGET
# ------------------------------------------------------------------------------
# Updates the manifest.yaml file with Compartment_OCID, dynamic OCI values, and server/client image tags from Terraform outputs.
update-manifest: apply
	@echo "INFO: Updating $(MANIFEST_FILE) with required values..."
	@if [ -z "$(COMPARTMENT_OCID)" ]; then echo "ERROR: COMPARTMENT_OCID is required for update-manifest"; exit 1; fi
	@MCP_SERVER_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path) && \
	MCP_CLIENT_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path) && \
	OCI_NAMESPACE=$$(terraform -chdir=$(TF_DIR) output -raw oci_namespace) && \
	SPEECH_BUCKET=$$(terraform -chdir=$(TF_DIR) output -raw speech_bucket_name) && \
	MCP_SERVER_IMAGE_TAG=$${MCP_SERVER_IMAGE_PATH}:$(IMAGE_VERSION) && \
	MCP_CLIENT_IMAGE_TAG=$${MCP_CLIENT_IMAGE_PATH}:$(CLIENT_IMAGE_VERSION) && \
	$(SED_INPLACE) 's|<Compartment_OCID>|$(COMPARTMENT_OCID)|g' $(MANIFEST_FILE) && \
	$(SED_INPLACE) "s|<Notification_Topic_OCID>||g" $(MANIFEST_FILE) && \
	$(SED_INPLACE) "s|<OCI_NAMESPACE>|$${OCI_NAMESPACE}|g" $(MANIFEST_FILE) && \
	$(SED_INPLACE) "s|<SPEECH_BUCKET>|$${SPEECH_BUCKET}|g" $(MANIFEST_FILE) && \
	$(SED_INPLACE) "s|<mcp-audio-image-tag>|$${MCP_SERVER_IMAGE_TAG}|g" $(MANIFEST_FILE) && \
	$(SED_INPLACE) "s|<mcp-server-image-tag>|$${MCP_SERVER_IMAGE_TAG}|g" $(MANIFEST_FILE) && \
	$(SED_INPLACE) "s|<mcp-client-image-tag>|$${MCP_CLIENT_IMAGE_TAG}|g" $(MANIFEST_FILE)



#setting up Cluster Credentials
kubectl: 
	@echo "INFO: Generating kubeconfig for cluster $(CLUSTER_ID)..."
	OCI_REGION_VALUE=$$(terraform -chdir=$(TF_DIR) output -raw oci_region 2>/dev/null || awk -F'=' '/^[[:space:]]*region[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' $(TF_DIR)/$(TF_VAR_FILE)) && \
	cluster_id=$$(terraform -chdir=$(TF_DIR) output -raw cluster_id) && \
	echo "INFO: Using OCI region $$OCI_REGION_VALUE for kubeconfig" && \
	oci ce cluster create-kubeconfig \
	--cluster-id $${cluster_id} \
	--file $(KUBECONFIG_PATH) \
	--region $$OCI_REGION_VALUE \
	--token-version 2.0.0 \
	--kube-endpoint PUBLIC_ENDPOINT


create-namespace: kubectl
	@echo "INFO: Ensuring namespace (K8S NAMESPACE)exists..."
	kubectl --kubeconfig $(KUBECONFIG_PATH) create ns $(MCP_NAMESPACE)

create-docker-credentials: 
	@echo "INFO: Creating Docker credentials for mcp namespace..."
	@IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path) && \
	REGISTRY_HOST=$$(echo $$IMAGE_PATH | awk -F/ '{print $$1}') && \
	NS=$$(echo $$IMAGE_PATH | awk -F/ '{print $$2}') && \
	EFFECTIVE_DOCKER_USER="$(DOCKER_USER)" && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then \
		echo "INFO: DOCKER_USER not provided."; \
		read -p "DOCKER_USER [example: $$NS/<your-oci-username>]: " EFFECTIVE_DOCKER_USER; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then echo "ERROR: DOCKER_USER is required"; exit 1; fi && \
	if ! echo "$$EFFECTIVE_DOCKER_USER" | grep -q '/'; then EFFECTIVE_DOCKER_USER="$$NS/$$EFFECTIVE_DOCKER_USER"; fi && \
	EFFECTIVE_DOCKER_PASS="$(DOCKER_PASS)" && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then \
		echo "INFO: DOCKER_PASS not provided."; \
		read -s -p "DOCKER_PASS (OCIR auth token): " EFFECTIVE_DOCKER_PASS; \
		echo; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then echo "ERROR: DOCKER_PASS is required"; exit 1; fi && \
	echo "INFO: Using registry $$REGISTRY_HOST" && \
	echo "INFO: Using docker username $$EFFECTIVE_DOCKER_USER" && \
	kubectl --kubeconfig $(KUBECONFIG_PATH) create secret docker-registry ocirsecret \
	--docker-server=$$REGISTRY_HOST \
	--docker-username=$$EFFECTIVE_DOCKER_USER \
	--docker-password="$$EFFECTIVE_DOCKER_PASS" \
	--docker-email=$(DOCKER_EMAIL) \
	--namespace $(MCP_NAMESPACE)

docker-build: kubectl
	@echo "INFO: Building Docker image..."	
	MCP_SERVER_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path) && \
	docker build --platform linux/amd64 -t $${MCP_SERVER_IMAGE_PATH}:$(IMAGE_VERSION) mcp-audio/

docker-build-client: kubectl
	@echo "INFO: Building MCP client Docker image..."	
	MCP_CLIENT_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path) && \
	docker build --platform linux/amd64 -t $${MCP_CLIENT_IMAGE_PATH}:$(CLIENT_IMAGE_VERSION) mcp-client/

docker-push: docker-build
	@echo "INFO: Pushing Docker image to registry..."
	@MCP_SERVER_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path) && \
	REGISTRY_HOST=$$(echo $$MCP_SERVER_IMAGE_PATH | awk -F/ '{print $$1}') && \
	NS=$$(echo $$MCP_SERVER_IMAGE_PATH | awk -F/ '{print $$2}') && \
	EFFECTIVE_DOCKER_USER="$(DOCKER_USER)" && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then \
		echo "INFO: DOCKER_USER not provided."; \
		read -p "DOCKER_USER [example: $$NS/<your-oci-username>]: " EFFECTIVE_DOCKER_USER; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then echo "ERROR: DOCKER_USER is required"; exit 1; fi && \
	if ! echo "$$EFFECTIVE_DOCKER_USER" | grep -q '/'; then EFFECTIVE_DOCKER_USER="$$NS/$$EFFECTIVE_DOCKER_USER"; fi && \
	EFFECTIVE_DOCKER_PASS="$(DOCKER_PASS)" && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then \
		echo "INFO: DOCKER_PASS not provided."; \
		read -s -p "DOCKER_PASS (OCIR auth token): " EFFECTIVE_DOCKER_PASS; \
		echo; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then echo "ERROR: DOCKER_PASS is required"; exit 1; fi && \
	echo "INFO: Using docker username $$EFFECTIVE_DOCKER_USER" && \
	echo "$$EFFECTIVE_DOCKER_PASS" | docker login --username $$EFFECTIVE_DOCKER_USER --password-stdin $$REGISTRY_HOST && \
	$(call docker_push_with_retry,$${MCP_SERVER_IMAGE_PATH}:$(IMAGE_VERSION))

docker-push-client: docker-build-client
	@echo "INFO: Pushing MCP client image to registry..."
	@MCP_CLIENT_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path) && \
	REGISTRY_HOST=$$(echo $$MCP_CLIENT_IMAGE_PATH | awk -F/ '{print $$1}') && \
	NS=$$(echo $$MCP_CLIENT_IMAGE_PATH | awk -F/ '{print $$2}') && \
	EFFECTIVE_DOCKER_USER="$(DOCKER_USER)" && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then \
		echo "INFO: DOCKER_USER not provided."; \
		read -p "DOCKER_USER [example: $$NS/<your-oci-username>]: " EFFECTIVE_DOCKER_USER; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then echo "ERROR: DOCKER_USER is required"; exit 1; fi && \
	if ! echo "$$EFFECTIVE_DOCKER_USER" | grep -q '/'; then EFFECTIVE_DOCKER_USER="$$NS/$$EFFECTIVE_DOCKER_USER"; fi && \
	EFFECTIVE_DOCKER_PASS="$(DOCKER_PASS)" && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then \
		echo "INFO: DOCKER_PASS not provided."; \
		read -s -p "DOCKER_PASS (OCIR auth token): " EFFECTIVE_DOCKER_PASS; \
		echo; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then echo "ERROR: DOCKER_PASS is required"; exit 1; fi && \
	echo "INFO: Using docker username $$EFFECTIVE_DOCKER_USER" && \
	echo "$$EFFECTIVE_DOCKER_PASS" | docker login --username $$EFFECTIVE_DOCKER_USER --password-stdin $$REGISTRY_HOST && \
	$(call docker_push_with_retry,$${MCP_CLIENT_IMAGE_PATH}:$(CLIENT_IMAGE_VERSION))

docker-hosted-build-server:
	@DEFAULT_HOSTED_TAG="$(HOSTED_IMAGE_TAG)" && \
	EFFECTIVE_HOSTED_IMAGE_TAG="$(HOSTED_IMAGE_TAG_OVERRIDE)" && \
	if [ -z "$$EFFECTIVE_HOSTED_IMAGE_TAG" ]; then \
		read -p "Enter hosted image tag [$$DEFAULT_HOSTED_TAG]: " EFFECTIVE_HOSTED_IMAGE_TAG; \
	fi && \
	EFFECTIVE_HOSTED_IMAGE_TAG=$${EFFECTIVE_HOSTED_IMAGE_TAG:-$$DEFAULT_HOSTED_TAG} && \
	echo "INFO: Building hosted SERVER image (tag=$$EFFECTIVE_HOSTED_IMAGE_TAG)..." && \
	MCP_SERVER_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path) && \
	docker build --platform linux/amd64 -t $${MCP_SERVER_IMAGE_PATH}:$$EFFECTIVE_HOSTED_IMAGE_TAG mcp-audio/

docker-hosted-push-server:
	@DEFAULT_HOSTED_TAG="$(HOSTED_IMAGE_TAG)" && \
	read -p "Enter hosted image tag [$$DEFAULT_HOSTED_TAG]: " EFFECTIVE_HOSTED_IMAGE_TAG && \
	EFFECTIVE_HOSTED_IMAGE_TAG=$${EFFECTIVE_HOSTED_IMAGE_TAG:-$$DEFAULT_HOSTED_TAG} && \
	$(MAKE) docker-hosted-build-server HOSTED_IMAGE_TAG_OVERRIDE=$$EFFECTIVE_HOSTED_IMAGE_TAG && \
	echo "INFO: Pushing hosted SERVER image (tag=$$EFFECTIVE_HOSTED_IMAGE_TAG)..." && \
	MCP_SERVER_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path) && \
	REGISTRY_HOST=$$(echo $$MCP_SERVER_IMAGE_PATH | awk -F/ '{print $$1}') && \
	NS=$$(echo $$MCP_SERVER_IMAGE_PATH | awk -F/ '{print $$2}') && \
	EFFECTIVE_DOCKER_USER="$(DOCKER_USER)" && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then \
		echo "INFO: DOCKER_USER not provided."; \
		read -p "DOCKER_USER [example: $$NS/<your-oci-username>]: " EFFECTIVE_DOCKER_USER; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then echo "ERROR: DOCKER_USER is required"; exit 1; fi && \
	if ! echo "$$EFFECTIVE_DOCKER_USER" | grep -q '/'; then EFFECTIVE_DOCKER_USER="$$NS/$$EFFECTIVE_DOCKER_USER"; fi && \
	EFFECTIVE_DOCKER_PASS="$(DOCKER_PASS)" && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then \
		echo "INFO: DOCKER_PASS not provided."; \
		read -s -p "DOCKER_PASS (OCIR auth token): " EFFECTIVE_DOCKER_PASS; \
		echo; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then echo "ERROR: DOCKER_PASS is required"; exit 1; fi && \
	echo "INFO: Using docker username $$EFFECTIVE_DOCKER_USER" && \
	echo "$$EFFECTIVE_DOCKER_PASS" | docker login --username $$EFFECTIVE_DOCKER_USER --password-stdin $$REGISTRY_HOST && \
	$(call docker_push_with_retry,$${MCP_SERVER_IMAGE_PATH}:$$EFFECTIVE_HOSTED_IMAGE_TAG)

docker-hosted-build-client:
	@DEFAULT_HOSTED_TAG="$(HOSTED_IMAGE_TAG)" && \
	EFFECTIVE_HOSTED_IMAGE_TAG="$(HOSTED_IMAGE_TAG_OVERRIDE)" && \
	if [ -z "$$EFFECTIVE_HOSTED_IMAGE_TAG" ]; then \
		read -p "Enter hosted image tag [$$DEFAULT_HOSTED_TAG]: " EFFECTIVE_HOSTED_IMAGE_TAG; \
	fi && \
	EFFECTIVE_HOSTED_IMAGE_TAG=$${EFFECTIVE_HOSTED_IMAGE_TAG:-$$DEFAULT_HOSTED_TAG} && \
	echo "INFO: Building hosted CLIENT image (tag=$$EFFECTIVE_HOSTED_IMAGE_TAG)..." && \
	MCP_CLIENT_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path) && \
	docker build --platform linux/amd64 -t $${MCP_CLIENT_IMAGE_PATH}:$$EFFECTIVE_HOSTED_IMAGE_TAG mcp-client/

docker-hosted-push-client:
	@DEFAULT_HOSTED_TAG="$(HOSTED_IMAGE_TAG)" && \
	read -p "Enter hosted image tag [$$DEFAULT_HOSTED_TAG]: " EFFECTIVE_HOSTED_IMAGE_TAG && \
	EFFECTIVE_HOSTED_IMAGE_TAG=$${EFFECTIVE_HOSTED_IMAGE_TAG:-$$DEFAULT_HOSTED_TAG} && \
	$(MAKE) docker-hosted-build-client HOSTED_IMAGE_TAG_OVERRIDE=$$EFFECTIVE_HOSTED_IMAGE_TAG && \
	echo "INFO: Pushing hosted CLIENT image (tag=$$EFFECTIVE_HOSTED_IMAGE_TAG)..." && \
	MCP_CLIENT_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path) && \
	REGISTRY_HOST=$$(echo $$MCP_CLIENT_IMAGE_PATH | awk -F/ '{print $$1}') && \
	NS=$$(echo $$MCP_CLIENT_IMAGE_PATH | awk -F/ '{print $$2}') && \
	EFFECTIVE_DOCKER_USER="$(DOCKER_USER)" && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then \
		echo "INFO: DOCKER_USER not provided."; \
		read -p "DOCKER_USER [example: $$NS/<your-oci-username>]: " EFFECTIVE_DOCKER_USER; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then echo "ERROR: DOCKER_USER is required"; exit 1; fi && \
	if ! echo "$$EFFECTIVE_DOCKER_USER" | grep -q '/'; then EFFECTIVE_DOCKER_USER="$$NS/$$EFFECTIVE_DOCKER_USER"; fi && \
	EFFECTIVE_DOCKER_PASS="$(DOCKER_PASS)" && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then \
		echo "INFO: DOCKER_PASS not provided."; \
		read -s -p "DOCKER_PASS (OCIR auth token): " EFFECTIVE_DOCKER_PASS; \
		echo; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then echo "ERROR: DOCKER_PASS is required"; exit 1; fi && \
	echo "INFO: Using docker username $$EFFECTIVE_DOCKER_USER" && \
	echo "$$EFFECTIVE_DOCKER_PASS" | docker login --username $$EFFECTIVE_DOCKER_USER --password-stdin $$REGISTRY_HOST && \
	$(call docker_push_with_retry,$${MCP_CLIENT_IMAGE_PATH}:$$EFFECTIVE_HOSTED_IMAGE_TAG)

docker-hosted-push: docker-hosted-push-server docker-hosted-push-client
	@echo "INFO: Hosted server+client images pushed (using prompted tag or default $(HOSTED_IMAGE_TAG))"

print-dynamic-values:
	@echo "INFO: Fetching dynamic deployment values..."
	@echo "INFO: Values expected from Terraform are available only after 'terraform apply'"
	@TF_NS=$$(terraform -chdir=$(TF_DIR) output -raw oci_namespace 2>/dev/null || true); \
	TF_REGION=$$(terraform -chdir=$(TF_DIR) output -raw oci_region 2>/dev/null || true); \
	CLI_NS=$$(oci os ns get --query 'data' --raw-output 2>/dev/null || true); \
	IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path 2>/dev/null || true); \
	CLIENT_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path 2>/dev/null || true); \
	CLUSTER_ID=$$(terraform -chdir=$(TF_DIR) output -raw cluster_id 2>/dev/null || true); \
	echo "OCI Region             : $${TF_REGION:-<unavailable>}"; \
	echo "OCI Namespace (terraform): $${TF_NS:-<unavailable>}"; \
	echo "OCI Namespace (oci cli) : $${CLI_NS:-<unavailable>}"; \
	echo "Image Path             : $${IMAGE_PATH:-<unavailable>}"; \
	echo "Client Image Path      : $${CLIENT_IMAGE_PATH:-<unavailable>}"; \
	echo "Cluster ID             : $${CLUSTER_ID:-<unavailable>}"; \
	echo "User must provide      : DOCKER_PASS, COMPARTMENT_OCID"; \
	echo "DOCKER_USER            : Optional (will prompt if missing in targets)"; \
	if [ -n "$$CLI_NS" ]; then \
		echo "Suggested DOCKER_USER : $$CLI_NS/<oci-username>"; \
		echo "Auto-derived example  : $$CLI_NS/$(DOCKER_EMAIL)"; \
	fi

create-runtime-secrets:
	@echo "INFO: Creating runtime secrets for server/client from .env files..."
	@if [ ! -f "$(CURDIR)/mcp-audio/.env" ]; then echo "ERROR: Missing mcp-audio/.env"; exit 1; fi
	@if [ ! -f "$(CURDIR)/mcp-client/.env" ]; then \
		echo "WARN: Missing mcp-client/.env; creating it from mcp-client/.env.example"; \
		cp "$(CURDIR)/mcp-client/.env.example" "$(CURDIR)/mcp-client/.env"; \
	fi
	kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) delete secret mcp-secrets --ignore-not-found
	kubectl --kubeconfig $(KUBECONFIG_PATH) create secret generic mcp-secrets --from-env-file=$(CURDIR)/mcp-audio/.env -n $(MCP_NAMESPACE)
	kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) delete secret mcp-client-secrets --ignore-not-found
	kubectl --kubeconfig $(KUBECONFIG_PATH) create secret generic mcp-client-secrets --from-env-file=$(CURDIR)/mcp-client/.env -n $(MCP_NAMESPACE)

deploy:
	@echo "INFO: Applying manifest and rolling out server/client in order..."
	$(MAKE) create-runtime-secrets
	kubectl --kubeconfig $(KUBECONFIG_PATH) apply -f $(MANIFEST_FILE)
	@SERVER_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path) && \
	CLIENT_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path) && \
	echo "INFO: Setting server image to $$SERVER_IMAGE_PATH:$(IMAGE_VERSION)" && \
	echo "INFO: Setting client image to $$CLIENT_IMAGE_PATH:$(CLIENT_IMAGE_VERSION)" && \
	kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) set image deployment/fastmcp-server fastmcp-server=$$SERVER_IMAGE_PATH:$(IMAGE_VERSION) && \
	kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) set image deployment/fastmcp-client fastmcp-client=$$CLIENT_IMAGE_PATH:$(CLIENT_IMAGE_VERSION)
	kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) rollout restart deployment/fastmcp-server
	kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) rollout status deployment/fastmcp-server --timeout=300s
	$(MAKE) KUBECONFIG_PATH=$(KUBECONFIG_PATH) sync-client-mcp-public-url
	$(MAKE) KUBECONFIG_PATH=$(KUBECONFIG_PATH) print-service-urls

mcp-server:
	@echo "mcp url for your client is"
	kubectl --kubeconfig $(KUBECONFIG_PATH) get services fastmcp-server -n $(MCP_NAMESPACE) -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

sync-client-mcp-public-url:
	@echo "INFO: Discovering public MCP URL from fastmcp-server LoadBalancer..."
	@set -e; \
	START_TS=$$(date +%s); \
	ADDR=""; \
	while true; do \
		IP=$$(kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) get svc fastmcp-server -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true); \
		HOST=$$(kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) get svc fastmcp-server -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true); \
		ADDR=$${IP:-$$HOST}; \
		if [ -n "$$ADDR" ]; then \
			break; \
		fi; \
		NOW_TS=$$(date +%s); \
		if [ $$((NOW_TS - START_TS)) -ge $(LB_READY_TIMEOUT) ]; then \
			echo "ERROR: Timed out waiting for fastmcp-server LoadBalancer address after $(LB_READY_TIMEOUT)s."; \
			exit 1; \
		fi; \
		echo "INFO: Waiting for fastmcp-server LoadBalancer address..."; \
		sleep 5; \
	done; \
	MCP_PUBLIC_URL="http://$$ADDR/mcp/"; \
	echo "INFO: Setting fastmcp-client MCP_PUBLIC_URL=$$MCP_PUBLIC_URL"; \
	kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) set env deployment/fastmcp-client MCP_PUBLIC_URL="$$MCP_PUBLIC_URL"; \
	echo "INFO: Client UI will now show MCP URL as $$MCP_PUBLIC_URL"

print-service-urls:
	@set -e; \
	SERVER_IP=$$(kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) get svc fastmcp-server -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true); \
	CLIENT_IP=$$(kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) get svc fastmcp-client -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true); \
	if [ -z "$$SERVER_IP" ]; then \
		SERVER_IP=$$(kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) get svc fastmcp-server -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true); \
	fi; \
	if [ -z "$$CLIENT_IP" ]; then \
		CLIENT_IP=$$(kubectl --kubeconfig $(KUBECONFIG_PATH) -n $(MCP_NAMESPACE) get svc fastmcp-client -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true); \
	fi; \
	echo "MCP Server IP: $$SERVER_IP"; \
	echo "MCP URL      : http://$$SERVER_IP/mcp/"; \
	echo "Health       : http://$$SERVER_IP/health"; \
	echo "MCP Client IP: $$CLIENT_IP"; \
	echo "Client UI    : http://$$CLIENT_IP/"

# ------------------------------------------------------------------------------
# LOCAL DEVELOPMENT TARGETS
# ------------------------------------------------------------------------------
# These targets help run the MCP audio server/client locally with per-service .env files.

dev-server-setup:
	@echo "INFO: Setting up MCP audio server virtualenv..."
	python3 -m venv mcp-audio/.venv
	. mcp-audio/.venv/bin/activate && pip install --upgrade pip && pip install -r mcp-audio/requirements.txt

dev-server-run:
	@echo "INFO: Running MCP audio server locally..."
	cd mcp-audio && \
	if [ ! -f .env ]; then echo "Missing mcp-audio/.env. Copy from .env.example"; exit 1; fi && \
	set -a && . ./.env && set +a && \
	. .venv/bin/activate && python app.py

dev-server-run-bg:
	@echo "INFO: Running MCP audio server locally (background)..."
	cd mcp-audio && \
	if [ ! -f .env ]; then echo "Missing mcp-audio/.env. Copy from .env.example"; exit 1; fi && \
	set -a && . ./.env && set +a && \
	. .venv/bin/activate && nohup python app.py > server.log 2>&1 &

dev-client-setup:
	@echo "INFO: Setting up MCP client virtualenv..."
	python3 -m venv mcp-client/.venv
	. mcp-client/.venv/bin/activate && pip install --upgrade pip && pip install -r mcp-client/requirements.txt

dev-client-run:
	@echo "INFO: Running MCP client locally..."
	cd mcp-client && \
	if [ ! -f .env ]; then echo "Missing mcp-client/.env. Copy from .env.example"; exit 1; fi && \
	. .venv/bin/activate && python app.py

dev-client-run-bg:
	@echo "INFO: Running MCP client locally (background)..."
	cd mcp-client && \
	if [ ! -f .env ]; then echo "Missing mcp-client/.env. Copy from .env.example"; exit 1; fi && \
	. .venv/bin/activate && nohup python app.py > client.log 2>&1 &

destroy-manifest: 
	kubectl --kubeconfig $(KUBECONFIG_PATH) delete -f $(MANIFEST_FILE)


# Destroys the terraform configuration to build infrastructure.
empty-speech-bucket:
	@echo "INFO: Attempting speech bucket cleanup before destroy (safe/no-fail)..."
	@NS=$$(oci os ns get --query 'data' --raw-output 2>/dev/null || true); \
	OCI_REGION_VALUE=$$(terraform -chdir=$(TF_DIR) output -raw oci_region 2>/dev/null || awk -F'=' '/^[[:space:]]*region[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' $(TF_DIR)/$(TF_VAR_FILE)); \
	if [ -z "$$NS" ]; then \
		echo "WARN: Could not resolve OCI namespace. Skipping bucket cleanup."; \
		exit 0; \
	fi; \
	BUCKET=$$(terraform -chdir=$(TF_DIR) output -raw speech_bucket_name 2>/dev/null || true); \
	if [ -z "$$BUCKET" ]; then \
		BUCKET="$(SPEECH_BUCKET_NAME)"; \
	fi; \
	if [ -z "$$BUCKET" ]; then \
		echo "WARN: Could not resolve speech bucket name. Skipping bucket cleanup."; \
		exit 0; \
	fi; \
	echo "INFO: Namespace=$$NS Bucket=$$BUCKET Region=$$OCI_REGION_VALUE"; \
	oci os object bulk-delete -ns "$$NS" -bn "$$BUCKET" --force --region "$$OCI_REGION_VALUE" >/dev/null 2>&1 || true; \
	oci os object bulk-delete -ns "$$NS" -bn "$$BUCKET" --force --region "$$OCI_REGION_VALUE" >/dev/null 2>&1 || true; \
	echo "INFO: Bucket cleanup step completed (or bucket already empty)."

destroy-terraform: 
	@echo "INFO: Destroying Terraform configuration..."
	@if [ "$(SKIP_BUCKET_CLEANUP)" != "true" ]; then \
		$(MAKE) empty-speech-bucket; \
	else \
		echo "INFO: SKIP_BUCKET_CLEANUP=true, skipping Object Storage cleanup"; \
	fi
	terraform -chdir=$(TF_DIR) destroy -var-file=$(TF_VAR_FILE) -auto-approve

destroy-k8s:
	@echo "INFO: Deleting Kubernetes resources for fresh run..."
	@kubectl delete -f $(MANIFEST_FILE) --ignore-not-found || true
	@kubectl -n $(MCP_NAMESPACE) delete svc fastmcp-server fastmcp-client --ignore-not-found || true
	@echo "INFO: Waiting for LoadBalancer services/VNIC references to be released..."
	@START_TS=$$(date +%s); \
	TIMEOUT=120; \
	while true; do \
		LB_COUNT=$$(kubectl -n $(MCP_NAMESPACE) get svc -o jsonpath='{range .items[*]}{.spec.type}{"\n"}{end}' 2>/dev/null | grep -c '^LoadBalancer$$' || true); \
		if [ "$$LB_COUNT" = "0" ]; then \
			echo "INFO: No LoadBalancer services remain in namespace $(MCP_NAMESPACE)."; \
			break; \
		fi; \
		NOW_TS=$$(date +%s); \
		if [ $$((NOW_TS - START_TS)) -ge $$TIMEOUT ]; then \
			echo "WARN: Timed out waiting for LB service cleanup after $${TIMEOUT}s. Continuing with namespace deletion."; \
			break; \
		fi; \
		echo "INFO: Still waiting on $$LB_COUNT LoadBalancer service(s)..."; \
		sleep 5; \
	done
	@kubectl -n $(MCP_NAMESPACE) delete secret mcp-secrets mcp-client-secrets ocirsecret --ignore-not-found || true
	@kubectl delete ns $(MCP_NAMESPACE) --ignore-not-found || true

destroy-all-fresh: destroy-k8s destroy-terraform
	@echo "INFO: Fresh destroy complete"

deploy-fresh-guided:
	@set -e; \
	echo "INFO: Running guided fresh deployment"; \
	TFVARS_PATH="$(TF_DIR)/$(TF_VAR_FILE)"; \
	DEFAULT_TENANCY_OCID="$(TENANCY_OCID)"; \
	DEFAULT_COMPARTMENT_OCID="$(COMPARTMENT_OCID)"; \
	DEFAULT_REGION="$(REGION)"; \
	if [ -f "$$TFVARS_PATH" ]; then \
		TFVARS_TENANCY=$$(awk -F'=' '/^[[:space:]]*tenancy_ocid[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' $$TFVARS_PATH); \
		TFVARS_COMPARTMENT=$$(awk -F'=' '/^[[:space:]]*compartment_id[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' $$TFVARS_PATH); \
		TFVARS_REGION=$$(awk -F'=' '/^[[:space:]]*region[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' $$TFVARS_PATH); \
		if { [ -z "$$DEFAULT_TENANCY_OCID" ] || [ "$$DEFAULT_TENANCY_OCID" = "<TENANCY_OCID>" ]; } && [ -n "$$TFVARS_TENANCY" ]; then DEFAULT_TENANCY_OCID="$$TFVARS_TENANCY"; fi; \
		if { [ -z "$$DEFAULT_COMPARTMENT_OCID" ] || [ "$$DEFAULT_COMPARTMENT_OCID" = "<COMPARTMENT_OCID>" ]; } && [ -n "$$TFVARS_COMPARTMENT" ]; then DEFAULT_COMPARTMENT_OCID="$$TFVARS_COMPARTMENT"; fi; \
		if { [ -z "$$DEFAULT_REGION" ] || [ "$$DEFAULT_REGION" = "<OCI_REGION>" ]; } && [ -n "$$TFVARS_REGION" ]; then DEFAULT_REGION="$$TFVARS_REGION"; fi; \
	fi; \
	TENANCY_OCID="$$DEFAULT_TENANCY_OCID"; \
	if [ -z "$$TENANCY_OCID" ] || [ "$$TENANCY_OCID" = "<TENANCY_OCID>" ]; then \
		read -p "Enter TENANCY_OCID: " TENANCY_OCID; \
	else \
		echo "INFO: Using TENANCY_OCID from terraform.tfvars/Makefile"; \
	fi; \
	if [ -z "$$TENANCY_OCID" ] || [ "$$TENANCY_OCID" = "<TENANCY_OCID>" ]; then echo "ERROR: TENANCY_OCID is required"; exit 1; fi; \
	COMPARTMENT_OCID="$$DEFAULT_COMPARTMENT_OCID"; \
	if [ -z "$$COMPARTMENT_OCID" ] || [ "$$COMPARTMENT_OCID" = "<COMPARTMENT_OCID>" ]; then \
		read -p "Enter COMPARTMENT_OCID: " COMPARTMENT_OCID; \
	else \
		echo "INFO: Using COMPARTMENT_OCID from terraform.tfvars"; \
	fi; \
	if [ -z "$$COMPARTMENT_OCID" ] || [ "$$COMPARTMENT_OCID" = "<COMPARTMENT_OCID>" ]; then echo "ERROR: COMPARTMENT_OCID is required"; exit 1; fi; \
	OCI_REGION="$$DEFAULT_REGION"; \
	if [ -z "$$OCI_REGION" ] || [ "$$OCI_REGION" = "<OCI_REGION>" ]; then \
		read -p "Enter OCI region: " OCI_REGION; \
	else \
		echo "INFO: Using region $$OCI_REGION"; \
	fi; \
	if [ -z "$$OCI_REGION" ] || [ "$$OCI_REGION" = "<OCI_REGION>" ]; then echo "ERROR: OCI region is required"; exit 1; fi; \
	echo "INFO: Syncing terraform/$(TF_VAR_FILE) using TENANCY_OCID=$$TENANCY_OCID COMPARTMENT_OCID=$$COMPARTMENT_OCID REGION=$$OCI_REGION"; \
	$(MAKE) update-tfvars TENANCY_OCID="$$TENANCY_OCID" COMPARTMENT_OCID="$$COMPARTMENT_OCID" REGION="$$OCI_REGION"; \
	$(MAKE) terraform-init-resilient; \
	terraform -chdir=$(TF_DIR) apply -var-file=$(TF_VAR_FILE) -auto-approve; \
	IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path); \
	CLIENT_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path); \
	OCI_NAMESPACE=$$(terraform -chdir=$(TF_DIR) output -raw oci_namespace); \
	SPEECH_BUCKET=$$(terraform -chdir=$(TF_DIR) output -raw speech_bucket_name); \
	CLUSTER_ID=$$(terraform -chdir=$(TF_DIR) output -raw cluster_id); \
	DOCKER_USER_DEFAULT="$(DOCKER_USER)"; \
	if [ -n "$$DOCKER_USER_DEFAULT" ]; then \
		echo "INFO: Using DOCKER_USER from Makefile: $$DOCKER_USER_DEFAULT"; \
		DOCKER_USER="$$DOCKER_USER_DEFAULT"; \
	else \
		read -p "Enter OCIR username [example: $$OCI_NAMESPACE/<your-oci-username>]: " DOCKER_USER; \
		if [ -z "$$DOCKER_USER" ]; then read -p "Enter OCIR username [or $$OCI_NAMESPACE/oracleidentitycloudservice/<idcs-username>]: " DOCKER_USER; fi; \
	fi; \
	if [ -z "$$DOCKER_USER" ]; then echo "ERROR: DOCKER_USER is required"; exit 1; fi; \
	if ! echo "$$DOCKER_USER" | grep -q '/'; then DOCKER_USER="$$OCI_NAMESPACE/$$DOCKER_USER"; fi; \
	DOCKER_PASS_DEFAULT="$(DOCKER_PASS)"; \
	if [ -n "$$DOCKER_PASS_DEFAULT" ]; then \
		echo "INFO: Using DOCKER_PASS from Makefile"; \
		DOCKER_PASS="$$DOCKER_PASS_DEFAULT"; \
	else \
		read -s -p "Enter OCIR auth token: " DOCKER_PASS; echo; \
	fi; \
	if [ -z "$$DOCKER_PASS" ]; then echo "ERROR: DOCKER_PASS is required"; exit 1; fi; \
	REGISTRY_HOST=$$(echo $$IMAGE_PATH | awk -F/ '{print $$1}'); \
	echo "INFO: Verifying OCIR login for $$DOCKER_USER at $$REGISTRY_HOST"; \
	if ! echo "$$DOCKER_PASS" | docker login --username "$$DOCKER_USER" --password-stdin $$REGISTRY_HOST; then \
		echo "ERROR: OCIR login failed. Use one of:"; \
		echo "  1) $$OCI_NAMESPACE/<oci-username>"; \
		echo "  2) $$OCI_NAMESPACE/oracleidentitycloudservice/<idcs-username>"; \
		echo "and ensure the auth token belongs to the same user."; \
		exit 1; \
	fi; \
	read -p "Enter IMAGE_TAG [$(IMAGE_VERSION)]: " IMAGE_TAG; \
	IMAGE_TAG=$${IMAGE_TAG:-$(IMAGE_VERSION)}; \
	echo "INFO: Using IMAGE_TAG=$$IMAGE_TAG"; \
	oci ce cluster create-kubeconfig --cluster-id $$CLUSTER_ID --file $(KUBECONFIG_PATH) --region $$OCI_REGION --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT; \
	RENDERED_MANIFEST=/tmp/mcp-manifest-$$(date +%Y%m%d%H%M%S).yaml; \
	cp $(MANIFEST_FILE) $$RENDERED_MANIFEST; \
	echo "INFO: Placeholder check before replacement (copied manifest)"; \
	if grep -qE '<mcp-audio-image-tag>|<mcp-server-image-tag>|<mcp-client-image-tag>|<Compartment_OCID>|<OCI_NAMESPACE>|<SPEECH_BUCKET>|<Notification_Topic_OCID>' $$RENDERED_MANIFEST; then \
		echo "INFO: Placeholders found before replacement:"; \
		grep -nE '<mcp-audio-image-tag>|<mcp-server-image-tag>|<mcp-client-image-tag>|<Compartment_OCID>|<OCI_NAMESPACE>|<SPEECH_BUCKET>|<Notification_Topic_OCID>' $$RENDERED_MANIFEST; \
	else \
		echo "WARN: No placeholders found before replacement (manifest may already be mutated)."; \
	fi; \
	$(SED_INPLACE) "s|<mcp-audio-image-tag>|$$IMAGE_PATH:$$IMAGE_TAG|g" $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<mcp-server-image-tag>|$$IMAGE_PATH:$$IMAGE_TAG|g" $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<mcp-client-image-tag>|$$CLIENT_IMAGE_PATH:$$IMAGE_TAG|g" $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<Compartment_OCID>|$$COMPARTMENT_OCID|g" $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<OCI_NAMESPACE>|$$OCI_NAMESPACE|g" $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<SPEECH_BUCKET>|$$SPEECH_BUCKET|g" $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<Notification_Topic_OCID>||g" $$RENDERED_MANIFEST; \
	if grep -qE '<mcp-audio-image-tag>|<mcp-server-image-tag>|<mcp-client-image-tag>|<Compartment_OCID>|<OCI_NAMESPACE>|<SPEECH_BUCKET>|<Notification_Topic_OCID>' $$RENDERED_MANIFEST; then \
		echo "ERROR: Unreplaced placeholders found in rendered manifest: $$RENDERED_MANIFEST"; \
		grep -nE '<mcp-audio-image-tag>|<mcp-server-image-tag>|<mcp-client-image-tag>|<Compartment_OCID>|<OCI_NAMESPACE>|<SPEECH_BUCKET>|<Notification_Topic_OCID>' $$RENDERED_MANIFEST; \
		exit 1; \
	fi; \
	echo "INFO: Rendered server image: $$IMAGE_PATH:$$IMAGE_TAG"; \
	echo "INFO: Rendered client image: $$CLIENT_IMAGE_PATH:$$IMAGE_TAG"; \
	grep -n "image:" $$RENDERED_MANIFEST; \
	kubectl create ns $(MCP_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -; \
	REGISTRY_HOST=$$(echo $$IMAGE_PATH | awk -F/ '{print $$1}'); \
	echo "INFO: Logging into $$REGISTRY_HOST"; \
	echo "$$DOCKER_PASS" | docker login --username "$$DOCKER_USER" --password-stdin $$REGISTRY_HOST; \
	echo "INFO: Building image $$IMAGE_PATH:$$IMAGE_TAG"; \
	docker build --platform linux/amd64 -t $$IMAGE_PATH:$$IMAGE_TAG mcp-audio/; \
	echo "INFO: Building client image $$CLIENT_IMAGE_PATH:$$IMAGE_TAG"; \
	docker build --platform linux/amd64 -t $$CLIENT_IMAGE_PATH:$$IMAGE_TAG mcp-client/; \
	echo "INFO: Pushing image $$IMAGE_PATH:$$IMAGE_TAG"; \
	ATTEMPT=1; MAX_ATTEMPTS=$(OCIR_PUSH_RETRY_ATTEMPTS); DELAY=$(OCIR_PUSH_RETRY_DELAY); \
	while [ $$ATTEMPT -le $$MAX_ATTEMPTS ]; do \
		echo "INFO: docker push attempt $$ATTEMPT/$$MAX_ATTEMPTS -> $$IMAGE_PATH:$$IMAGE_TAG"; \
		if docker push $$IMAGE_PATH:$$IMAGE_TAG; then break; fi; \
		if [ $$ATTEMPT -ge $$MAX_ATTEMPTS ]; then echo "ERROR: docker push failed after $$MAX_ATTEMPTS attempts -> $$IMAGE_PATH:$$IMAGE_TAG"; exit 1; fi; \
		echo "WARN: docker push failed. Retrying in $${DELAY}s (possible OCIR/IAM propagation delay)..."; \
		sleep $$DELAY; \
		ATTEMPT=$$((ATTEMPT + 1)); \
	done; \
	echo "INFO: Pushing client image $$CLIENT_IMAGE_PATH:$$IMAGE_TAG"; \
	ATTEMPT=1; MAX_ATTEMPTS=$(OCIR_PUSH_RETRY_ATTEMPTS); DELAY=$(OCIR_PUSH_RETRY_DELAY); \
	while [ $$ATTEMPT -le $$MAX_ATTEMPTS ]; do \
		echo "INFO: docker push attempt $$ATTEMPT/$$MAX_ATTEMPTS -> $$CLIENT_IMAGE_PATH:$$IMAGE_TAG"; \
		if docker push $$CLIENT_IMAGE_PATH:$$IMAGE_TAG; then break; fi; \
		if [ $$ATTEMPT -ge $$MAX_ATTEMPTS ]; then echo "ERROR: docker push failed after $$MAX_ATTEMPTS attempts -> $$CLIENT_IMAGE_PATH:$$IMAGE_TAG"; exit 1; fi; \
		echo "WARN: docker push failed. Retrying in $${DELAY}s (possible OCIR/IAM propagation delay)..."; \
		sleep $$DELAY; \
		ATTEMPT=$$((ATTEMPT + 1)); \
	done; \
	kubectl -n $(MCP_NAMESPACE) delete secret ocirsecret --ignore-not-found; \
	kubectl create secret docker-registry ocirsecret --docker-server=$$REGISTRY_HOST --docker-username="$$DOCKER_USER" --docker-password="$$DOCKER_PASS" --docker-email="$(DOCKER_EMAIL)" --namespace $(MCP_NAMESPACE); \
	kubectl -n $(MCP_NAMESPACE) delete secret mcp-secrets --ignore-not-found; \
	kubectl create secret generic mcp-secrets --from-env-file=$(CURDIR)/mcp-audio/.env -n $(MCP_NAMESPACE); \
	if [ ! -f "$(CURDIR)/mcp-client/.env" ]; then \
		echo "WARN: Missing mcp-client/.env; creating it from mcp-client/.env.example"; \
		cp "$(CURDIR)/mcp-client/.env.example" "$(CURDIR)/mcp-client/.env"; \
	fi; \
	kubectl -n $(MCP_NAMESPACE) delete secret mcp-client-secrets --ignore-not-found; \
	kubectl create secret generic mcp-client-secrets --from-env-file=$(CURDIR)/mcp-client/.env -n $(MCP_NAMESPACE); \
	echo "INFO: Rendered manifest kept for reference at $$RENDERED_MANIFEST"; \
	kubectl apply -f $$RENDERED_MANIFEST; \
	echo "INFO: Enforcing server/client deployment images explicitly"; \
	kubectl -n $(MCP_NAMESPACE) set image deployment/fastmcp-server fastmcp-server=$$IMAGE_PATH:$$IMAGE_TAG; \
	kubectl -n $(MCP_NAMESPACE) set image deployment/fastmcp-client fastmcp-client=$$CLIENT_IMAGE_PATH:$$IMAGE_TAG; \
	kubectl -n $(MCP_NAMESPACE) rollout restart deployment/fastmcp-server; \
	kubectl -n $(MCP_NAMESPACE) rollout status deployment/fastmcp-server --timeout=300s; \
	$(MAKE) KUBECONFIG_PATH=$(KUBECONFIG_PATH) sync-client-mcp-public-url; \
	$(MAKE) KUBECONFIG_PATH=$(KUBECONFIG_PATH) print-service-urls

validate-fresh:
	@echo "INFO: Validating tfvars / Makefile values and placeholder replacement"
	@TFVARS_PATH="$(TF_DIR)/$(TF_VAR_FILE)"; \
	if [ ! -f "$$TFVARS_PATH" ]; then \
		echo "ERROR: Missing $$TFVARS_PATH"; exit 1; \
	fi; \
	TF_TENANCY=$$(awk -F'=' '/^[[:space:]]*tenancy_ocid[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH"); \
	TF_COMPARTMENT=$$(awk -F'=' '/^[[:space:]]*compartment_id[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH"); \
	TF_REGION=$$(awk -F'=' '/^[[:space:]]*region[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' "$$TFVARS_PATH"); \
	MK_TENANCY="$(TENANCY_OCID)"; MK_TENANCY=$${MK_TENANCY#\"}; MK_TENANCY=$${MK_TENANCY%\"}; \
	MK_COMPARTMENT="$(COMPARTMENT_OCID)"; MK_COMPARTMENT=$${MK_COMPARTMENT#\"}; MK_COMPARTMENT=$${MK_COMPARTMENT%\"}; \
	MK_REGION="$(REGION)"; MK_REGION=$${MK_REGION#\"}; MK_REGION=$${MK_REGION%\"}; \
	FINAL_TENANCY="$$TF_TENANCY"; FINAL_COMPARTMENT="$$TF_COMPARTMENT"; FINAL_REGION="$$TF_REGION"; \
	if [ -z "$$FINAL_TENANCY" ] || [ "$$FINAL_TENANCY" = "<TENANCY_OCID>" ]; then \
		if [ -n "$$MK_TENANCY" ] && [ "$$MK_TENANCY" != "ocid1.tenancy.oc1.." ]; then FINAL_TENANCY="$$MK_TENANCY"; echo "INFO: Using TENANCY_OCID from Makefile"; \
		else echo "ERROR: tenancy_ocid missing in terraform.tfvars and no real TENANCY_OCID found in Makefile"; exit 1; fi; \
	fi; \
	if [ -z "$$FINAL_COMPARTMENT" ] || [ "$$FINAL_COMPARTMENT" = "<COMPARTMENT_OCID>" ]; then \
		if [ -n "$$MK_COMPARTMENT" ] && [ "$$MK_COMPARTMENT" != "ocid1.compartment.oc1.." ]; then FINAL_COMPARTMENT="$$MK_COMPARTMENT"; echo "INFO: Using COMPARTMENT_OCID from Makefile"; \
		else echo "ERROR: compartment_id missing in terraform.tfvars and no real COMPARTMENT_OCID found in Makefile"; exit 1; fi; \
	fi; \
	if [ -z "$$FINAL_REGION" ] || [ "$$FINAL_REGION" = "<OCI_REGION>" ]; then \
		if [ -n "$$MK_REGION" ]; then FINAL_REGION="$$MK_REGION"; echo "INFO: Using REGION from Makefile"; \
		else echo "ERROR: region missing in terraform.tfvars and no REGION found in Makefile"; exit 1; fi; \
	fi; \
	echo "INFO: Final tenancy_ocid       = $$FINAL_TENANCY"; \
	echo "INFO: Final compartment_id     = $$FINAL_COMPARTMENT"; \
	echo "INFO: Final region             = $$FINAL_REGION"; \
	TF_OCI_NS=$$(terraform -chdir=$(TF_DIR) output -raw oci_namespace 2>/dev/null || true); \
	TF_BUCKET=$$(terraform -chdir=$(TF_DIR) output -raw speech_bucket_name 2>/dev/null || true); \
	TF_SERVER_IMAGE=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path 2>/dev/null || true); \
	TF_CLIENT_IMAGE=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path 2>/dev/null || true); \
	EFFECTIVE_OCI_NS=$${TF_OCI_NS:-$(OCI_NAMESPACE)}; \
	EFFECTIVE_BUCKET="$$TF_BUCKET"; \
	RENDERED_MANIFEST=/tmp/mcp-validate-manifest-$$.yaml; \
	cp $(MANIFEST_FILE) $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<Compartment_OCID>|$$FINAL_COMPARTMENT|g" $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<OCI_NAMESPACE>|$$EFFECTIVE_OCI_NS|g" $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<SPEECH_BUCKET>|$$EFFECTIVE_BUCKET|g" $$RENDERED_MANIFEST; \
	$(SED_INPLACE) "s|<Notification_Topic_OCID>||g" $$RENDERED_MANIFEST; \
	if [ -n "$$TF_SERVER_IMAGE" ]; then \
		$(SED_INPLACE) "s|<mcp-server-image-tag>|$$TF_SERVER_IMAGE:$(IMAGE_VERSION)|g" $$RENDERED_MANIFEST; \
		$(SED_INPLACE) "s|<mcp-audio-image-tag>|$$TF_SERVER_IMAGE:$(IMAGE_VERSION)|g" $$RENDERED_MANIFEST; \
	fi; \
	if [ -n "$$TF_CLIENT_IMAGE" ]; then \
		$(SED_INPLACE) "s|<mcp-client-image-tag>|$$TF_CLIENT_IMAGE:$(CLIENT_IMAGE_VERSION)|g" $$RENDERED_MANIFEST; \
	fi; \
	if grep -nE '<mcp-server-image-tag>|<mcp-audio-image-tag>|<mcp-client-image-tag>|<Compartment_OCID>|<OCI_NAMESPACE>|<SPEECH_BUCKET>|<Notification_Topic_OCID>' $$RENDERED_MANIFEST; then \
		echo "ERROR: validate-fresh found unresolved placeholders after replacement attempt."; \
		echo "ERROR: Fix values in terraform.tfvars and/or Makefile, then re-run make validate-fresh"; \
		exit 1; \
	else \
		echo "SUCCESS: validate-fresh passed. You can go ahead with make deploy-fresh-guided"; \
	fi; \
	kubectl -n $(MCP_NAMESPACE) get deploy,pods,svc -o wide || true

# QUICK REDEPLOY TARGET
# ------------------------------------------------------------------------------
# Minimal inputs needed:
# - DOCKER_USER=<namespace>/<oci-username>
# - DOCKER_PASS=<oci-auth-token>
# Optional:
# - IMAGE_VERSION=latest (default already set at top as latest)
#
# Example:
quick-redeploy:
	@echo "INFO: Resolving OCIR repository from Terraform output..."
	@OCI_REGION_VALUE=$$(terraform -chdir=$(TF_DIR) output -raw oci_region 2>/dev/null || awk -F'=' '/^[[:space:]]*region[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' $(TF_DIR)/$(TF_VAR_FILE)) && \
	IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_path) && \
	CLIENT_IMAGE_PATH=$$(terraform -chdir=$(TF_DIR) output -raw mcp_client_repository_path) && \
	REGISTRY_HOST=$$(echo $$IMAGE_PATH | awk -F/ '{print $$1}') && \
	NS=$$(echo $$IMAGE_PATH | awk -F/ '{print $$2}') && \
	EFFECTIVE_DOCKER_USER="$(DOCKER_USER)" && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then \
		echo "INFO: DOCKER_USER not provided."; \
		echo "INFO: Enter OCIR username in format <namespace>/<username>"; \
		read -p "DOCKER_USER [example: $$NS/<your-oci-username>]: " EFFECTIVE_DOCKER_USER; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_USER" ]; then \
		echo "ERROR: DOCKER_USER is required"; \
		exit 1; \
	fi && \
	if ! echo "$$EFFECTIVE_DOCKER_USER" | grep -q '/'; then \
		EFFECTIVE_DOCKER_USER="$$NS/$$EFFECTIVE_DOCKER_USER"; \
		echo "INFO: Using normalized docker username $$EFFECTIVE_DOCKER_USER"; \
	fi && \
	EFFECTIVE_DOCKER_PASS="$(DOCKER_PASS)" && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then \
		echo "INFO: DOCKER_PASS not provided."; \
		read -s -p "DOCKER_PASS (OCIR auth token): " EFFECTIVE_DOCKER_PASS; \
		echo; \
	fi && \
	if [ -z "$$EFFECTIVE_DOCKER_PASS" ]; then \
		echo "ERROR: DOCKER_PASS is required"; \
		exit 1; \
	fi && \
	echo "INFO: Resolved OCI region $$OCI_REGION_VALUE" && \
	echo "INFO: Using server image $$IMAGE_PATH:$(IMAGE_VERSION)" && \
	echo "INFO: Using client image $$CLIENT_IMAGE_PATH:$(CLIENT_IMAGE_VERSION)" && \
	echo "INFO: Using docker username $$EFFECTIVE_DOCKER_USER" && \
	echo "INFO: Logging into $$REGISTRY_HOST" && \
	echo "$$EFFECTIVE_DOCKER_PASS" | docker login --username "$$EFFECTIVE_DOCKER_USER" --password-stdin $$REGISTRY_HOST && \
	echo "INFO: Ensuring namespace $(MCP_NAMESPACE) exists" && \
	kubectl create namespace $(MCP_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f - && \
	if ! kubectl -n $(MCP_NAMESPACE) get deployment fastmcp-server >/dev/null 2>&1 || ! kubectl -n $(MCP_NAMESPACE) get deployment fastmcp-client >/dev/null 2>&1; then \
		echo "INFO: fastmcp deployments missing; rendering and applying manifest bootstrap"; \
		OCI_NAMESPACE_VALUE=$$(terraform -chdir=$(TF_DIR) output -raw oci_namespace); \
		SPEECH_BUCKET_VALUE=$$(terraform -chdir=$(TF_DIR) output -raw speech_bucket_name); \
		COMPARTMENT_VALUE="$(COMPARTMENT_OCID)"; \
		if [ -z "$$COMPARTMENT_VALUE" ]; then \
			COMPARTMENT_VALUE=$$(awk -F'=' '/^[[:space:]]*compartment_id[[:space:]]*=/{gsub(/["[:space:]]/,"",$$2); print $$2; exit}' $(TF_DIR)/$(TF_VAR_FILE)); \
		fi; \
		if [ -z "$$COMPARTMENT_VALUE" ]; then \
			echo "ERROR: COMPARTMENT_OCID is required for bootstrap manifest rendering"; \
			exit 1; \
		fi; \
		RENDERED_MANIFEST=/tmp/mcp-manifest-bootstrap-$$(date +%Y%m%d%H%M%S).yaml; \
		cp $(MANIFEST_FILE) $$RENDERED_MANIFEST; \
		$(SED_INPLACE) "s|<mcp-audio-image-tag>|$$IMAGE_PATH:$(IMAGE_VERSION)|g" $$RENDERED_MANIFEST; \
		$(SED_INPLACE) "s|<mcp-server-image-tag>|$$IMAGE_PATH:$(IMAGE_VERSION)|g" $$RENDERED_MANIFEST; \
		$(SED_INPLACE) "s|<mcp-client-image-tag>|$$CLIENT_IMAGE_PATH:$(CLIENT_IMAGE_VERSION)|g" $$RENDERED_MANIFEST; \
		$(SED_INPLACE) "s|<Compartment_OCID>|$$COMPARTMENT_VALUE|g" $$RENDERED_MANIFEST; \
		$(SED_INPLACE) "s|<OCI_NAMESPACE>|$$OCI_NAMESPACE_VALUE|g" $$RENDERED_MANIFEST; \
		$(SED_INPLACE) "s|<SPEECH_BUCKET>|$$SPEECH_BUCKET_VALUE|g" $$RENDERED_MANIFEST; \
		$(SED_INPLACE) "s|<Notification_Topic_OCID>||g" $$RENDERED_MANIFEST; \
		if grep -qE '<mcp-audio-image-tag>|<mcp-server-image-tag>|<mcp-client-image-tag>|<Compartment_OCID>|<OCI_NAMESPACE>|<SPEECH_BUCKET>|<Notification_Topic_OCID>' $$RENDERED_MANIFEST; then \
			echo "ERROR: Unreplaced placeholders found in bootstrap manifest: $$RENDERED_MANIFEST"; \
			grep -nE '<mcp-audio-image-tag>|<mcp-server-image-tag>|<mcp-client-image-tag>|<Compartment_OCID>|<OCI_NAMESPACE>|<SPEECH_BUCKET>|<Notification_Topic_OCID>' $$RENDERED_MANIFEST; \
			exit 1; \
		fi; \
		kubectl --kubeconfig $(KUBECONFIG_PATH) apply -f $$RENDERED_MANIFEST; \
	fi && \
	echo "INFO: Recreating ocirsecret in namespace $(MCP_NAMESPACE)" && \
	kubectl -n $(MCP_NAMESPACE) delete secret ocirsecret --ignore-not-found && \
	kubectl create secret docker-registry ocirsecret \
	  --docker-server=$$REGISTRY_HOST \
	  --docker-username="$$EFFECTIVE_DOCKER_USER" \
	  --docker-password="$$EFFECTIVE_DOCKER_PASS" \
	  --docker-email="$(DOCKER_EMAIL)" \
	  --namespace $(MCP_NAMESPACE) && \
	echo "INFO: Building server image..." && \
	docker build --platform linux/amd64 -t $$IMAGE_PATH:$(IMAGE_VERSION) mcp-audio/ && \
	echo "INFO: Building client image..." && \
	docker build --platform linux/amd64 -t $$CLIENT_IMAGE_PATH:$(CLIENT_IMAGE_VERSION) mcp-client/ && \
	echo "INFO: Pushing server image..." && \
	ATTEMPT=1; MAX_ATTEMPTS=$(OCIR_PUSH_RETRY_ATTEMPTS); DELAY=$(OCIR_PUSH_RETRY_DELAY); \
	while [ $$ATTEMPT -le $$MAX_ATTEMPTS ]; do \
		echo "INFO: docker push attempt $$ATTEMPT/$$MAX_ATTEMPTS -> $$IMAGE_PATH:$(IMAGE_VERSION)"; \
		if docker push $$IMAGE_PATH:$(IMAGE_VERSION); then break; fi; \
		if [ $$ATTEMPT -ge $$MAX_ATTEMPTS ]; then echo "ERROR: docker push failed after $$MAX_ATTEMPTS attempts -> $$IMAGE_PATH:$(IMAGE_VERSION)"; exit 1; fi; \
		echo "WARN: docker push failed. Retrying in $${DELAY}s (possible OCIR/IAM propagation delay)..."; \
		sleep $$DELAY; \
		ATTEMPT=$$((ATTEMPT + 1)); \
	done && \
	echo "INFO: Pushing client image..." && \
	ATTEMPT=1; MAX_ATTEMPTS=$(OCIR_PUSH_RETRY_ATTEMPTS); DELAY=$(OCIR_PUSH_RETRY_DELAY); \
	while [ $$ATTEMPT -le $$MAX_ATTEMPTS ]; do \
		echo "INFO: docker push attempt $$ATTEMPT/$$MAX_ATTEMPTS -> $$CLIENT_IMAGE_PATH:$(CLIENT_IMAGE_VERSION)"; \
		if docker push $$CLIENT_IMAGE_PATH:$(CLIENT_IMAGE_VERSION); then break; fi; \
		if [ $$ATTEMPT -ge $$MAX_ATTEMPTS ]; then echo "ERROR: docker push failed after $$MAX_ATTEMPTS attempts -> $$CLIENT_IMAGE_PATH:$(CLIENT_IMAGE_VERSION)"; exit 1; fi; \
		echo "WARN: docker push failed. Retrying in $${DELAY}s (possible OCIR/IAM propagation delay)..."; \
		sleep $$DELAY; \
		ATTEMPT=$$((ATTEMPT + 1)); \
	done && \
	echo "INFO: Refreshing runtime secrets from mcp-audio/.env and mcp-client/.env..." && \
	$(MAKE) KUBECONFIG_PATH=$(KUBECONFIG_PATH) create-runtime-secrets && \
	echo "INFO: Updating deployment images and restarting rollout..." && \
	kubectl -n $(MCP_NAMESPACE) set image deployment/fastmcp-server fastmcp-server=$$IMAGE_PATH:$(IMAGE_VERSION) && \
	kubectl -n $(MCP_NAMESPACE) set image deployment/fastmcp-client fastmcp-client=$$CLIENT_IMAGE_PATH:$(CLIENT_IMAGE_VERSION) && \
	kubectl -n $(MCP_NAMESPACE) rollout restart deployment/fastmcp-server && \
	kubectl -n $(MCP_NAMESPACE) rollout status deployment/fastmcp-server --timeout=240s && \
	$(MAKE) KUBECONFIG_PATH=$(KUBECONFIG_PATH) sync-client-mcp-public-url && \
	kubectl -n $(MCP_NAMESPACE) rollout restart deployment/fastmcp-client && \
	kubectl -n $(MCP_NAMESPACE) rollout status deployment/fastmcp-client --timeout=200s && \
	$(MAKE) KUBECONFIG_PATH=$(KUBECONFIG_PATH) print-service-urls && \
	kubectl -n $(MCP_NAMESPACE) get pods -o wide
	
