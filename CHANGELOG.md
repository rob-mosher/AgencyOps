# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-03-03

### Added

- HTTPS-only enforcement on ACA ingress (`allow_insecure_connections = false`)
- IP allowlisting support via `allowed_ip_ranges` Terraform variable
- Azure setup guide in README (spending limit, scoped service principal, API key generation)
- Security section in ARCHITECTURE.md (defense-in-depth overview)

## [0.2.0] - 2026-03-03

### Changed

- **BREAKING**: Pivoted from local stdio MCP server to cloud-hosted Azure MCP server
- Transport: stdio → streamable-http
- Backplane: Z230 hardware → Azure subscription
- Terraform provider: Docker → azurerm (Azure Container Instances)
- Budget tracking: AWS+Azure dual-provider → Azure-only with ACI cost estimation
- Project structure: `src/` package layout → flat `agencyops/` modules

### Added

- Dockerfile for Azure Container Apps deployment
- Terraform configs for server infrastructure (`terraform/server/`)
- Terraform configs for workload provisioning (`terraform/workloads/`)
- Azure Container Instances as provisionable resource type
- ACI cost estimation (CPU, memory, GPU pricing)
- API key authentication via Bearer token
- `requirements.txt` for Docker builds

### Removed

- GPU atomic locking (fcntl-based, Z230-specific)
- Docker provider Terraform configuration
- S3+DynamoDB Terraform backend
- AWS budget tracking
- Z230 hardware specs from backplane
- Python package (setuptools) configuration

## [0.1.0] - 2026-03-03

### Added

- MCP server with 7 tools: query_backplane, get_state, plan_resource, apply_plan, get_budget_status, delete_resource, reconcile
- GPU atomic locking via fcntl with metadata tracking
- Mock budget tracker with hard-stop enforcement
- Terraform subprocess backend with Protocol abstraction
- Pydantic data models for all request/response types
- Terraform configs for Docker container provisioning (for_each pattern)
- S3 + DynamoDB Terraform backend configuration
- Unit tests for all subsystems (38 tests)
- COLLABORATORS.md following the Collaborators Framework
- MIT License

[Unreleased]: https://github.com/rob-mosher/AgencyOps/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/rob-mosher/AgencyOps/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/rob-mosher/AgencyOps/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rob-mosher/AgencyOps/releases/tag/v0.1.0
