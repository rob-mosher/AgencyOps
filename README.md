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

### 3. Connect from claude.ai

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
