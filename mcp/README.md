# Citraverse KiCad MCP

This local MCP server gives an MCP-capable agent controlled access to the Citraverse KiCad project. It is intentionally narrow:

- `kicad_project_overview` lists project artifacts and board metadata.
- `kicad_run_drc` runs KiCad's design-rule checker.
- `kicad_export_board_preview` produces a PNG review artifact under `kicad/review/`.

It never uploads a design, changes system KiCad preferences, orders a board, or generates fabrication files.

## Connect it to an MCP client

Use the `mcp/kicad_mcp.config.json` entry in your MCP client's local configuration. The server expects newline-delimited JSON-RPC over standard input/output and uses the installed KiCad CLI at:

```text
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
```

## Safety boundary

The preliminary board is an engineering layout, not a fabrication release. Run DRC and obtain explicit hardware review before authorizing Gerber generation or manufacturing.
