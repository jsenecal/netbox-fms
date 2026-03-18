# Cable Profiles

NetBox's built-in cable profiles cap at 16 positions. Fiber cables commonly have 24-432 strands. NetBox FMS registers custom profiles to extend the system.

## Single-Connector Profiles

| Profile Key | Label | Strand Count |
|------------|-------|-------------|
| single-1c24p | 1C24P | 24 |
| single-1c48p | 1C48P | 48 |
| single-1c72p | 1C72P | 72 |
| single-1c96p | 1C96P | 96 |
| single-1c144p | 1C144P | 144 |
| single-1c216p | 1C216P | 216 |
| single-1c288p | 1C288P | 288 |
| single-1c432p | 1C432P | 432 |

## Trunk Profiles (Multi-Connector)

| Profile Key | Connectors | Positions per Connector | Total Strands |
|------------|-----------|------------------------|--------------|
| trunk-2c12p | 2 | 12 | 24 |
| trunk-4c12p | 4 | 12 | 48 |
| trunk-6c12p | 6 | 12 | 72 |
| trunk-8c12p | 8 | 12 | 96 |
| trunk-12c12p | 12 | 12 | 144 |
| trunk-18c12p | 18 | 12 | 216 |
| trunk-24c12p | 24 | 12 | 288 |
| trunk-2c24p | 2 | 24 | 48 |
| trunk-4c24p | 4 | 24 | 96 |
| trunk-6c24p | 6 | 24 | 144 |
| trunk-12c24p | 12 | 24 | 288 |

> **Note:** Profiles are registered via `PluginConfig.ready()`.
