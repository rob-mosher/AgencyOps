# Architecture

## System Overview

AgencyOps is an MCP (Model Context Protocol) server that mediates between AI entities and infrastructure. It enforces the plan/apply separation pattern — every infrastructure change must be planned, validated against policies, and explicitly applied.

```
AI Entity (Claude, etc.)
    │
    ▼
MCP Server (stdio)
    ├── query_backplane()  ──► BackplaneConfig (static)
    ├── get_state()        ──► Terraform show ──► Docker state
    ├── plan_resource()    ──► Policy check ──► Terraform plan
    ├── apply_plan()       ──► Terraform apply + GPU lock
    ├── get_budget_status() ──► BudgetTracker (JSON file)
    ├── delete_resource()  ──► Terraform destroy + GPU unlock
    └── reconcile()        ──► Terraform state vs Docker ps
```

## Subsystems

### GPU Manager (`gpu_manager.py`)

Atomic locking of the Z230's single GPU (GTX 1060, 6GB VRAM). The GPU is treated as an indivisible resource — when locked, nothing else can use it.

- **Mechanism**: `fcntl.flock(LOCK_EX | LOCK_NB)` for mutual exclusion
- **Metadata**: JSON sidecar file tracks holder, purpose, timestamp, PID
- **Lock file**: `{data_dir}/gpu.lock`
- **Behavior**: Non-blocking — returns error immediately if locked

### Budget Tracker (`budget_tracker.py`)

Mock budget tracking for MVP. Tracks estimated spend against monthly limits per cloud provider.

- **Storage**: `{data_dir}/budget.json`
- **Hard stops**: New provisioning blocked when budget exhausted
- **Warning threshold**: 80% consumed
- **Projection**: Naive linear extrapolation from current spend

### Terraform Backend (`terraform_backend.py`)

Wraps the Terraform CLI with structured Python interfaces.

- **Protocol**: `TerraformBackend` protocol enables test mocking
- **Implementation**: `SubprocessTerraformBackend` for real Terraform calls
- **Plan storage**: `{data_dir}/plans/{plan_id}.tfplan` + `.json` metadata
- **JSON output**: Parses Terraform's `-json` flag output

## Data Flow: Plan/Apply Cycle

1. Entity calls `plan_resource(image, memory, namespace, purpose, gpu)`
2. Server validates policies:
   - Purpose field is non-empty
   - GPU is available (if requested)
   - Budget has remaining capacity
3. If policies pass, generates Terraform plan (`terraform plan -out=...`)
4. Returns plan summary with policy validation results
5. Entity reviews and calls `apply_plan(plan_id)`
6. Server executes plan, locks GPU if needed
7. Entity can verify via `get_state()`

## Configuration

Three layers, highest priority last:

1. **Pydantic defaults** — sensible Z230 defaults
2. **Config file** — `{data_dir}/config.json` (optional)
3. **Environment variables** — `AGENCYOPS_*` prefix
