# Architecture

## System Overview

AgencyOps is a cloud-hosted MCP server that mediates between AI entities and Azure infrastructure. It enforces the plan/apply separation pattern — every infrastructure change must be planned, validated against policies, and explicitly applied.

```
Human (optional)
    │
    ▼
Claude (claude.ai)
    │
    ▼ MCP (streamable-http)
AgencyOps Server (Azure Container Apps)
    ├── query_backplane()   ──► Azure subscription info + budget
    ├── get_state()         ──► Terraform show ──► Azure resources
    ├── plan_resource()     ──► Policy check + cost estimation ──► Terraform plan
    ├── apply_plan()        ──► Terraform apply + budget tracking
    ├── get_budget_status() ──► BudgetTracker (JSON file)
    ├── delete_resource()   ──► Terraform destroy + budget adjustment
    └── reconcile()         ──► Terraform state vs az container list
```

## Deployment Architecture

```
Azure Container Apps           Azure Container Instances
┌─────────────────────┐       ┌───────────────────────┐
│  AgencyOps MCP      │       │  Workload containers   │
│  ├── FastMCP        │──TF──►│  managed by Terraform  │
│  ├── Terraform CLI  │       │  (for_each pattern)    │
│  └── Azure CLI      │       └───────────────────────┘
│                     │
│  /data (Azure File  │       Azure Container Registry
│   Share volume)     │       ┌───────────────────────┐
│  ├── budget.json    │       │  agencyops:latest      │
│  ├── plans/         │       └───────────────────────┘
│  └── terraform.tfstate
└─────────────────────┘
```

## Subsystems

### Budget Tracker (`budget_tracker.py`)

Tracks estimated Azure spend against a monthly limit with ACI cost estimation.

- **Storage**: `{data_dir}/budget.json`
- **Hard stops**: New provisioning blocked when budget exhausted
- **Warning threshold**: 80% consumed
- **Cost estimation**: ACI pricing (CPU ~$35/vCPU/mo, Memory ~$3.89/GB/mo, GPU K80 ~$648/mo)
- **Projection**: Linear extrapolation from current spend

### Terraform Backend (`terraform_backend.py`)

Wraps the Terraform CLI with structured Python interfaces. Provider-agnostic design.

- **Protocol**: `TerraformBackend` protocol enables test mocking
- **Implementation**: `SubprocessTerraformBackend` for real Terraform calls
- **Plan storage**: `{data_dir}/plans/{plan_id}.tfplan` + `.json` metadata
- **JSON output**: Parses Terraform's `-json` flag output

## Security

### Defense in depth

```
Azure Spending Limit ─── platform-level hard stop (no surprise bills)
        │
IP Allowlisting ──────── network-level (ACA ingress rules)
        │
API Key (Bearer) ─────── application-level authentication
        │
Budget Tracker ───────── application-level provisioning limit
        │
Scoped Service Principal ── least-privilege (Contributor on workloads RG only)
```

### Authentication

MVP uses API key authentication via Bearer token header. The server validates `Authorization: Bearer <key>` on incoming requests.

### Network restrictions

ACA ingress supports IP allowlisting via `ip_security_restriction` blocks in `terraform/server/main.tf`. When the `allowed_ip_ranges` variable is populated, only specified CIDR ranges can reach the endpoint — all other traffic is denied.

### Service principal scoping

The Terraform service principal (`ARM_CLIENT_ID`/`ARM_CLIENT_SECRET`) should be scoped to **Contributor on the workloads resource group only**, not the entire subscription. This limits blast radius — a compromised credential can only affect workload containers, not the MCP server infrastructure or other Azure resources.

## Data Flow: Plan/Apply Cycle

1. Claude calls `plan_resource(image, cpu, memory_gb, namespace, purpose)`
2. Server validates policies:
   - Purpose field is non-empty
   - Budget has remaining capacity for estimated cost
   - Quota check passes
3. If policies pass, generates Terraform plan (`terraform plan -out=...`)
4. Returns plan summary with cost breakdown and policy validation
5. Claude reviews and calls `apply_plan(plan_id)`
6. Server executes plan, records cost to budget tracker
7. Claude can verify via `get_state()`

## Configuration

Environment variables with `AGENCYOPS_*` prefix, injected via Azure Container Apps secrets and env vars. See README for the full reference.
