# Five Bounded Mutation Patterns

The public execution layer demonstrates five write contracts:

1. `mutation.inbox_apply` — execute reviewed Gmail rules through the existing narrow workflow.
2. `mutation.state_reset` — reset local inbox-processing state.
3. `mutation.brief_write` — write an executive brief under an admitted output root.
4. `mutation.audit_snapshot` — persist an audit snapshot under an admitted output root.
5. `mutation.recommendations_export` — export reviewed recommendations under an admitted output root.

The point is not the number five. The point is that each mutation has a name, a boundary, a confirmation rule, and a receipt.