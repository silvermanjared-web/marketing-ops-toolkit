# Governance

Marketing Ops Toolkit 2.0 uses capability-level governance.

Rules:

1. Discovery is explicit.
2. Read operations do not gain write authority.
3. Mutation is limited to named operations.
4. Writes require explicit confirmation.
5. File writes are restricted to an admitted output root.
6. External-platform writes remain delegated to the existing narrow implementation and are never generalized.
7. Every bounded mutation returns a receipt.
8. After implementation, perform bounded cleanup and stop.