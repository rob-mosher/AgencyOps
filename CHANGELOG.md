# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/rob-mosher/AgencyOps/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rob-mosher/AgencyOps/releases/tag/v0.1.0
