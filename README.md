# AgencyOps

A cloud-hosted MCP server that enables AI entities to provision Azure infrastructure with bounded agency.

## How It Works

```
Human (optional) → Claude (claude.ai) → MCP Server (Azure) → Azure Resources
```

Claude calls the remote MCP server to declare infrastructure needs and provision within constitutional limits. Every decision is **deliberate** (plan before apply), **inspectable** (humans can audit), **purposeful** (all resources justify existence), and **bounded** (budgets are real constraints).

## MCP Tools

| Tool | Description |
|------|-------------|
| `query_backplane()` | Returns Azure subscription info, available SKUs, and budget status |
| `get_state()` | Queries Terraform state for currently provisioned Azure resources |
| `plan_resource()` | Generates a Terraform plan with policy validation and cost estimation |
| `apply_plan()` | Executes a previously generated plan, records cost to budget |
| `get_budget_status()` | Returns Azure budget tracking status |
| `delete_resource()` | Destroys an Azure resource via Terraform |
| `reconcile()` | Detects drift between Terraform state and Azure reality |

## Local Development

```bash
pip install -r requirements.txt

# Run tests
PYTHONPATH=. pytest tests/ -v

# Run server locally
python -m agencyops
```

## Azure Setup

### Prerequisites

- An Azure subscription with credits (e.g., Visual Studio Enterprise — $150/month)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- [Terraform](https://developer.hashicorp.com/terraform/downloads) installed

### 1. Verify your spending limit

Azure benefit subscriptions include a spending limit that suspends resources when credits run out (no surprise bills). Confirm it's enabled:

Azure Portal → Subscriptions → your subscription → "Spending limit: On"

### 2. Create a scoped service principal

Create a service principal with Contributor access **only** on the workloads resource group:

```bash
az login
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

# Create the workloads resource group first
az group create --name agencyops-workloads --location eastus

# Create service principal scoped to just this resource group
az ad sp create-for-rbac \
  --name agencyops-terraform \
  --role Contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/agencyops-workloads
```

Save the output — you'll need `appId`, `password`, and `tenant` for deployment.

### 3. Generate an API key

```bash
openssl rand -hex 32
```

## Deployment

### 1. Build and push container image

```bash
docker build -t agencyops .

# Tag and push to ACR
az acr login --name <acr-name>
docker tag agencyops <acr-name>.azurecr.io/agencyops:latest
docker push <acr-name>.azurecr.io/agencyops:latest
```

### 2. Deploy infrastructure

```bash
cd terraform/server
terraform init
terraform apply
```

### 3. Lock down access (recommended)

Restrict ingress to specific IP ranges by setting `allowed_ip_ranges` in your Terraform variables:

```hcl
# terraform.tfvars
allowed_ip_ranges = [
  { name = "my-ip",    ip_address_range = "203.0.113.10/32" },
  { name = "mcp-egress", ip_address_range = "..." },  # Anthropic MCP egress IPs
]
```

When this list is non-empty, all other IPs are denied. Check Anthropic's documentation for current MCP egress IP ranges.

### 4. Connect from claude.ai

Use the MCP server URL from `terraform output mcp_server_url` with your API key.

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AGENCYOPS_DATA_DIR` | `~/.agencyops` | State directory (plans, budget) |
| `AGENCYOPS_TERRAFORM_DIR` | `./terraform/workloads` | Path to workload Terraform configs |
| `AGENCYOPS_API_KEY` | | API key for authentication |
| `AGENCYOPS_AZURE_SUBSCRIPTION_ID` | | Azure subscription ID |
| `AGENCYOPS_AZURE_LOCATION` | `eastus` | Azure region |
| `AGENCYOPS_AZURE_RESOURCE_GROUP` | `agencyops-workloads` | Resource group for provisioned resources |
| `AGENCYOPS_AZURE_MONTHLY_LIMIT` | `150.0` | Monthly budget (USD) |

## Security

Three layers of protection:

| Layer | Mechanism | Scope |
|-------|-----------|-------|
| **Platform** | Azure spending limit | Hard-stops all charges when credits exhausted |
| **Network** | IP allowlisting (optional) | Restricts who can reach the endpoint |
| **Application** | API key + budget tracker | Authenticates requests, blocks provisioning at budget limit |

The service principal should have **Contributor on the workloads resource group only** — not the entire subscription. This limits blast radius if credentials are compromised.

## Architecture

```
agencyops/
├── server.py              # FastMCP server — 7 tools (streamable-http)
├── models.py              # Pydantic data models (Azure-focused)
├── budget_tracker.py      # Budget tracking with cost estimation
├── terraform_backend.py   # Terraform subprocess wrapper (Protocol-based)
└── __main__.py            # Entry point

terraform/
├── server/                # Deploys the MCP server itself (Container Apps, ACR, etc.)
└── workloads/             # What Claude provisions (Azure Container Instances)
```

## Philosophy

This isn't automation. This is **agency** — giving computational entities the ability to declare infrastructure needs and provision within constitutional limits.

## License

MIT
