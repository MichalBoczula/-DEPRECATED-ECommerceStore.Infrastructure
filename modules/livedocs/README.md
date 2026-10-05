# Stateless LiveDocs host

Inputs: `resource_group_name`, `environment_id` (shared Consumption environment),
`name`, `tags`, `image` (immutable mb0101/ecommerce-store-livedocs SHA256 digest).
Outputs: `id`, `portal_url`.

Single revision, 0.25 vCPU / 0.5 GiB, replicas 0..1, HTTPS external ingress to
HTTP 8080. Explicit `/health/live` startup/liveness and `/health/ready` readiness.
The pre-baked image needs no Azure secrets, runtime archive mounts or database.
Terraform owns the selected image; no competing revision workflow or ignored
image changes. Archive storage is outside application state in the operator
foundation root. See [deployment setup](../../docs/livedocs-deployment.md).
