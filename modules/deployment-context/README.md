# Deployment context

Provides consistent names and tags for disposable development and portfolio
deployments. It has no provider dependencies, resources or state-store ownership.
Terraform must be at least `1.16.5` and below `2.0.0`.

| Input | Contract |
| --- | --- |
| `project` | Nonempty project label, up to 64 characters |
| `environment` | `development` or `portfolio` |
| `name_prefix` | 3–10 lowercase alphanumeric characters, starting with a letter |
| `location` | Azure region identifier; existence is checked during resource deployment |
| `cost_profile` | `minimal` (default), or `interview` for portfolio only |
| `tags` | Optional extra string tags; reserved names cannot be overridden, regardless of case |

Outputs are `name_prefix`, `location` and `tags`. Names end in `-dev` or
`-portfolio`. Mandatory tags are `project`, `environment`, `managedBy`,
`lifecycle` and `costProfile`. Lifecycle is `disposable`. Tags describe intent;
they do not enforce pricing or spending limits.

The output prefix is not a complete Azure resource name. Resource modules must
enforce their own length/character rules and add stable uniqueness for names
that are globally scoped, such as storage accounts. The retained development
resource-group name remains `rg-ecommerce-dev`, as defined by the foundation.

```hcl
module "context" {
  source      = "../../modules/deployment-context"
  project     = "ECommerceStore"
  environment = "development"
  name_prefix = "ecommerce"
  location    = "northeurope"
  tags        = { owner = "portfolio" }
}
```

Run `terraform init -backend=false` and `terraform test -test-directory=tests`
in this directory to check both environments and rejection of invalid inputs.
