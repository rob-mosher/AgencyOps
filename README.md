# AgencyOps

An MCP server that enables AI entities to provision infrastructure with bounded agency.

## What It Does

AgencyOps gives computational entities the ability to declare infrastructure needs and provision within constitutional limits — budgets, hardware constraints, and purpose requirements. Every decision is **deliberate** (plan before apply), **inspectable** (humans can audit), **purposeful** (all resources justify existence), and **bounded** (budgets and hardware are real constraints).

## MCP Tools

| Tool | Description |
|------|-------------|
| `query_backplane()` | Returns Z230 hardware specs, GPU status, and cloud budgets |
| `get_state()` | Queries Terraform state for currently provisioned resources |
| `plan_resource()` | Generates a Terraform plan with policy validation |
| `apply_plan()` | Executes a previously generated plan, locks GPU if needed |
| `get_budget_status()` | Returns budget tracking status for all cloud providers |
| `delete_resource()` | Destroys a resource via Terraform, releases GPU lock |
| `reconcile()` | Detects drift between Terraform state and actual infrastructure |

## Setup

```bash
# Install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## Claude Code Integration

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "agencyops": {
      "command": "python3",
      "args": ["-m", "agencyops"],
      "env": {
        "AGENCYOPS_DATA_DIR": "/path/to/.agencyops"
      }
    }
  }
}
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AGENCYOPS_DATA_DIR` | `~/.agencyops` | State directory (plans, budget, GPU lock) |
| `AGENCYOPS_TERRAFORM_DIR` | `./terraform` | Path to Terraform configs |
| `AGENCYOPS_AWS_MONTHLY_LIMIT` | `150.0` | AWS monthly budget (USD) |
| `AGENCYOPS_AZURE_MONTHLY_LIMIT` | `150.0` | Azure monthly budget (USD) |

## Architecture

```
src/agencyops/
├── mcp_server.py          # FastMCP server — 7 tools
├── models.py              # Pydantic data models
├── gpu_manager.py         # Atomic GPU locking (fcntl)
├── budget_tracker.py      # Mock budget tracking (JSON)
├── terraform_backend.py   # Terraform subprocess wrapper
└── __main__.py            # Entry point (python -m agencyops)

terraform/
├── main.tf                # Docker provider + container resources
├── backend.tf             # S3 + DynamoDB remote state
├── variables.tf
└── outputs.tf
```

## Philosophy

This isn't automation. This is **agency** — giving computational entities the ability to declare infrastructure needs and provision within constitutional limits.

## License

MIT
