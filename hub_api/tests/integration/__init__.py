"""Cross-module seam integration tests (squawk-merge P5-E2E, spec section D).

These exercise the four merge seams end-to-end across module boundaries —
node enrollment, DNS zone/record propagation, and threat-intel blocklisting
— using real_dal (never MagicMock, per the penguin-dal comma-syntax
TypeError regression: ``db(a, b)`` silently drops the second condition,
``db((a) & (b))`` is required) and a real gRPC server bound to an ephemeral
port (not direct servicer method calls), so wire (de)serialization and auth
metadata are exercised too, not just Python-level call contracts.

Node-agent's own single-enrollment guarantee ("a node enrolls exactly once
... so the control plane never sees two competing registrations", see
``agents/node-agent/crates/agent/src/run.rs``) is enforced client-side and
is out of scope here; these tests cover the server-side contract it enrolls
against.
"""
