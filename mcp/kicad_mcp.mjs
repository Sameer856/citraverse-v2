#!/usr/bin/env node

/**
 * Citraverse KiCad MCP
 *
 * A deliberately small, local stdio MCP server for inspecting and validating
 * KiCad projects in this workspace. It does not upload a design, alter KiCad
 * preferences, or fabricate anything.
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { resolve, relative, extname, basename } from 'node:path';
import { spawnSync } from 'node:child_process';
import readline from 'node:readline';

const workspace = resolve(process.env.CITRAVERSE_KICAD_WORKSPACE || process.cwd());
const kicadCli = process.env.KICAD_CLI || '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli';

function reply(id, result) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id, result })}\n`);
}

function fail(id, code, message) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id, error: { code, message } })}\n`);
}

function insideWorkspace(path) {
  const resolved = resolve(workspace, path);
  return resolved === workspace || resolved.startsWith(`${workspace}/`) ? resolved : null;
}

function walk(dir, results = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '.git' || entry.name === 'node_modules') continue;
    const full = resolve(dir, entry.name);
    if (entry.isDirectory()) walk(full, results);
    else results.push(full);
  }
  return results;
}

function textResult(text) {
  return { content: [{ type: 'text', text }] };
}

const toolDefinitions = [
  {
    name: 'kicad_project_overview',
    description: 'Lists KiCad artifacts in the Citraverse workspace and summarizes board file metadata.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'kicad_run_drc',
    description: 'Runs KiCad board DRC for a workspace-relative .kicad_pcb file. Read-only validation.',
    inputSchema: {
      type: 'object',
      properties: { board: { type: 'string', description: 'Workspace-relative .kicad_pcb path.' } },
      required: ['board'],
    },
  },
  {
    name: 'kicad_export_board_preview',
    description: 'Renders a workspace-relative board to a PNG review artifact under kicad/review/.',
    inputSchema: {
      type: 'object',
      properties: { board: { type: 'string', description: 'Workspace-relative .kicad_pcb path.' } },
      required: ['board'],
    },
  },
];

function callTool(name, args) {
  if (name === 'kicad_project_overview') {
    const files = walk(workspace).filter((file) => ['.kicad_pro', '.kicad_sch', '.kicad_pcb'].includes(extname(file)));
    const lines = [`Workspace: ${workspace}`, `KiCad CLI: ${existsSync(kicadCli) ? 'available' : 'not found'}`];
    if (!files.length) lines.push('No KiCad project artifacts are present yet.');
    for (const file of files) {
      const size = statSync(file).size;
      lines.push(`${relative(workspace, file)} - ${size} bytes`);
      if (extname(file) === '.kicad_pcb') {
        const text = readFileSync(file, 'utf8');
        const footprints = (text.match(/\(footprint /g) || []).length;
        const nets = (text.match(/\(net \d+/g) || []).length;
        lines.push(`  footprints: ${footprints}; nets: ${nets}`);
      }
    }
    return textResult(lines.join('\n'));
  }

  const board = typeof args?.board === 'string' ? insideWorkspace(args.board) : null;
  if (!board || extname(board) !== '.kicad_pcb' || !existsSync(board)) {
    throw new Error('board must name an existing workspace-relative .kicad_pcb file');
  }
  if (!existsSync(kicadCli)) throw new Error(`KiCad CLI not found at ${kicadCli}`);

  if (name === 'kicad_run_drc') {
    const run = spawnSync(kicadCli, ['pcb', 'drc', '--exit-code-violations', board], { encoding: 'utf8', cwd: workspace });
    const output = `${run.stdout || ''}${run.stderr || ''}`.trim() || 'KiCad DRC completed without textual output.';
    return textResult(`Exit code: ${run.status ?? 'unknown'}\n${output}`);
  }

  if (name === 'kicad_export_board_preview') {
    const outputDir = resolve(workspace, 'kicad', 'review');
    mkdirSync(outputDir, { recursive: true });
    const output = resolve(outputDir, `${basename(board, '.kicad_pcb')}.png`);
    const run = spawnSync(kicadCli, ['pcb', 'render', '--output', output, '--width', '1600', '--height', '1600', board], { encoding: 'utf8', cwd: workspace });
    const messages = `${run.stdout || ''}${run.stderr || ''}`.trim();
    if (run.status !== 0) throw new Error(messages || `KiCad render failed with exit ${run.status}`);
    return textResult(`Created ${relative(workspace, output)}\n${messages}`);
  }

  throw new Error(`Unknown tool: ${name}`);
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('line', (line) => {
  let message;
  try { message = JSON.parse(line); } catch { return; }
  if (!message.method) return;
  if (message.method === 'notifications/initialized') return;
  if (message.method === 'initialize') {
    reply(message.id, {
      protocolVersion: '2024-11-05',
      capabilities: { tools: {} },
      serverInfo: { name: 'citraverse-kicad', version: '0.1.0' },
    });
    return;
  }
  if (message.method === 'tools/list') { reply(message.id, { tools: toolDefinitions }); return; }
  if (message.method === 'tools/call') {
    try { reply(message.id, callTool(message.params?.name, message.params?.arguments || {})); }
    catch (error) { reply(message.id, { content: [{ type: 'text', text: error.message }], isError: true }); }
    return;
  }
  if (message.id !== undefined) fail(message.id, -32601, `Method not found: ${message.method}`);
});
