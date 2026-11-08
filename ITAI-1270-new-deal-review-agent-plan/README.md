# New Deal Review Agent — Plan (ITAI-1270)

Design and delivery plan for an event-driven agent that automates Revenue Analyst intake across email, Asana, Salesforce, NetSuite, and SharePoint.

| | |
|---|---|
| **Jira** | [ITAI-1270 — New Deal Review](https://sailpoint.atlassian.net/browse/ITAI-1270) (source: [ITFINSYS-673](https://sailpoint.atlassian.net/browse/ITFINSYS-673)) |
| **Target implementation** | `sailpoint/gemini-enterprise-agents` → Cloud Run `new-deal-review-agent` (`us-central1`) |
| **Status** | Draft for review |

## What’s in this repo

- **[PLAN.md](./PLAN.md)** — Full architecture, workflows, data map, deployment, risks, and open questions.
- **`diagrams/mmd/`** — Mermaid source for all figures.
- **`diagrams/diagrams/`** — Rendered PNGs referenced from the plan.

## Workflows (summary)

1. **Purchase Acknowledgement email** — Create and populate an Asana Deal Review Tracker task; collect the document pack into SharePoint.
2. **NetSuite sales order** — Match by quote number, enrich deal fields, analyse the executed quote, and when TCV ≥ $250k USD and the Revenue Arrangement exists, generate and upload the Deal Review Sheet.

The agent is **not conversational**: it is triggered by events and periodic reconciliation, not by user prompts.

## Editing diagrams

Change the `.mmd` files under `diagrams/mmd/`, re-export PNGs into `diagrams/diagrams/`, and update links in `PLAN.md` if filenames change.
