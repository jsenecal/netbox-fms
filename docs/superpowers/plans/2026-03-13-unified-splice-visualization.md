# Unified Splice Visualization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plan-only splice editor with a unified visualization/editor that always shows live splice state, supports ad-hoc editing with pending-changes-then-save workflow, and rewrites JS to TypeScript.

**Architecture:** Single TypeScript component with three context modes (`view`, `edit`, `plan-edit`). All edits buffered in-memory as pending changes. Save button commits them — creating a new plan via quick-add modal or bulk-updating existing plan via API. Existing splices render full color until changed, then become ghosts with colored overlays.

**Tech Stack:** TypeScript 5.8+, esbuild (IIFE), D3.js v7 (external), Django REST Framework, Bootstrap 5 modal.

**Spec:** `docs/superpowers/specs/2026-03-13-unified-splice-visualization-design.md`

---

## Chunk 1: Build Tooling & TypeScript Foundation

### Task 1: TypeScript build tooling

**Files:**
- Create: `netbox_fms/static/netbox_fms/package.json`
- Create: `netbox_fms/static/netbox_fms/tsconfig.json`
- Create: `netbox_fms/static/netbox_fms/bundle.cjs`
- Modify: `.gitignore`
- Modify: `Makefile`

- [ ] **Step 1: Create package.json**

```json
{
  "private": true,
  "scripts": {
    "build": "node bundle.cjs",
    "watch": "node bundle.cjs --watch",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "esbuild": "^0.25.0",
    "typescript": "~5.8.0",
    "@types/d3": "^7.4.0"
  }
}
```

Write to `netbox_fms/static/netbox_fms/package.json`.

- [ ] **Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "strict": true,
    "target": "ES2016",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "declaration": false,
    "sourceMap": true
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist"]
}
```

Write to `netbox_fms/static/netbox_fms/tsconfig.json`.

- [ ] **Step 3: Create bundle.cjs**

```javascript
const esbuild = require('esbuild');
const path = require('path');

const isWatch = process.argv.includes('--watch');

const buildOptions = {
  entryPoints: [path.join(__dirname, 'src', 'splice-editor.ts')],
  bundle: true,
  minify: !isWatch,
  sourcemap: 'linked',
  target: 'es2016',
  outdir: path.join(__dirname, 'dist'),
  outExtension: { '.js': '.min.js' },
  external: ['d3'],
  format: 'iife',
  globalName: 'SpliceEditor',
  logLevel: 'info',
};

async function main() {
  if (isWatch) {
    const ctx = await esbuild.context(buildOptions);
    await ctx.watch();
    console.log('Watching for changes...');
  } else {
    await esbuild.build(buildOptions);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

Write to `netbox_fms/static/netbox_fms/bundle.cjs`.

- [ ] **Step 4: Update .gitignore**

Add these lines to `.gitignore`:

```
netbox_fms/static/netbox_fms/node_modules/
```

- [ ] **Step 5: Add build targets to Makefile**

Add these targets to the `Makefile`:

```makefile
ts-install:
	cd netbox_fms/static/netbox_fms && npm install

ts-build: ts-install
	cd netbox_fms/static/netbox_fms && npm run build

ts-watch:
	cd netbox_fms/static/netbox_fms && npm run watch

ts-typecheck:
	cd netbox_fms/static/netbox_fms && npm run typecheck
```

- [ ] **Step 6: Install dependencies and verify build scaffold**

Run:
```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npm install
```
Expected: `node_modules/` created, no errors.

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/static/netbox_fms/package.json netbox_fms/static/netbox_fms/tsconfig.json netbox_fms/static/netbox_fms/bundle.cjs .gitignore Makefile
git commit -m "build: add TypeScript build tooling for splice editor"
```

---

### Task 2: TypeScript types module

**Files:**
- Create: `netbox_fms/static/netbox_fms/src/types.ts`

- [ ] **Step 1: Create types.ts**

```typescript
/** Context mode determines save behavior and UI chrome. */
export type ContextMode = 'view' | 'edit' | 'plan-edit';

/** Splice action mode from toolbar buttons. */
export type ActionMode = 'single' | 'sequential' | 'delete';

/** Configuration injected from Django template via window.SPLICE_EDITOR_CONFIG. */
export interface EditorConfig {
  deviceId: number;
  planId: number | null;
  contextMode: ContextMode;
  planStatus: string;
  strandsUrl: string;
  bulkUpdateUrl: string | null;
  quickAddFormUrl: string;
  quickAddApiUrl: string;
  csrfToken: string;
}

/** A single fiber strand as returned by ClosureStrandsAPIView. */
export interface StrandData {
  id: number;
  name: string;
  position: number;
  color: string;
  tube_color: string | null;
  tube_name: string | null;
  ribbon_name: string | null;
  ribbon_color: string | null;
  front_port_id: number | null;
  live_spliced_to: number | null;
  plan_entry_id: number | null;
  plan_spliced_to: number | null;
}

/** A tube group as returned by the API. */
export interface TubeData {
  id: number;
  name: string;
  color: string;
  stripe_color: string | null;
  strand_count: number;
  strands: StrandData[];
}

/** A cable group as returned by the API. */
export interface CableGroupData {
  fiber_cable_id: number;
  cable_label: string;
  fiber_type: string;
  strand_count: number;
  tubes: TubeData[];
  loose_strands: StrandData[];
}

/** Layout node types for the column renderer. */
export type NodeType = 'cable' | 'tube' | 'strand';

/** A node in the column layout (cable header, tube header, or strand). */
export interface LayoutNode {
  type: NodeType;
  y: number;
  hidden: boolean;

  // Cable fields
  label?: string;
  cableId?: number;
  fiberType?: string;
  strandCount?: number;

  // Tube fields
  tubeId?: number;
  color?: string;
  stripeColor?: string | null;
  collapsed?: boolean;

  // Strand fields
  id?: number;
  tubeColor?: string | null;
  tubeName?: string | null;
  ribbonName?: string | null;
  ribbonColor?: string | null;
  frontPortId?: number | null;
  liveSplicedTo?: number | null;
  planEntryId?: number | null;
  planSplicedTo?: number | null;
  parentTubeNode?: LayoutNode;
}

/** A pending splice change (add or remove). */
export interface PendingChange {
  action: 'add' | 'remove';
  fiberA: number;    // strand ID (not front_port_id)
  fiberB: number;    // strand ID
  portA: number;     // front_port_id
  portB: number;     // front_port_id
}

/** An existing splice connection (live or plan). */
export interface SpliceEntry {
  sourceId: number;      // strand ID
  targetId: number;      // strand ID
  entryId: number | null; // plan entry ID (null for live-only)
  isLive: boolean;
  isPlan: boolean;
}

/** Bulk update request body. */
export interface BulkUpdatePayload {
  add: Array<{ fiber_a: number; fiber_b: number }>;
  remove: Array<{ fiber_a: number; fiber_b: number }>;
}

/** Quick-add plan creation payload. */
export interface QuickAddPayload {
  name: string;
  closure: number;
  status: string;
  description: string;
  project: number | null;
  tags: number[];
}

/** Quick-add plan response. */
export interface QuickAddResponse {
  id: number;
  name: string;
  url: string;
}
```

Write to `netbox_fms/static/netbox_fms/src/types.ts`.

- [ ] **Step 2: Verify types compile**

Run:
```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/static/netbox_fms/src/types.ts
git commit -m "feat: add TypeScript type definitions for splice editor"
```

---

### Task 3: API client module

**Files:**
- Create: `netbox_fms/static/netbox_fms/src/api.ts`

- [ ] **Step 1: Create api.ts**

```typescript
import type {
  BulkUpdatePayload,
  CableGroupData,
  EditorConfig,
  QuickAddResponse,
} from './types';

/** Fetch strand data for a device from ClosureStrandsAPIView. */
export async function fetchStrands(
  config: EditorConfig,
): Promise<CableGroupData[]> {
  let url = config.strandsUrl;
  if (config.planId !== null) {
    const sep = url.includes('?') ? '&' : '?';
    url += `${sep}plan_id=${config.planId}`;
  }
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

/** Create a new splice plan via quick-add API. */
export async function quickAddPlan(
  config: EditorConfig,
  formData: FormData,
): Promise<QuickAddResponse> {
  const resp = await fetch(config.quickAddApiUrl, {
    method: 'POST',
    headers: { 'X-CSRFToken': config.csrfToken },
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || err.error || `HTTP ${resp.status}`);
  }
  return resp.json();
}

/** Bulk-update splice plan entries (add/remove atomically). */
export async function bulkUpdatePlan(
  config: EditorConfig,
  payload: BulkUpdatePayload,
): Promise<{ entries: unknown[] }> {
  if (!config.bulkUpdateUrl) {
    throw new Error('No bulk update URL — plan may not exist yet');
  }
  const resp = await fetch(config.bulkUpdateUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': config.csrfToken,
    },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || err.error || `HTTP ${resp.status}`);
  }
  return resp.json();
}

/** Fetch quick-add form HTML from Django. */
export async function fetchQuickAddForm(
  config: EditorConfig,
): Promise<string> {
  const resp = await fetch(config.quickAddFormUrl);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.text();
}
```

Write to `netbox_fms/static/netbox_fms/src/api.ts`.

- [ ] **Step 2: Verify types compile**

Run:
```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/static/netbox_fms/src/api.ts
git commit -m "feat: add API client module for splice editor"
```

---

### Task 4: State management module

**Files:**
- Create: `netbox_fms/static/netbox_fms/src/state.ts`

- [ ] **Step 1: Create state.ts**

```typescript
import type {
  CableGroupData,
  LayoutNode,
  PendingChange,
  SpliceEntry,
  StrandData,
} from './types';

// -----------------------------------------------------------------------
// Layout constants
// -----------------------------------------------------------------------
export const COLUMN_WIDTH = 280;
export const STRAND_HEIGHT = 20;
export const STRAND_DOT_R = 5;
export const TUBE_ROW_H = 18;
export const CABLE_ROW_H = 22;
export const GROUP_PAD = 6;
export const HEADER_HEIGHT = 28;
export const TOP_PAD = 10;
export const TUBE_INDENT = 14;
export const TUBE_DOT_R = 4;
export const MIN_HEIGHT = 500;

// -----------------------------------------------------------------------
// State
// -----------------------------------------------------------------------
export class EditorState {
  cableGroups: CableGroupData[] = [];
  leftNodes: LayoutNode[] = [];
  rightNodes: LayoutNode[] = [];
  spliceEntries: SpliceEntry[] = [];
  pendingChanges: PendingChange[] = [];
  leftOffset = 0;
  rightOffset = 0;

  /** Build a lookup map: strand ID -> StrandData. */
  private strandMap: Map<number, StrandData> = new Map();

  /** Load cable groups from API and rebuild layout. */
  loadCableGroups(groups: CableGroupData[]): void {
    this.cableGroups = groups;
    this.strandMap.clear();
    for (const cg of groups) {
      for (const tube of cg.tubes) {
        for (const s of tube.strands) this.strandMap.set(s.id, s);
      }
      for (const s of cg.loose_strands) this.strandMap.set(s.id, s);
    }
    this.rebuildLayout();
  }

  /** Get strand data by ID. */
  getStrand(id: number): StrandData | undefined {
    return this.strandMap.get(id);
  }

  /** Rebuild column layouts and collect splice entries. */
  rebuildLayout(): void {
    const mid = Math.ceil(this.cableGroups.length / 2);
    this.leftNodes = this.layoutColumn(this.cableGroups.slice(0, mid));
    this.rightNodes = this.layoutColumn(this.cableGroups.slice(mid));
    this.collectSpliceEntries();
    this.leftOffset = 0;
    this.rightOffset = 0;
  }

  // -------------------------------------------------------------------
  // Pending changes
  // -------------------------------------------------------------------

  addPendingSplice(
    strandA: number, strandB: number,
    portA: number, portB: number,
  ): void {
    // Don't add duplicate
    const exists = this.pendingChanges.some(
      (p) => p.action === 'add' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
    if (!exists) {
      this.pendingChanges.push({
        action: 'add', fiberA: strandA, fiberB: strandB,
        portA, portB,
      });
    }
  }

  removePendingSplice(strandA: number, strandB: number, portA: number, portB: number): void {
    // Check if we're removing a pending add (cancel it out)
    const addIdx = this.pendingChanges.findIndex(
      (p) => p.action === 'add' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
    if (addIdx >= 0) {
      this.pendingChanges.splice(addIdx, 1);
      return;
    }
    // Otherwise add a remove entry
    const exists = this.pendingChanges.some(
      (p) => p.action === 'remove' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
    if (!exists) {
      this.pendingChanges.push({
        action: 'remove', fiberA: strandA, fiberB: strandB,
        portA, portB,
      });
    }
  }

  hasPendingChanges(): boolean {
    return this.pendingChanges.length > 0;
  }

  clearPending(): void {
    this.pendingChanges = [];
  }

  /** Get pending changes as bulk update payload (uses front_port_ids). */
  getPendingPayload(): { add: Array<{ fiber_a: number; fiber_b: number }>; remove: Array<{ fiber_a: number; fiber_b: number }> } {
    const add: Array<{ fiber_a: number; fiber_b: number }> = [];
    const remove: Array<{ fiber_a: number; fiber_b: number }> = [];
    for (const p of this.pendingChanges) {
      if (p.action === 'add') {
        add.push({ fiber_a: p.portA, fiber_b: p.portB });
      } else {
        remove.push({ fiber_a: p.portA, fiber_b: p.portB });
      }
    }
    return { add, remove };
  }

  /**
   * Get re-splices: strands that appear in both a remove and an add.
   * Returns Map of strandId to { oldTarget, newTarget }.
   */
  getReSplices(): Map<number, { oldTarget: number; newTarget: number }> {
    const result = new Map<number, { oldTarget: number; newTarget: number }>();
    const removes = this.pendingChanges.filter((p) => p.action === 'remove');
    const adds = this.pendingChanges.filter((p) => p.action === 'add');

    for (const rem of removes) {
      for (const add of adds) {
        if (rem.fiberA === add.fiberA) {
          result.set(rem.fiberA, { oldTarget: rem.fiberB, newTarget: add.fiberB });
        } else if (rem.fiberA === add.fiberB) {
          result.set(rem.fiberA, { oldTarget: rem.fiberB, newTarget: add.fiberA });
        } else if (rem.fiberB === add.fiberA) {
          result.set(rem.fiberB, { oldTarget: rem.fiberA, newTarget: add.fiberB });
        } else if (rem.fiberB === add.fiberB) {
          result.set(rem.fiberB, { oldTarget: rem.fiberA, newTarget: add.fiberA });
        }
      }
    }
    return result;
  }

  /**
   * Check if a strand is involved in a pending change.
   * Returns the pending change action or null.
   */
  getStrandPendingState(strandId: number): 'add' | 'remove' | null {
    for (const p of this.pendingChanges) {
      if (p.fiberA === strandId || p.fiberB === strandId) {
        return p.action;
      }
    }
    return null;
  }

  /**
   * Check if a specific splice (between two strands) has a pending delete.
   */
  isSplicePendingDelete(strandA: number, strandB: number): boolean {
    return this.pendingChanges.some(
      (p) => p.action === 'remove' &&
        ((p.fiberA === strandA && p.fiberB === strandB) ||
         (p.fiberA === strandB && p.fiberB === strandA)),
    );
  }

  // -------------------------------------------------------------------
  // Layout helpers
  // -------------------------------------------------------------------

  private layoutColumn(cables: CableGroupData[]): LayoutNode[] {
    const nodes: LayoutNode[] = [];
    let y = TOP_PAD;

    for (const cg of cables) {
      nodes.push({
        type: 'cable',
        label: cg.cable_label,
        y,
        hidden: false,
        cableId: cg.fiber_cable_id,
        fiberType: cg.fiber_type,
        strandCount: cg.strand_count,
      });
      y += CABLE_ROW_H;

      for (const tube of cg.tubes) {
        const tubeNode: LayoutNode = {
          type: 'tube',
          label: tube.name,
          color: tube.color,
          stripeColor: tube.stripe_color,
          strandCount: tube.strand_count,
          y,
          hidden: false,
          tubeId: tube.id,
          collapsed: false,
        };
        nodes.push(tubeNode);
        y += TUBE_ROW_H;

        for (const s of tube.strands) {
          nodes.push({
            type: 'strand',
            id: s.id,
            label: s.name,
            color: s.color,
            tubeColor: s.tube_color,
            tubeName: s.tube_name,
            ribbonName: s.ribbon_name,
            ribbonColor: s.ribbon_color,
            y,
            hidden: false,
            frontPortId: s.front_port_id,
            liveSplicedTo: s.live_spliced_to,
            planEntryId: s.plan_entry_id,
            planSplicedTo: s.plan_spliced_to,
            tubeId: tube.id,
            parentTubeNode: tubeNode,
          });
          y += STRAND_HEIGHT;
        }
        y += GROUP_PAD;
      }

      for (const s of cg.loose_strands) {
        nodes.push({
          type: 'strand',
          id: s.id,
          label: s.name,
          color: s.color,
          tubeColor: null,
          tubeName: null,
          ribbonName: s.ribbon_name,
          ribbonColor: s.ribbon_color,
          y,
          hidden: false,
          frontPortId: s.front_port_id,
          liveSplicedTo: s.live_spliced_to,
          planEntryId: s.plan_entry_id,
          planSplicedTo: s.plan_spliced_to,
          tubeId: undefined,
          parentTubeNode: undefined,
        });
        y += STRAND_HEIGHT;
      }
      y += GROUP_PAD;
    }

    return nodes;
  }

  private collectSpliceEntries(): void {
    this.spliceEntries = [];
    const seen = new Set<string>();

    for (const cg of this.cableGroups) {
      const allStrands: StrandData[] = [];
      for (const t of cg.tubes) allStrands.push(...t.strands);
      allStrands.push(...cg.loose_strands);

      for (const s of allStrands) {
        // Live splices
        if (s.live_spliced_to) {
          const key = `live-${Math.min(s.id, s.live_spliced_to)}-${Math.max(s.id, s.live_spliced_to)}`;
          if (!seen.has(key)) {
            seen.add(key);
            this.spliceEntries.push({
              sourceId: s.id,
              targetId: s.live_spliced_to,
              entryId: null,
              isLive: true,
              isPlan: false,
            });
          }
        }
        // Plan splices
        if (s.plan_entry_id && s.plan_spliced_to) {
          const key = `plan-${Math.min(s.id, s.plan_spliced_to)}-${Math.max(s.id, s.plan_spliced_to)}`;
          if (!seen.has(key)) {
            seen.add(key);
            this.spliceEntries.push({
              sourceId: s.id,
              targetId: s.plan_spliced_to,
              entryId: s.plan_entry_id,
              isLive: false,
              isPlan: true,
            });
          }
        }
      }
    }
  }

  /** Recalculate y-positions respecting collapsed tubes. */
  recalcPositions(nodes: LayoutNode[]): void {
    const collapsedTubes = new Set<number>();
    const tubeYMap = new Map<number, number>();

    for (const n of nodes) {
      if (n.type === 'tube' && n.collapsed) collapsedTubes.add(n.tubeId!);
    }

    let y = TOP_PAD;
    for (const n of nodes) {
      if (n.type === 'strand' && n.tubeId !== undefined && collapsedTubes.has(n.tubeId)) {
        n.y = tubeYMap.get(n.tubeId) ?? y;
        n.hidden = true;
        continue;
      }
      n.hidden = false;
      n.y = y;
      if (n.type === 'cable') {
        y += CABLE_ROW_H;
      } else if (n.type === 'tube') {
        tubeYMap.set(n.tubeId!, y);
        y += TUBE_ROW_H;
      } else {
        y += STRAND_HEIGHT;
      }
    }
  }

  /** Get visible strands in a column starting from a given strand ID. */
  getVisibleStrandsFrom(side: 'left' | 'right', startId: number): LayoutNode[] {
    const nodes = side === 'left' ? this.leftNodes : this.rightNodes;
    const strands = nodes.filter((n) => n.type === 'strand' && !n.hidden);
    const idx = strands.findIndex((n) => n.id === startId);
    return idx >= 0 ? strands.slice(idx) : [];
  }

  /**
   * Get visible strands within the same tube, starting from a given strand ID.
   * Used by sequential mode (does not cross tube boundaries).
   */
  getVisibleStrandsInTubeFrom(side: 'left' | 'right', startId: number): LayoutNode[] {
    const nodes = side === 'left' ? this.leftNodes : this.rightNodes;
    const startNode = nodes.find((n) => n.type === 'strand' && n.id === startId);
    if (!startNode) return [];

    const tubeId = startNode.tubeId;
    const strands = nodes.filter(
      (n) => n.type === 'strand' && !n.hidden && n.tubeId === tubeId,
    );
    const idx = strands.findIndex((n) => n.id === startId);
    return idx >= 0 ? strands.slice(idx) : [];
  }

  /** Get column height for rendering. */
  columnHeight(nodes: LayoutNode[]): number {
    const visible = nodes.filter((n) => !n.hidden);
    if (!visible.length) return MIN_HEIGHT;
    const last = visible[visible.length - 1];
    return last.y + STRAND_HEIGHT + TOP_PAD;
  }
}
```

Write to `netbox_fms/static/netbox_fms/src/state.ts`.

- [ ] **Step 2: Verify types compile**

Run:
```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/static/netbox_fms/src/state.ts
git commit -m "feat: add state management module for splice editor"
```

---

### Task 5: Renderer module

**Files:**
- Create: `netbox_fms/static/netbox_fms/src/renderer.ts`

- [ ] **Step 1: Create renderer.ts**

This is the D3 rendering engine. It is a TypeScript port of the rendering logic from `splice_editor.js` (lines 250-510), with the addition of ghost/pending visual states.

The renderer must:
1. Create the SVG with clip paths, backgrounds, headers, column groups.
2. Render cable nodes, tube nodes (with collapse toggle), and strand nodes with EIA-598 color dots.
3. Render splice links as bezier curves — with ghost/pending-delete/pending-add visual states.
4. Handle column drag/scroll.

Key rendering additions vs. the old JS:
- **Ghost lines:** existing splices that have pending deletes get `opacity: 0.2, stroke-width: 1`, plus a dashed red overlay.
- **Pending adds:** solid green bezier curves drawn from `state.pendingChanges`.
- **Same-side splices:** loop curves through center (same as old JS).

The full implementation follows the exact same SVG structure as the existing `splice_editor.js`. See the spec at `docs/superpowers/specs/2026-03-13-unified-splice-visualization-design.md` Section 3 for visual states.

Constructor signature:
```typescript
constructor(
  state: EditorState,
  containerEl: HTMLElement,
  onStrandClick: (node: LayoutNode, side: 'left' | 'right') => void,
  onSpliceClick: (entry: SpliceEntry) => void,
  onTubeToggle: (node: LayoutNode, nodes: LayoutNode[]) => void,
)
```

Public methods:
- `render(): void` — Full re-render.
- `handleResize(): void` — Update container width and re-render.

The complete implementation is a direct port of the existing JS rendering (302 lines in `renderColumn`, `renderCableNode`, `renderTubeNode`, `renderStrandNode`, `renderLinks`, `setupDrag`) with D3 type annotations and the pending/ghost visual state additions.

Write to `netbox_fms/static/netbox_fms/src/renderer.ts`.

- [ ] **Step 2: Verify types compile**

Run:
```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npx tsc --noEmit
```
Expected: No errors (or minor D3 type issues to resolve).

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/static/netbox_fms/src/renderer.ts
git commit -m "feat: add D3 renderer module for splice editor"
```

---

### Task 6: Interactions module

**Files:**
- Create: `netbox_fms/static/netbox_fms/src/interactions.ts`

- [ ] **Step 1: Create interactions.ts**

This module handles:
1. **Toolbar mode buttons** — single/sequential/delete mode switching.
2. **Save button** — dynamically injected, shown/hidden based on `state.hasPendingChanges()`.
3. **Sequential count selector** — inline +/- buttons with number input (default 12, range 1-144), visible only in sequential mode.
4. **Strand click handling** — delegates to single/sequential/delete handlers.
5. **Splice click handling** — for delete mode on splice links.
6. **beforeunload** — warns about unsaved changes.

Constructor signature:
```typescript
constructor(
  state: EditorState,
  renderer: Renderer,
  config: EditorConfig,
  onSave: () => void,
)
```

Public methods:
- `handleStrandClick(node: LayoutNode, side: 'left' | 'right'): void`
- `handleSpliceClick(entry: SpliceEntry): void`
- `updateSaveButton(): void`
- `setStatus(msg: string): void`
- `clearSelection(): void`

Key behavior:
- **Single mode:** Click strand A to select, click strand B to create pending splice. Click same strand to deselect.
- **Sequential mode:** Click strand A, click strand B, creates N pending splices where N is from the count selector. Walks strands within the same tube only (no cross-tube). Shows "Spliced X of Y requested" if fewer strands available.
- **Delete mode:** Click a strand or splice link to create pending delete.
- All changes are pending until Save is clicked.

Write to `netbox_fms/static/netbox_fms/src/interactions.ts`.

- [ ] **Step 2: Verify types compile**

Run:
```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/static/netbox_fms/src/interactions.ts
git commit -m "feat: add interactions module for splice editor"
```

---

### Task 7: Modal module

**Files:**
- Create: `netbox_fms/static/netbox_fms/src/modal.ts`

- [ ] **Step 1: Create modal.ts**

This module handles the quick-add SplicePlan modal:
1. Fetches form HTML from Django's `SplicePlanQuickAddFormView` endpoint.
2. Creates a Bootstrap 5 modal programmatically using DOM APIs (no `innerHTML` for untrusted content — the form HTML comes from our own Django server).
3. Handles submit via the `quickAddPlan()` API function.
4. Returns `QuickAddResponse | null` (null if cancelled).

**Security note:** The form HTML is fetched from our own Django endpoint (same-origin, authenticated). It contains rendered Django form fields. Use `insertAdjacentHTML` or set content via DOM after sanitization. Since this is same-origin server-rendered content, it is trusted.

Constructor/function signature:
```typescript
export async function showQuickAddModal(
  config: EditorConfig,
): Promise<QuickAddResponse | null>
```

The modal creates:
- A `.modal` backdrop
- `.modal-dialog.modal-lg` with header ("Create Splice Plan"), body (form HTML), footer (Cancel + Create buttons)
- Close handlers on backdrop click, close button, and Cancel button
- Submit handler that collects FormData and calls `quickAddPlan()`
- Error display in an alert div

Write to `netbox_fms/static/netbox_fms/src/modal.ts`.

- [ ] **Step 2: Verify types compile**

Run:
```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add netbox_fms/static/netbox_fms/src/modal.ts
git commit -m "feat: add quick-add modal module for splice editor"
```

---

### Task 8: Main entry point and build

**Files:**
- Create: `netbox_fms/static/netbox_fms/src/splice-editor.ts`

- [ ] **Step 1: Create splice-editor.ts**

This is the main entry point that:
1. Reads `window.SPLICE_EDITOR_CONFIG`.
2. Initializes `EditorState`, `Renderer`, and `Interactions`.
3. Loads data via `fetchStrands()`.
4. Handles save flow: if `view` mode (no plan), shows quick-add modal first, then bulk-updates; if `edit`/`plan-edit`, bulk-updates directly.
5. Sets up resize handler.

```typescript
import { bulkUpdatePlan, fetchStrands } from './api';
import { Interactions } from './interactions';
import { showQuickAddModal } from './modal';
import { Renderer } from './renderer';
import { EditorState } from './state';
import type { EditorConfig, LayoutNode, SpliceEntry } from './types';

declare const d3: typeof import('d3');

const config = (window as unknown as { SPLICE_EDITOR_CONFIG: EditorConfig }).SPLICE_EDITOR_CONFIG;
if (config) {
  init(config);
}

async function init(config: EditorConfig): Promise<void> {
  const containerEl = document.getElementById('splice-canvas-container');
  if (!containerEl) return;

  const state = new EditorState();

  const renderer = new Renderer(
    state,
    containerEl,
    (node: LayoutNode, side: 'left' | 'right') => interactions.handleStrandClick(node, side),
    (entry: SpliceEntry) => interactions.handleSpliceClick(entry),
    (node: LayoutNode, nodes: LayoutNode[]) => {
      node.collapsed = !node.collapsed;
      state.recalcPositions(nodes);
      renderer.render();
    },
  );

  const interactions = new Interactions(state, renderer, config, handleSave);

  // Load initial data
  await loadData();

  // Resize handler
  let resizeTimer: ReturnType<typeof setTimeout>;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderer.handleResize(), 150);
  });

  async function loadData(): Promise<void> {
    try {
      const groups = await fetchStrands(config);
      state.loadCableGroups(groups);
      renderer.render();
      interactions.setStatus(
        `Loaded ${groups.length} cable(s). Click strands to splice.`,
      );
    } catch (err) {
      interactions.setStatus(`Error: ${(err as Error).message}`);
    }
  }

  async function handleSave(): Promise<void> {
    if (!state.hasPendingChanges()) return;

    if (config.contextMode === 'view' && !config.planId) {
      // No plan exists — show quick-add modal
      const result = await showQuickAddModal(config);
      if (!result) return; // User cancelled

      // Update config with new plan
      config.planId = result.id;
      config.contextMode = 'edit';
      // Construct bulk update URL from the quick-add response
      config.bulkUpdateUrl = config.quickAddApiUrl.replace(
        'quick-add/',
        `${result.id}/bulk-update/`,
      );

      // Now save the pending changes to the new plan
      await savePendingChanges();
    } else {
      // Plan exists — direct save
      await savePendingChanges();
    }
  }

  async function savePendingChanges(): Promise<void> {
    try {
      const payload = state.getPendingPayload();
      await bulkUpdatePlan(config, payload);
      state.clearPending();
      interactions.updateSaveButton();
      interactions.setStatus('Changes saved successfully.');
      // Reload data to get fresh state
      await loadData();
    } catch (err) {
      interactions.setStatus(`Save error: ${(err as Error).message}`);
    }
  }
}
```

Write to `netbox_fms/static/netbox_fms/src/splice-editor.ts`.

- [ ] **Step 2: Build the bundle**

Run:
```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npm run build
```
Expected: `dist/splice-editor.min.js` and `dist/splice-editor.min.js.map` created.

- [ ] **Step 3: Verify type checking passes**

Run:
```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npm run typecheck
```
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add netbox_fms/static/netbox_fms/src/splice-editor.ts netbox_fms/static/netbox_fms/dist/
git commit -m "feat: add main entry point and build splice editor TypeScript bundle"
```

---

## Chunk 2: Backend API & View Changes

### Task 9: ClosureStrandsAPIView — add live splice data

**Files:**
- Modify: `netbox_fms/api/views.py:185-263`
- Modify: `netbox_fms/api/serializers.py:358-367`
- Test: `tests/test_services.py` (add new test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_services.py`:

```python
class TestClosureStrandsLiveData(TestCase):
    """Test that ClosureStrandsAPIView returns live splice data."""

    @classmethod
    def setUpTestData(cls):
        from dcim.models import (
            Cable, CableTermination, Device, DeviceRole, DeviceType,
            FrontPort, Manufacturer, Module, ModuleBay, ModuleType, Site,
        )
        from django.contrib.contenttypes.models import ContentType

        site = Site.objects.create(name="Live Site", slug="live-site")
        mfr = Manufacturer.objects.create(name="Live Mfr", slug="live-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="live-closure")
        role = DeviceRole.objects.create(name="Live Role", slug="live-role")
        cls.closure = Device.objects.create(name="C-Live", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F1", type="lc")
        cls.fp2 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F2", type="lc")

        # Create live connection (0-length cable between fp1 and fp2)
        fp_ct = ContentType.objects.get_for_model(FrontPort)
        cable = Cable.objects.create(length=0, length_unit="m")
        CableTermination.objects.create(cable=cable, cable_end="A", termination_type=fp_ct, termination_id=cls.fp1.pk)
        CableTermination.objects.create(cable=cable, cable_end="B", termination_type=fp_ct, termination_id=cls.fp2.pk)

    def test_get_live_state_returns_connection(self):
        from netbox_fms.services import get_live_state
        state = get_live_state(self.closure)
        assert len(state) > 0
        all_pairs = set()
        for pairs in state.values():
            all_pairs.update(pairs)
        assert (min(self.fp1.pk, self.fp2.pk), max(self.fp1.pk, self.fp2.pk)) in all_pairs
```

- [ ] **Step 2: Run test to verify it passes** (this tests existing `get_live_state`, should already pass)

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_services.py::TestClosureStrandsLiveData -v
```

- [ ] **Step 3: Modify ClosureStrandsAPIView to include live splice data**

In `netbox_fms/api/views.py`, modify the `ClosureStrandsAPIView.get()` method to:

1. Build a live splice lookup using CableTermination queries for FrontPort pairs on this device.
2. Optionally build a plan splice lookup when `plan_id` query param is provided.
3. Output fields: `live_spliced_to` (from live connections), `plan_entry_id` and `plan_spliced_to` (from plan entries).

Replace the splice lookup section (lines 205-212) with:

```python
        from django.contrib.contenttypes.models import ContentType
        from dcim.models import FrontPort

        # Build LIVE splice lookup: front_port_id -> spliced_to_front_port_id
        # Only match module-attached FrontPorts (tray ports), matching get_live_state() logic
        fp_ct = ContentType.objects.get_for_model(FrontPort)
        tray_front_port_ids = set(
            FrontPort.objects.filter(
                device_id=device_id,
                module__isnull=False,
            ).values_list("pk", flat=True)
        )
        live_lookup = {}  # front_port_id -> front_port_id
        if tray_front_port_ids:
            terms = CableTermination.objects.filter(
                termination_type=fp_ct,
                termination_id__in=tray_front_port_ids,
            ).values_list("cable_id", "termination_id", "cable_end")

            cable_terms = {}
            for cable_id, term_id, cable_end in terms:
                cable_terms.setdefault(cable_id, {})[cable_end] = term_id

            for _cable_id, ends in cable_terms.items():
                if "A" in ends and "B" in ends:
                    a_id, b_id = ends["A"], ends["B"]
                    if a_id in tray_front_port_ids and b_id in tray_front_port_ids:
                        live_lookup[a_id] = b_id
                        live_lookup[b_id] = a_id

        # Build PLAN splice lookup (optional, when plan_id provided)
        plan_lookup = {}
        plan_id = request.query_params.get("plan_id")
        if plan_id:
            plan_entries = SplicePlanEntry.objects.filter(
                plan_id=plan_id,
            ).values_list("id", "fiber_a_id", "fiber_b_id")
            for entry_id, fa_id, fb_id in plan_entries:
                plan_lookup[fa_id] = (entry_id, fb_id)
                plan_lookup[fb_id] = (entry_id, fa_id)
```

Then build a `front_port_id -> strand_id` reverse mapping (needed because the renderer looks up nodes by strand ID, but splices are tracked by front_port_id):

```python
        # Build front_port_id -> strand_id reverse lookup
        # so we can return strand IDs (not front_port IDs) for splice targets
        fp_to_strand = {}
        for fc in fiber_cables:
            for s in fc.fiber_strands.all():
                if s.front_port_id:
                    fp_to_strand[s.front_port_id] = s.pk
```

Then update the strand_data dict (replace `splice_entry_id` and `spliced_to`):

```python
                live_fp = live_lookup.get(s.front_port_id)
                live_strand = fp_to_strand.get(live_fp) if live_fp else None
                plan_info = plan_lookup.get(s.front_port_id, (None, None))
                plan_strand = fp_to_strand.get(plan_info[1]) if plan_info[1] else None
                strand_data = {
                    "id": s.pk,
                    "name": s.name,
                    "position": s.position,
                    "color": s.color,
                    "tube_color": s.buffer_tube.color if s.buffer_tube else None,
                    "tube_name": s.buffer_tube.name if s.buffer_tube else None,
                    "ribbon_name": s.ribbon.name if s.ribbon else None,
                    "ribbon_color": s.ribbon.color if s.ribbon else None,
                    "front_port_id": s.front_port_id,
                    "live_spliced_to": live_strand,
                    "plan_entry_id": plan_info[0],
                    "plan_spliced_to": plan_strand,
                }
```

**Important:** `live_spliced_to` and `plan_spliced_to` are **strand IDs** (not front_port IDs). The renderer uses strand IDs to look up layout nodes for drawing splice lines.

- [ ] **Step 4: Update ClosureStrandSerializer**

In `netbox_fms/api/serializers.py`, update:

```python
class ClosureStrandSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    position = serializers.IntegerField()
    color = serializers.CharField()
    front_port_id = serializers.IntegerField(allow_null=True)
    live_spliced_to = serializers.IntegerField(allow_null=True)
    plan_entry_id = serializers.IntegerField(allow_null=True)
    plan_spliced_to = serializers.IntegerField(allow_null=True)
```

- [ ] **Step 5: Run existing tests to verify no regressions**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/api/views.py netbox_fms/api/serializers.py tests/test_services.py
git commit -m "feat: add live splice data to ClosureStrandsAPIView"
```

---

### Task 10: Bulk update API action

**Files:**
- Modify: `netbox_fms/api/views.py:138-171`
- Test: `tests/test_api.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_api.py`:

```python
from dcim.models import (
    Device, DeviceRole, DeviceType, FrontPort,
    Manufacturer, Module, ModuleBay, ModuleType, Site,
)
from django.test import TestCase
from rest_framework.test import APIClient

from netbox_fms.models import SplicePlan, SplicePlanEntry


class TestBulkUpdateAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="API Site", slug="api-site")
        mfr = Manufacturer.objects.create(name="API Mfr", slug="api-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="api-closure")
        role = DeviceRole.objects.create(name="API Role", slug="api-role")
        cls.closure = Device.objects.create(name="C-API", site=site, device_type=dt, role=role)

        mt = ModuleType.objects.create(manufacturer=mfr, model="Tray")
        bay = ModuleBay.objects.create(device=cls.closure, name="Bay 1")
        cls.tray = Module.objects.create(device=cls.closure, module_bay=bay, module_type=mt)

        cls.fp1 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F1", type="lc")
        cls.fp2 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F2", type="lc")
        cls.fp3 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F3", type="lc")
        cls.fp4 = FrontPort.objects.create(device=cls.closure, module=cls.tray, name="F4", type="lc")

        cls.plan = SplicePlan.objects.create(closure=cls.closure, name="API Plan")

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_superuser("testadmin", "test@test.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_bulk_add(self):
        url = f"/api/plugins/netbox-fms/splice-plans/{self.plan.pk}/bulk-update/"
        resp = self.client.post(url, {
            "add": [{"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk}],
            "remove": [],
        }, format="json")
        assert resp.status_code == 200
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 1

    def test_bulk_remove(self):
        SplicePlanEntry.objects.create(
            plan=self.plan, tray=self.tray, fiber_a=self.fp3, fiber_b=self.fp4,
        )
        url = f"/api/plugins/netbox-fms/splice-plans/{self.plan.pk}/bulk-update/"
        resp = self.client.post(url, {
            "add": [],
            "remove": [{"fiber_a": self.fp3.pk, "fiber_b": self.fp4.pk}],
        }, format="json")
        assert resp.status_code == 200
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 0

    def test_bulk_atomic_rollback(self):
        """Invalid add should rollback entire transaction."""
        url = f"/api/plugins/netbox-fms/splice-plans/{self.plan.pk}/bulk-update/"
        resp = self.client.post(url, {
            "add": [
                {"fiber_a": self.fp1.pk, "fiber_b": self.fp2.pk},
                {"fiber_a": 999999, "fiber_b": self.fp3.pk},  # Invalid
            ],
            "remove": [],
        }, format="json")
        assert resp.status_code == 400
        assert SplicePlanEntry.objects.filter(plan=self.plan).count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_api.py -v
```
Expected: FAIL (endpoint doesn't exist yet).

- [ ] **Step 3: Implement bulk_update action**

Add to `SplicePlanViewSet` in `netbox_fms/api/views.py`:

```python
    @action(detail=True, methods=["post"], url_path="bulk-update")
    def bulk_update_entries(self, request, pk=None):
        plan = self.get_object()
        adds = request.data.get("add", [])
        removes = request.data.get("remove", [])

        from dcim.models import FrontPort

        try:
            with transaction.atomic():
                # Process removes
                for item in removes:
                    fa_id, fb_id = item["fiber_a"], item["fiber_b"]
                    SplicePlanEntry.objects.filter(
                        plan=plan,
                    ).filter(
                        models.Q(fiber_a_id=fa_id, fiber_b_id=fb_id)
                        | models.Q(fiber_a_id=fb_id, fiber_b_id=fa_id)
                    ).delete()

                # Process adds
                for item in adds:
                    fa_id, fb_id = item["fiber_a"], item["fiber_b"]
                    fa = FrontPort.objects.get(pk=fa_id)
                    tray = fa.module
                    if tray is None:
                        raise ValueError(f"FrontPort {fa_id} has no module (tray)")
                    SplicePlanEntry.objects.create(
                        plan=plan,
                        tray=tray,
                        fiber_a_id=fa_id,
                        fiber_b_id=fb_id,
                    )

                plan.diff_stale = True
                plan.save(update_fields=["diff_stale"])

        except (FrontPort.DoesNotExist, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        entries = SplicePlanEntry.objects.filter(plan=plan)
        return Response({
            "entries": [
                {"id": e.pk, "fiber_a": e.fiber_a_id, "fiber_b": e.fiber_b_id, "tray": e.tray_id}
                for e in entries
            ]
        })
```

Add `from django.db import models` to the imports at top of `api/views.py` if not already present.

- [ ] **Step 4: Run tests**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_api.py -v
```
Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add netbox_fms/api/views.py tests/test_api.py
git commit -m "feat: add bulk-update API action for splice plan entries"
```

---

### Task 11: Quick-add API and form view

**Files:**
- Modify: `netbox_fms/api/views.py`
- Modify: `netbox_fms/views.py`
- Modify: `netbox_fms/urls.py`
- Create: `netbox_fms/templates/netbox_fms/spliceplan_quick_add_form.html`
- Test: `tests/test_api.py` (add tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py`:

```python
class TestQuickAddAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = Site.objects.create(name="QA Site", slug="qa-site")
        mfr = Manufacturer.objects.create(name="QA Mfr", slug="qa-mfr")
        dt = DeviceType.objects.create(manufacturer=mfr, model="Closure", slug="qa-closure")
        role = DeviceRole.objects.create(name="QA Role", slug="qa-role")
        cls.closure = Device.objects.create(name="C-QA", site=site, device_type=dt, role=role)

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_superuser("qaadmin", "qa@test.com", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_quick_add_creates_plan(self):
        url = "/api/plugins/netbox-fms/splice-plans/quick-add/"
        resp = self.client.post(url, {
            "name": "Quick Plan",
            "closure": self.closure.pk,
            "status": "planned",
            "description": "",
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["name"] == "Quick Plan"
        assert SplicePlan.objects.filter(closure=self.closure).exists()

    def test_quick_add_duplicate_closure_fails(self):
        SplicePlan.objects.create(closure=self.closure, name="Existing")
        url = "/api/plugins/netbox-fms/splice-plans/quick-add/"
        resp = self.client.post(url, {
            "name": "Dupe Plan",
            "closure": self.closure.pk,
            "status": "planned",
        }, format="json")
        assert resp.status_code == 400
```

- [ ] **Step 2: Implement quick_add action**

Add to `SplicePlanViewSet` in `netbox_fms/api/views.py`:

```python
    @action(detail=False, methods=["post"], url_path="quick-add")
    def quick_add(self, request):
        serializer = SplicePlanSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
```

- [ ] **Step 3: Create quick-add form template**

Create `netbox_fms/templates/netbox_fms/spliceplan_quick_add_form.html`:

```html
{% load i18n %}

{% for fieldset in form.fieldsets %}
<fieldset class="mb-3">
    {% if fieldset.name %}
    <legend class="fs-6 fw-bold">{{ fieldset.name }}</legend>
    {% endif %}
    {% for field in fieldset.fields %}
    <div class="mb-2 row">
        <label class="col-sm-3 col-form-label col-form-label-sm" for="{{ field.id_for_label }}">{{ field.label }}</label>
        <div class="col-sm-9">
            {{ field }}
            {% if field.help_text %}<div class="form-text small">{{ field.help_text }}</div>{% endif %}
            {% for error in field.errors %}<div class="invalid-feedback d-block">{{ error }}</div>{% endfor %}
        </div>
    </div>
    {% endfor %}
</fieldset>
{% endfor %}
```

- [ ] **Step 4: Create SplicePlanQuickAddFormView**

Add to `netbox_fms/views.py`:

```python
class SplicePlanQuickAddFormView(View):
    """Return rendered SplicePlanForm HTML for the quick-add modal."""

    def get(self, request):
        from django.http import HttpResponse

        closure_id = request.GET.get("closure_id")
        initial = {}
        if closure_id:
            initial["closure"] = closure_id
        form = SplicePlanForm(initial=initial)
        html = render(
            request,
            "netbox_fms/spliceplan_quick_add_form.html",
            {"form": form},
        ).content.decode()
        return HttpResponse(html)
```

- [ ] **Step 5: Add URL for the form view**

Add to `netbox_fms/urls.py`, in the SplicePlan section, **before** the `splice-plans/add/` path:

```python
    path("splice-plans/quick-add-form/", views.SplicePlanQuickAddFormView.as_view(), name="spliceplan_quick_add_form"),
```

- [ ] **Step 6: Run tests**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/test_api.py -v
```
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add netbox_fms/api/views.py netbox_fms/views.py netbox_fms/urls.py netbox_fms/templates/netbox_fms/spliceplan_quick_add_form.html tests/test_api.py
git commit -m "feat: add quick-add API and form view for splice plans"
```

---

### Task 12: Update templates and views for unified editor

**Files:**
- Modify: `netbox_fms/templates/netbox_fms/device_splice_editor.html`
- Modify: `netbox_fms/templates/netbox_fms/splice_editor.html`
- Modify: `netbox_fms/views.py:593-657`

- [ ] **Step 1: Update DeviceSpliceEditorView**

In `netbox_fms/views.py`, modify the `DeviceSpliceEditorView.get()` method:

```python
    def get(self, request, pk):
        device = get_object_or_404(Device, pk=pk)
        plan = SplicePlan.objects.filter(closure=device).first()
        context_mode = "edit" if plan else "view"

        return render(
            request,
            "netbox_fms/device_splice_editor.html",
            {
                "object": device,
                "device": device,
                "plan": plan,
                "context_mode": context_mode,
                "tab": self.tab,
            },
        )
```

- [ ] **Step 2: Rewrite device_splice_editor.html**

Replace the entire content of `netbox_fms/templates/netbox_fms/device_splice_editor.html`:

```html
{% extends 'dcim/device/base.html' %}
{% load static %}
{% load helpers %}
{% load i18n %}

{% block title %}{% trans "Splice Editor" %}: {{ device }}{% endblock %}

{% block head %}
{{ block.super }}
<link rel="stylesheet" href="{% static 'netbox_fms/css/splice_editor.css' %}">
{% endblock %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-12">
        <div class="card">
            <h5 class="card-header d-flex justify-content-between align-items-center">
                <span>
                    {% trans "Splice Editor" %}{% if plan %} &mdash; {{ plan.name }}{% endif %}
                </span>
                {% if plan %}
                <span class="badge bg-{{ plan.status }}">{{ plan.get_status_display }}</span>
                {% endif %}
            </h5>
            <div class="card-body p-0">
                <!-- Toolbar -->
                <div class="splice-toolbar p-2 border-bottom" id="splice-toolbar">
                    <div class="btn-group me-3" role="group">
                        <button type="button" class="btn btn-sm btn-outline-primary active" data-mode="single" title="{% trans 'Single splice mode' %}">
                            <i class="mdi mdi-ray-start-end"></i> {% trans "Single" %}
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-primary" data-mode="sequential" title="{% trans 'Sequential bulk splice mode' %}">
                            <i class="mdi mdi-format-list-numbered"></i> {% trans "Sequential" %}
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-danger" data-mode="delete" title="{% trans 'Delete splice mode' %}">
                            <i class="mdi mdi-close"></i> {% trans "Delete" %}
                        </button>
                    </div>
                    {% if plan %}
                    <a href="{{ plan.get_absolute_url }}" class="btn btn-sm btn-outline-secondary ms-2">
                        <i class="mdi mdi-eye"></i> {% trans "Plan Details" %}
                    </a>
                    {% endif %}
                    <span class="text-muted small ms-3">{% trans "Scroll each column independently. Splicing works across or within sides." %}</span>
                </div>

                <!-- D3 splice canvas -->
                <div class="splice-editor-container" id="splice-canvas-container"></div>

                <!-- Status bar -->
                <div class="p-2 border-top text-muted small" id="splice-status">
                    {% trans "Loading strands..." %}
                </div>
            </div>
        </div>
    </div>
</div>
<script>
    window.SPLICE_EDITOR_CONFIG = {
        deviceId: {{ device.pk }},
        planId: {{ plan.pk|default:"null" }},
        contextMode: "{{ context_mode }}",
        planStatus: "{{ plan.status|default:'' }}",
        strandsUrl: "{% url 'plugins-api:netbox_fms-api:closure_strands' device_id=device.pk %}",
        bulkUpdateUrl: {% if plan %}"{% url 'plugins-api:netbox_fms-api:spliceplan-bulk-update-entries' pk=plan.pk %}"{% else %}null{% endif %},
        quickAddFormUrl: "{% url 'plugins:netbox_fms:spliceplan_quick_add_form' %}?closure_id={{ device.pk }}",
        quickAddApiUrl: "{% url 'plugins-api:netbox_fms-api:spliceplan-quick-add' %}",
        csrfToken: "{{ csrf_token }}",
    };
</script>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script src="{% static 'netbox_fms/dist/splice-editor.min.js' %}"></script>
{% endblock %}
```

- [ ] **Step 3: Update splice_editor.html (standalone plan editor)**

Replace the content of `netbox_fms/templates/netbox_fms/splice_editor.html`:

```html
{% extends 'generic/object.html' %}
{% load static %}
{% load helpers %}
{% load i18n %}

{% block title %}{% trans "Splice Editor" %}: {{ object }}{% endblock %}

{% block head %}
{{ block.super }}
<link rel="stylesheet" href="{% static 'netbox_fms/css/splice_editor.css' %}">
{% endblock %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-12">
        <div class="card">
            <h5 class="card-header d-flex justify-content-between align-items-center">
                <span>{% trans "Splice Editor" %} &mdash; {{ object.name }}</span>
                <span class="badge bg-{{ object.status }}">{{ object.get_status_display }}</span>
            </h5>
            <div class="card-body p-0">
                <!-- Toolbar -->
                <div class="splice-toolbar p-2 border-bottom" id="splice-toolbar">
                    <div class="btn-group me-3" role="group">
                        <button type="button" class="btn btn-sm btn-outline-primary active" data-mode="single" title="{% trans 'Single splice mode' %}">
                            <i class="mdi mdi-ray-start-end"></i> {% trans "Single" %}
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-primary" data-mode="sequential" title="{% trans 'Sequential bulk splice mode' %}">
                            <i class="mdi mdi-format-list-numbered"></i> {% trans "Sequential" %}
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-danger" data-mode="delete" title="{% trans 'Delete splice mode' %}">
                            <i class="mdi mdi-close"></i> {% trans "Delete" %}
                        </button>
                    </div>
                    <a href="{{ object.get_absolute_url }}" class="btn btn-sm btn-outline-secondary ms-2">
                        <i class="mdi mdi-arrow-left"></i> {% trans "Back to Plan" %}
                    </a>
                    <span class="text-muted small ms-3">{% trans "Scroll each column independently. Splicing works across or within sides." %}</span>
                </div>

                <!-- D3 splice canvas -->
                <div class="splice-editor-container" id="splice-canvas-container"></div>

                <!-- Status bar -->
                <div class="p-2 border-top text-muted small" id="splice-status">
                    {% trans "Loading strands..." %}
                </div>
            </div>
        </div>
    </div>
</div>
<script>
    window.SPLICE_EDITOR_CONFIG = {
        deviceId: {{ object.closure_id }},
        planId: {{ object.pk }},
        contextMode: "plan-edit",
        planStatus: "{{ object.status }}",
        strandsUrl: "{% url 'plugins-api:netbox_fms-api:closure_strands' device_id=object.closure_id %}",
        bulkUpdateUrl: "{% url 'plugins-api:netbox_fms-api:spliceplan-bulk-update-entries' pk=object.pk %}",
        quickAddFormUrl: "",
        quickAddApiUrl: "",
        csrfToken: "{{ csrf_token }}",
    };
</script>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script src="{% static 'netbox_fms/dist/splice-editor.min.js' %}"></script>
{% endblock %}
```

- [ ] **Step 4: Update SpliceEditorView to pass context_mode**

In `netbox_fms/views.py`, modify `SpliceEditorView`:

```python
class SpliceEditorView(View):
    """Visual splice editor for a SplicePlan."""

    def get(self, request, pk):
        plan = get_object_or_404(SplicePlan.objects.select_related("closure"), pk=pk)
        return render(request, "netbox_fms/splice_editor.html", {
            "object": plan,
            "context_mode": "plan-edit",
        })
```

- [ ] **Step 5: Run full test suite**

Run:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add netbox_fms/templates/netbox_fms/device_splice_editor.html netbox_fms/templates/netbox_fms/splice_editor.html netbox_fms/views.py
git commit -m "feat: update templates and views for unified splice editor"
```

---

## Chunk 3: CSS Updates, Cleanup & Verification

### Task 13: CSS updates for ghost lines and pending states

**Files:**
- Modify: `netbox_fms/static/netbox_fms/css/splice_editor.css`

- [ ] **Step 1: Add new CSS rules**

Append to `netbox_fms/static/netbox_fms/css/splice_editor.css`:

```css
/* Pending splice states */
.splice-link.pending-add {
    stroke: var(--bs-success, #198754);
    stroke-width: 2;
    opacity: 0.9;
    pointer-events: none;
}

.splice-link.pending-delete {
    stroke: var(--bs-danger, #dc3545);
    stroke-width: 2;
    stroke-dasharray: 6, 3;
    opacity: 0.8;
    pointer-events: none;
}

/* Ghost splice (existing but pending change) */
.splice-link.ghost {
    opacity: 0.2;
    stroke-width: 1;
}

/* Save button pulse */
#splice-save-btn:not(.d-none) {
    animation: save-pulse 2s ease-in-out infinite;
}

@keyframes save-pulse {
    0%, 100% { box-shadow: none; }
    50% { box-shadow: 0 0 0 3px rgba(25, 135, 84, 0.3); }
}

/* Sequential count selector */
#sequential-count input[type="number"] {
    text-align: center;
    -moz-appearance: textfield;
}

#sequential-count input[type="number"]::-webkit-outer-spin-button,
#sequential-count input[type="number"]::-webkit-inner-spin-button {
    -webkit-appearance: none;
    margin: 0;
}
```

- [ ] **Step 2: Commit**

```bash
git add netbox_fms/static/netbox_fms/css/splice_editor.css
git commit -m "style: add CSS for pending splice states and ghost lines"
```

---

### Task 14: Verify API URL names and fix any mismatches

**Files:**
- Verify: `netbox_fms/api/urls.py` — DRF auto-generates URL names from ViewSet action names

- [ ] **Step 1: Verify URL names generated by DRF**

DRF's `DefaultRouter` generates URL names as `{basename}-{url_name}` where `url_name` comes from the `@action` decorator's `url_path`. For `SplicePlanViewSet`:
- `@action(url_path="bulk-update")` on method `bulk_update_entries` generates URL name: `spliceplan-bulk-update-entries`
- `@action(url_path="quick-add", detail=False)` on method `quick_add` generates URL name: `spliceplan-quick-add`

Verify by running:
```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "
import django; django.setup()
from django.urls import reverse
# Test that URL names resolve
try:
    print('bulk-update:', reverse('plugins-api:netbox_fms-api:spliceplan-bulk-update-entries', kwargs={'pk': 1}))
except Exception as e:
    print('bulk-update ERROR:', e)
try:
    print('quick-add:', reverse('plugins-api:netbox_fms-api:spliceplan-quick-add'))
except Exception as e:
    print('quick-add ERROR:', e)
try:
    print('quick-add-form:', reverse('plugins:netbox_fms:spliceplan_quick_add_form'))
except Exception as e:
    print('quick-add-form ERROR:', e)
"
```

Fix any URL name mismatches found (adjust `@action` `url_name` parameter or template references).

- [ ] **Step 2: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve API URL name mismatches"
```

---

### Task 15: Remove old splice_editor.js

**Files:**
- Delete: `netbox_fms/static/netbox_fms/js/splice_editor.js`

- [ ] **Step 1: Delete old JS file**

```bash
rm netbox_fms/static/netbox_fms/js/splice_editor.js
```

- [ ] **Step 2: Verify no remaining references**

Search for `splice_editor.js` references in templates:
```bash
grep -r "splice_editor.js" netbox_fms/templates/ || echo "No references found"
```
Expected: No references (templates now reference `dist/splice-editor.min.js`).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove old splice_editor.js (replaced by TypeScript)"
```

---

### Task 16: Full verification

- [ ] **Step 1: Run lint**

```bash
ruff check --fix netbox_fms/
ruff format netbox_fms/
```

- [ ] **Step 2: Run TypeScript type checking**

```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npm run typecheck
```

- [ ] **Step 3: Rebuild TypeScript**

```bash
cd /opt/netbox-fms/netbox_fms/static/netbox_fms && npm run build
```

- [ ] **Step 4: Run full test suite**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-fms/tests/ -v
```

- [ ] **Step 5: Verify all imports**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_fms.models import *; from netbox_fms.forms import *; from netbox_fms.filters import *; from netbox_fms.views import *"
```

- [ ] **Step 6: Final commit if any remaining changes**

```bash
git add -A
git commit -m "chore: lint and verification pass"
```
