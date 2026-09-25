# Ziti Module

**Status:** Greenfield scaffold (implementation pending)

## Overview

The ziti module integrates OpenZiti identity and access control into the Tobogganing hub-api. It provides an alternative or complementary identity provider and transport mechanism alongside or independent of sdwan tunneling.

## Architecture

- **Control-plane integration** (professional tier): OpenZiti controller management and configuration
- **SDK integration** (enterprise tier): Client-side SDK initialization and policy enforcement
- **Transport-independent**: No hard dependency on sdwan or any specific tunnel transport; can coexist or serve as an alternative

## Roadmap

- Phase 1: OpenZiti controller API client (authentication, service discovery, identity enrollment)
- Phase 2: SDK wrapper for client-side identity binding and session management
- Phase 3: Context-aware policy enforcement (threat intelligence, impossible-travel detection)
- Phase 4: Integration with audit and compliance logging

## Current State

Currently a placeholder module that mounts cleanly to the registry. Full implementation is deferred pending roadmap phases.
