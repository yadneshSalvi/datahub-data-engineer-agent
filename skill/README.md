# DataHub incident-triage skill

`datahub-incident-triage` packages the investigation playbook from the On-Call Data Engineer Agent
as a reusable, user-invocable DataHub skill. It is structured for contribution to
`datahub-project/datahub-skills` and uses the same frontmatter, routing, compatibility, step, and
safety sections as that registry.

## Install locally

Copy the skill into the agent-compatible skill directory for a project:

```bash
mkdir -p .agents/skills
cp -R skill/datahub-incident-triage .agents/skills/
```

Then invoke `/datahub-incident-triage` where slash commands are supported, or ask the agent to
triage a failing DataHub assertion, freshness breach, or data incident. The skill expects a
configured DataHub CLI; it can also use DataHub MCP tools when the host agent exposes them.

For an upstream contribution, copy `datahub-incident-triage/` into the registry's `skills/`
directory alongside `datahub-search`, `datahub-lineage`, and `datahub-quality`.

This skill is derived from the live-tested workflow, OSS constraints, and failure modes in this
project. It does not include the demo application or assume the RideFlow seed exists.
