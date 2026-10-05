# AI Operating System Reference

This toolkit implements the execution side of the portfolio's shared AI operating-system architecture.

The canonical reference lives in [Growth Architecture OS](https://github.com/silvermanjared-web/growth-architecture-os/tree/main/04-ai-systems/ai-operating-system-reference).

Local mapping:

- **capability discovery** → `src/execution/bounded.py`;
- **bounded mutation** → five explicit `mutation.*` contracts;
- **authority** → confirmation required for every write;
- **target boundary** → local artifacts remain inside an admitted output root;
- **evidence** → structured receipts;
- **external systems** → delegated to narrow existing implementations rather than generalized.

This is intentionally less "a bag of scripts" and more an execution layer an operator or AI client can inspect before acting.