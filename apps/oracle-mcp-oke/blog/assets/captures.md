# Screenshot Capture Checklist

Use this checklist while collecting CLI and console screenshots for the blog.

## Naming convention

- `step-01-*.png`, `step-02-*.png`, ...
- Keep resolution readable (prefer >= 1400px wide)
- Mask sensitive OCIDs, tokens, emails where needed

## Required captures

- [ ] `assets/step-01-architecture-overview.png`
  - Optional architecture diagram (draw.io / Excalidraw / OCI icons)
- [ ] `assets/step-02-terraform-apply-success.png`
  - Terraform apply completion summary
- [ ] `assets/step-03-cluster-kubeconfig.png`
  - `oci ce cluster create-kubeconfig` + `kubectl get nodes`
- [ ] `assets/step-04-ocir-login-build-push.png`
  - Docker login/build/push success snippets
- [ ] `assets/step-05-k8s-secret-and-deploy.png`
  - `kubectl create secret` + `kubectl apply`
- [ ] `assets/step-06-pod-running-service-ip.png`
  - `kubectl get pods -n mcp` and `kubectl get svc -n mcp`
- [ ] `assets/step-07-health-endpoint-check.png`
  - `curl -i http://<external-ip>/health` returns 200
- [ ] `assets/step-08-client-env-and-run.png`
  - client `.env` and `python app.py` output URL
- [ ] `assets/step-09-client-ui-result.png`
  - MCP client UI response (sentiment/transcription)
- [ ] `assets/step-10-troubleshooting-snippets.png`
  - representative errors and fixes section visuals

## Insertion map

- Intro/Architecture section → `step-01-architecture-overview.png`
- Provisioning section → `step-02-terraform-apply-success.png`
- Kubeconfig section → `step-03-cluster-kubeconfig.png`
- Container image section → `step-04-ocir-login-build-push.png`
- Kubernetes deploy section → `step-05-k8s-secret-and-deploy.png`
- Verification section → `step-06-pod-running-service-ip.png`, `step-07-health-endpoint-check.png`
- Client section → `step-08-client-env-and-run.png`, `step-09-client-ui-result.png`
- Troubleshooting section → `step-10-troubleshooting-snippets.png`