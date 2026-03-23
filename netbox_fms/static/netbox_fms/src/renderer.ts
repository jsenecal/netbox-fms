declare const d3: any;

import {
  EditorState,
  COLUMN_WIDTH,
  STRAND_HEIGHT,
  STRAND_DOT_R,
  TUBE_ROW_H,
  CABLE_ROW_H,
  GROUP_PAD,
  HEADER_HEIGHT,
  TOP_PAD,
  TUBE_INDENT,
  TUBE_DOT_R,
  MIN_HEIGHT,
} from './state';
import type { LayoutNode, SpliceEntry } from './types';

/** Position entry used when building the link node map. */
interface NodePosition {
  x: number;
  y: number;
  hidden: boolean;
  color?: string;
}

/**
 * D3-based SVG renderer for the splice editor.
 *
 * Draws two scrollable columns of cable/tube/strand nodes with splice link
 * curves between them.  Supports pending-add, pending-delete, re-splice, and
 * collapsed-tube visual states.
 */
export class SpliceRenderer {
  private state: EditorState;
  private containerEl: HTMLElement;
  private onStrandClick: (node: LayoutNode, side: 'left' | 'right') => void;
  private onSpliceClick: (entry: SpliceEntry, event: MouseEvent) => void;
  private onTubeToggle: (node: LayoutNode, nodes: LayoutNode[]) => void;
  private onCableMove: ((cableId: number) => void) | null = null;

  private containerWidth: number;

  // D3 selections — typed as `any` because d3 is an untyped global.
  private svg: any;
  private defs: any;
  private leftBg: any;
  private rightBg: any;
  private rightHeader: any;
  private linksGroup: any;
  private linksHitGroup: any;
  private leftGroup: any;
  private leftInner: any;
  private rightGroup: any;
  private rightInner: any;
  private linkGen: any;
  private wheelAttached = false;
  private currentSvgHeight = 0;

  constructor(
    state: EditorState,
    containerEl: HTMLElement,
    onStrandClick: (node: LayoutNode, side: 'left' | 'right') => void,
    onSpliceClick: (entry: SpliceEntry, event: MouseEvent) => void,
    onTubeToggle: (node: LayoutNode, nodes: LayoutNode[]) => void,
  ) {
    this.state = state;
    this.containerEl = containerEl;
    this.onStrandClick = onStrandClick;
    this.onSpliceClick = onSpliceClick;
    this.onTubeToggle = onTubeToggle;

    this.containerWidth = containerEl.clientWidth || 900;

    // --- SVG scaffold ---
    this.svg = d3
      .select(containerEl)
      .append('svg')
      .attr('class', 'splice-editor-svg')
      .attr('width', this.containerWidth);

    this.defs = this.svg.append('defs');

    // Clip paths for left / right columns
    this.defs
      .append('clipPath')
      .attr('id', 'clip-left')
      .append('rect')
      .attr('x', 0)
      .attr('y', HEADER_HEIGHT)
      .attr('width', COLUMN_WIDTH);
    this.defs
      .append('clipPath')
      .attr('id', 'clip-right')
      .append('rect')
      .attr('y', HEADER_HEIGHT)
      .attr('width', COLUMN_WIDTH);

    // Column backgrounds — plain rects, colors set in render() to match current theme
    this.leftBg = this.svg
      .append('rect')
      .attr('class', 'column-bg')
      .attr('x', 0)
      .attr('y', 0)
      .attr('width', COLUMN_WIDTH);
    this.rightBg = this.svg
      .append('rect')
      .attr('class', 'column-bg')
      .attr('y', 0)
      .attr('width', COLUMN_WIDTH);

    // Column header placeholder (kept for layout spacing)
    this.rightHeader = { attr: () => this.rightHeader }; // no-op stub

    // Render order: links behind, columns in middle, link hit areas on top
    this.linksGroup = this.svg.append('g').attr('class', 'links-group');
    this.leftGroup = this.svg.append('g').attr('clip-path', 'url(#clip-left)');
    this.leftInner = this.leftGroup.append('g');
    this.rightGroup = this.svg.append('g');
    this.rightInner = this.rightGroup.append('g');
    this.linksHitGroup = this.svg.append('g').attr('class', 'links-hit-group');

    // D3 horizontal link generator
    this.linkGen = d3
      .linkHorizontal()
      .x((d: NodePosition) => d.x)
      .y((d: NodePosition) => d.y);
  }

  // -------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------

  /** Set callback for cable move button clicks. */
  setOnCableMove(cb: (cableId: number) => void): void {
    this.onCableMove = cb;
  }

  /** Full re-render of the SVG contents. */
  render(): void {
    // Recalculate container width on every render so the SVG adapts when
    // the detail panel opens/closes or the window is resized.
    this.containerWidth = this.containerEl.clientWidth || 900;
    this.svg.attr('width', this.containerWidth);

    const leftHeight = this.state.columnHeight(this.state.leftNodes);
    const rightHeight = this.state.columnHeight(this.state.rightNodes);
    const svgHeight = Math.max(leftHeight, rightHeight, MIN_HEIGHT) + HEADER_HEIGHT;
    const rightX = this.containerWidth - COLUMN_WIDTH;

    this.svg.attr('height', svgHeight);

    // Update backgrounds — read theme on every render
    const isDark = document.body.getAttribute('data-bs-theme') === 'dark';
    const colBg = isDark ? '#001423' : '#ffffff';
    const colBorder = isDark ? '#1a2d3d' : '#dee2e6';
    const gapBg = isDark ? '#000d17' : '#f0f0f0';
    this.containerEl.style.background = gapBg;

    this.leftBg.attr('height', svgHeight).attr('fill', colBg).attr('stroke', colBorder);
    this.rightBg.attr('x', rightX).attr('height', svgHeight).attr('fill', colBg).attr('stroke', colBorder);

    // Update header
    this.rightHeader.attr('x', rightX + COLUMN_WIDTH / 2);

    // Update clip rects
    this.defs.select('#clip-left rect').attr('height', svgHeight);
    this.defs.select('#clip-right rect').attr('x', rightX).attr('height', svgHeight);
    this.rightGroup.attr('clip-path', 'url(#clip-right)');

    this.renderColumn(this.leftInner, this.state.leftNodes, 'left', 0);
    this.renderColumn(this.rightInner, this.state.rightNodes, 'right', rightX);
    this.renderLinks();
    this.setupDrag(svgHeight);
  }

  /** Re-measure container and re-render. */
  handleResize(): void {
    this.containerWidth = this.containerEl.clientWidth || 900;
    this.svg.attr('width', this.containerWidth);
    this.render();
  }

  // -------------------------------------------------------------------
  // Column rendering
  // -------------------------------------------------------------------

  private renderColumn(
    group: any,
    nodes: LayoutNode[],
    side: 'left' | 'right',
    xOffset: number,
  ): void {
    group.selectAll('*').remove();
    const g = group.append('g').attr('transform', `translate(0,${HEADER_HEIGHT})`);

    for (const node of nodes) {
      if (node.hidden) continue;
      if (node.type === 'cable') {
        this.renderCableNode(g, node, side, xOffset);
      } else if (node.type === 'tube') {
        this.renderTubeNode(g, node, side, xOffset, nodes);
      } else if (node.type === 'strand') {
        this.renderStrandNode(g, node, side, xOffset);
      }
    }
  }

  private renderCableNode(
    g: any,
    node: LayoutNode,
    side: 'left' | 'right',
    xOffset: number,
  ): void {
    const cg = g.append('g').attr('class', 'cable-group');
    const textX = xOffset + (side === 'left' ? 8 : COLUMN_WIDTH - 8);
    const anchor = side === 'left' ? 'start' : 'end';

    cg.append('text')
      .attr('class', 'cable-label')
      .attr('x', textX)
      .attr('y', node.y + 4)
      .attr('text-anchor', anchor)
      .text(node.label ?? '');

    // Subtitle: fiber type + strand count
    if (node.fiberType || node.strandCount) {
      const sub: string[] = [];
      if (node.fiberType) sub.push(node.fiberType);
      if (node.strandCount) sub.push(node.strandCount + 'F');
      cg.append('text')
        .attr('class', 'cable-subtitle')
        .attr('x', textX)
        .attr('y', node.y + 14)
        .attr('text-anchor', anchor)
        .text(sub.join(' \u2022 '));
    }

    // Far-end device link (navigate to the closure at the other end)
    if (node.farDeviceName && node.farDeviceUrl) {
      const arrow = side === 'left' ? '\u2192 ' : '\u2190 ';
      const linkX = textX;
      const linkY = node.y + (node.fiberType || node.strandCount ? 23 : 14);
      const linkEl = cg.append('a')
        .attr('href', node.farDeviceUrl + 'splice-editor/')
        .attr('target', '_self');
      linkEl.append('text')
        .attr('class', 'cable-far-device')
        .attr('x', linkX)
        .attr('y', linkY)
        .attr('text-anchor', anchor)
        .text(arrow + node.farDeviceName);
    }

    // Move-to-other-side button
    if (this.onCableMove && node.cableId) {
      const label = side === 'left' ? 'move right \u25b6' : '\u25c0 move left';
      const btnX = xOffset + (side === 'left' ? COLUMN_WIDTH - 12 : 12);
      const btnAnchor = side === 'left' ? 'end' : 'start';

      const mutedColor = getComputedStyle(document.body).getPropertyValue('--bs-secondary-color').trim() || '#6c757d';
      const hoverColor = getComputedStyle(document.body).getPropertyValue('--bs-primary').trim() || '#0d6efd';

      const btn = cg.append('text')
        .attr('class', 'cable-move-btn')
        .attr('x', btnX)
        .attr('y', node.y + 4)
        .attr('text-anchor', btnAnchor)
        .attr('font-size', '9px')
        .attr('fill', mutedColor)
        .attr('cursor', 'pointer')
        .text(label);

      btn.on('click', () => {
        this.onCableMove!(node.cableId!);
      });

      btn.on('mouseover', (_event: MouseEvent, _d: unknown, _i?: number) => {
        btn.attr('fill', hoverColor);
      });
      btn.on('mouseout', (_event: MouseEvent, _d: unknown, _i?: number) => {
        btn.attr('fill', mutedColor);
      });
    }
  }

  private renderTubeNode(
    g: any,
    node: LayoutNode,
    side: 'left' | 'right',
    xOffset: number,
    allNodes: LayoutNode[],
  ): void {
    const tg = g.append('g').attr('class', 'tube-group').style('cursor', 'pointer');
    const dotX = xOffset + (side === 'left' ? TUBE_INDENT : COLUMN_WIDTH - TUBE_INDENT);
    const textX = xOffset + (side === 'left' ? TUBE_INDENT + 10 : COLUMN_WIDTH - TUBE_INDENT - 10);
    const anchor = side === 'left' ? 'start' : 'end';

    // Tube color dot
    tg.append('circle')
      .attr('class', 'tube-dot')
      .attr('cx', dotX)
      .attr('cy', node.y)
      .attr('r', TUBE_DOT_R)
      .attr('fill', '#' + (node.color || 'ccc'));

    // Stripe indicator
    if (node.stripeColor) {
      tg.append('circle')
        .attr('cx', dotX + (side === 'left' ? -3 : 3))
        .attr('cy', node.y - 3)
        .attr('r', 2)
        .attr('fill', '#' + node.stripeColor)
        .attr('stroke', '#dee2e6')
        .attr('stroke-width', 0.5);
    }

    // Label with strand count and collapse indicator
    const icon = node.collapsed ? '\u25b6 ' : '\u25bc ';
    const countStr = ' (' + (node.strandCount || '?') + 'F)';
    tg.append('text')
      .attr('class', 'tube-label')
      .attr('x', textX)
      .attr('y', node.y + 3)
      .attr('text-anchor', anchor)
      .text(icon + (node.label ?? '') + countStr);

    tg.on('click', () => {
      this.onTubeToggle(node, allNodes);
    });
  }

  private renderStrandNode(
    g: any,
    node: LayoutNode,
    side: 'left' | 'right',
    xOffset: number,
  ): void {
    const dotX = side === 'left' ? xOffset + COLUMN_WIDTH - 14 : xOffset + 14;
    const indent = node.tubeId !== undefined ? TUBE_INDENT + 10 : 8;
    const textX = side === 'left' ? xOffset + indent : xOffset + COLUMN_WIDTH - indent;
    const anchor = side === 'left' ? 'start' : 'end';

    const isSpliced = !!(node.liveSplicedTo || node.planSplicedTo);
    const isSelected = this.state.selectedStrandId === node.id;
    const isPendingAdd = node.id !== undefined && this.state.isStrandPendingAdd(node.id);
    const isPendingDelete = node.id !== undefined && this.state.getStrandPendingState(node.id) === 'remove';
    const isProtected = !!node.isProtected;
    const sg = g
      .append('g')
      .attr('class', 'strand-node')
      .classed('spliced', isSpliced)
      .classed('selected', isSelected)
      .classed('pending-taken', isPendingAdd)
      .classed('pending-delete', isPendingDelete)
      .classed('protected', isProtected)
      .datum(node);

    // Tube color accent bar
    if (node.tubeColor) {
      const barX = side === 'left' ? xOffset + indent - 6 : xOffset + COLUMN_WIDTH - indent + 4;
      sg.append('rect')
        .attr('x', barX)
        .attr('y', node.y - STRAND_HEIGHT / 2 + 3)
        .attr('width', 3)
        .attr('height', STRAND_HEIGHT - 4)
        .attr('rx', 1)
        .attr('fill', '#' + node.tubeColor)
        .attr('opacity', 0.6);
    }

    // Invisible hit area for easier clicking (wider than the visible row)
    sg.append('rect')
      .attr('class', 'strand-hit-area')
      .attr('x', xOffset)
      .attr('y', node.y - STRAND_HEIGHT / 2 + 1)
      .attr('width', COLUMN_WIDTH)
      .attr('height', STRAND_HEIGHT)
      .attr('fill', 'transparent')
      .attr('cursor', 'pointer');

    // Selection glow ring (behind dot)
    if (isSelected) {
      sg.append('circle')
        .attr('class', 'strand-glow')
        .attr('cx', dotX)
        .attr('cy', node.y)
        .attr('r', STRAND_DOT_R + 5)
        .attr('fill', 'none')
        .attr('stroke', getComputedStyle(document.body).getPropertyValue('--bs-primary').trim() || '#0d6efd')
        .attr('stroke-width', 2)
        .attr('stroke-opacity', 0.6);
    }

    // Subtle glow behind the dot for visibility
    const dotDark = document.body.getAttribute('data-bs-theme') === 'dark';
    const dotGlowColor = dotDark ? '#4dc9c0' : '#333333';
    sg.append('circle')
      .attr('class', 'strand-dot-glow')
      .attr('cx', dotX)
      .attr('cy', node.y)
      .attr('r', STRAND_DOT_R + 3)
      .attr('fill', dotGlowColor)
      .attr('opacity', 0.12);

    // Strand fiber dot (EIA-598 color)
    sg.append('circle')
      .attr('class', 'strand-dot')
      .attr('cx', dotX)
      .attr('cy', node.y)
      .attr('r', STRAND_DOT_R)
      .attr('fill', '#' + (node.color || 'ccc'))
      .attr('stroke', dotDark ? '#adb5bd' : '#212529')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.5);

    // Strand name
    sg.append('text')
      .attr('class', 'strand-name')
      .attr('x', textX)
      .attr('y', node.y + 3)
      .attr('text-anchor', anchor)
      .text(node.label ?? '');

    // Ribbon badge
    if (node.ribbonName) {
      const ribbonX = side === 'left' ? dotX - 20 : dotX + 20;
      sg.append('text')
        .attr('x', ribbonX)
        .attr('y', node.y + 3)
        .attr('text-anchor', 'middle')
        .attr('font-size', '8px')
        .attr('fill', '#' + (node.ribbonColor || '999'))
        .attr('font-weight', '600')
        .text('R');
    }

    // Lock icon + circuit name link for protected strands
    if (isProtected) {
      const lockX = side === 'left' ? dotX - 16 : dotX + 16;
      sg.append('text')
        .attr('x', lockX)
        .attr('y', node.y + 3)
        .attr('text-anchor', 'middle')
        .attr('font-size', '9px')
        .attr('fill', '#dc3545')
        .attr('opacity', 0.8)
        .text('\uD83D\uDD12');

      if (node.circuitName) {
        const circuitX = side === 'left' ? lockX - 12 : lockX + 12;
        const circuitAnchor = side === 'left' ? 'end' : 'start';
        if (node.circuitUrl) {
          const linkEl = sg.append('a')
            .attr('href', node.circuitUrl)
            .attr('target', '_self');
          linkEl.append('text')
            .attr('x', circuitX)
            .attr('y', node.y + 3)
            .attr('text-anchor', circuitAnchor)
            .attr('font-size', '9px')
            .attr('fill', getComputedStyle(document.body).getPropertyValue('--bs-link-color').trim() || '#0d6efd')
            .attr('cursor', 'pointer')
            .text(node.circuitName);
        } else {
          sg.append('text')
            .attr('x', circuitX)
            .attr('y', node.y + 3)
            .attr('text-anchor', circuitAnchor)
            .attr('font-size', '9px')
            .attr('fill', '#dc3545')
            .attr('opacity', 0.7)
            .text(node.circuitName);
        }
      }
    }

    // Hover title
    let title = node.label ?? '';
    if (node.tubeName) title += ' | Tube: ' + node.tubeName;
    if (node.ribbonName) title += ' | Ribbon: ' + node.ribbonName;
    if (node.frontPortId) title += ' | Port: #' + node.frontPortId;
    if (isProtected && node.circuitName) title += ' | Protected by: ' + node.circuitName;
    sg.append('title').text(title);

    // Protected strands are non-interactive
    if (isProtected) {
      sg.style('opacity', '0.7').style('cursor', 'not-allowed');
    } else {
      sg.on('click', (event: Event) => {
        event.stopPropagation();
        this.onStrandClick(node, side);
      });
    }
  }

  // -------------------------------------------------------------------
  // Links
  // -------------------------------------------------------------------

  private renderLinks(): void {
    this.linksGroup.selectAll('*').remove();
    this.linksHitGroup.selectAll('*').remove();

    const rightX = this.containerWidth - COLUMN_WIDTH;
    const nodeMap = new Map<number, NodePosition>();

    // Build position map for all strands (including color for gradients)
    for (const n of this.state.leftNodes) {
      if (n.type === 'strand' && n.id !== undefined) {
        nodeMap.set(n.id, {
          x: COLUMN_WIDTH - 14,
          y: n.y + HEADER_HEIGHT + this.state.leftOffset,
          hidden: n.hidden,
          color: n.color,
        });
      }
    }
    for (const n of this.state.rightNodes) {
      if (n.type === 'strand' && n.id !== undefined) {
        nodeMap.set(n.id, {
          x: rightX + 14,
          y: n.y + HEADER_HEIGHT + this.state.rightOffset,
          hidden: n.hidden,
          color: n.color,
        });
      }
    }

    // Clear old link gradients
    this.defs.selectAll('.link-gradient').remove();

    // Track strands involved in re-splices so we can avoid double-rendering
    const reSplices = this.state.getReSplices();
    const reSpliceOldPairs = new Set<string>();
    for (const [strandId, info] of reSplices) {
      const key1 = Math.min(strandId, info.oldTarget) + '-' + Math.max(strandId, info.oldTarget);
      reSpliceOldPairs.add(key1);
    }

    // Track strands that are being re-spliced elsewhere (pending-add to a different target)
    const pendingAddStrands = new Set<number>();
    for (const p of this.state.pendingChanges) {
      if (p.action === 'add') {
        pendingAddStrands.add(p.fiberA);
        pendingAddStrands.add(p.fiberB);
      }
    }

    // --- Existing splice entries (live first so plan-only renders on top) ---
    const sortedEntries = [...this.state.spliceEntries].sort((a, b) => {
      const aOrder = (a.isLive && !a.isPlan) ? 0 : (a.isLive && a.isPlan) ? 1 : 2;
      const bOrder = (b.isLive && !b.isPlan) ? 0 : (b.isLive && b.isPlan) ? 1 : 2;
      return aOrder - bOrder;
    });
    for (const entry of sortedEntries) {
      const a = nodeMap.get(entry.sourceId);
      const b = nodeMap.get(entry.targetId);
      if (!a || !b) continue;

      const pathD = this.buildLinkPath(a, b);
      const isPendingDelete = this.state.isSplicePendingDelete(entry.sourceId, entry.targetId);
      const entryKey =
        Math.min(entry.sourceId, entry.targetId) + '-' + Math.max(entry.sourceId, entry.targetId);
      const isReSpliceOld = reSpliceOldPairs.has(entryKey);
      // If either strand is being spliced elsewhere, dim this line
      const isSuperseded = !isPendingDelete && !isReSpliceOld &&
        (pendingAddStrands.has(entry.sourceId) || pendingAddStrands.has(entry.targetId));

      const gradId = `link-grad-${entry.sourceId}-${entry.targetId}`;
      const gradUrl = this.createLinkGradient(a, b, gradId);

      if (isPendingDelete || isReSpliceOld || isSuperseded) {
        // Ghost line (faded, unselectable)
        this.linksGroup
          .append('path')
          .attr('class', 'splice-link ghost')
          .attr('d', pathD)
          .attr('stroke', gradUrl)
          .attr('opacity', 0.15)
          .attr('stroke-width', 1)
          .attr('fill', 'none')
          .attr('pointer-events', 'none');

        // Dashed overlay — red for explicit delete, amber for superseded
        if (isPendingDelete || isReSpliceOld) {
          this.linksGroup
            .append('path')
            .attr('class', 'splice-link pending-delete')
            .attr('d', pathD)
            .attr('stroke-dasharray', '4,3')
            .attr('fill', 'none');
        }
      } else {
        // Invisible wide hit area for clicking — in top-most group so it's above strand hit areas
        const hitEntry = entry;
        this.linksHitGroup
          .append('path')
          .attr('class', 'splice-link-hit')
          .attr('d', pathD)
          .attr('stroke', 'transparent')
          .attr('stroke-width', 14)
          .attr('fill', 'none')
          .attr('cursor', 'pointer')
          .style('pointer-events', 'stroke')
          .on('click', (event: MouseEvent) => {
            this.onSpliceClick(hitEntry, event);
          });

        const sameSide = Math.abs(a.x - b.x) < 10;
        const isSelected = this.state.isSpliceSelected(entry.sourceId, entry.targetId);

        // Subtle glow behind line — light halo in dark mode, dark halo in light mode
        const dark = document.body.getAttribute('data-bs-theme') === 'dark';
        const glowColor = dark ? '#4dc9c0' : '#333333';
        this.linksGroup
          .append('path')
          .attr('class', 'splice-link-glow')
          .attr('d', pathD)
          .attr('stroke', glowColor)
          .attr('stroke-width', 6)
          .attr('stroke-opacity', 0.12)
          .attr('fill', 'none')
          .attr('pointer-events', 'none');

        // Selection highlight (bright outline behind the line)
        if (isSelected) {
          const selColor = getComputedStyle(document.body).getPropertyValue('--bs-primary').trim() || '#0d6efd';
          this.linksGroup
            .append('path')
            .attr('class', 'splice-link-selected')
            .attr('d', pathD)
            .attr('stroke', selColor)
            .attr('stroke-width', 6)
            .attr('stroke-opacity', 0.5)
            .attr('fill', 'none')
            .attr('pointer-events', 'none');
        }

        // Normal splice link with gradient
        const isPlanOnly = entry.isPlan && !entry.isLive;
        const path = this.linksGroup
          .append('path')
          .attr('class', 'splice-link')
          .classed('same-side', sameSide)
          .classed('plan-only', isPlanOnly)
          .attr('d', pathD)
          .attr('stroke', gradUrl)
          .attr('pointer-events', 'none')
          .datum(entry);

        if (isPlanOnly) {
          path.attr('stroke-dasharray', '8,4').attr('opacity', 0.7);
        }

        if (a.hidden || b.hidden) {
          path.attr('opacity', 0.2).attr('stroke-dasharray', '3,3');
        }
      }
    }

    // --- Pending add changes ---
    for (const pc of this.state.pendingChanges) {
      if (pc.action !== 'add') continue;

      const a = nodeMap.get(pc.fiberA);
      const b = nodeMap.get(pc.fiberB);
      if (!a || !b) continue;

      const pathD = this.buildLinkPath(a, b);
      const gradId = `link-grad-add-${pc.fiberA}-${pc.fiberB}`;
      const gradUrl = this.createLinkGradient(a, b, gradId);

      this.linksGroup
        .append('path')
        .attr('class', 'splice-link pending-add')
        .attr('d', pathD)
        .attr('stroke', gradUrl)
        .attr('fill', 'none');
    }
  }

  /** Build an SVG path string for a link between two node positions. */
  private buildLinkPath(a: NodePosition, b: NodePosition): string {
    if (Math.abs(a.x - b.x) < 10) {
      // Same-side splice: loop curve through center
      const loopX =
        a.x < this.containerWidth / 2
          ? Math.min(a.x + 120, this.containerWidth / 2 - 20)
          : Math.max(a.x - 120, this.containerWidth / 2 + 20);
      return (
        'M' + a.x + ',' + a.y +
        ' C' + loopX + ',' + a.y +
        ' ' + loopX + ',' + b.y +
        ' ' + b.x + ',' + b.y
      );
    }

    // Cross-side splice: d3 horizontal link
    const source = a.x < b.x ? a : b;
    const target = a.x < b.x ? b : a;
    return this.linkGen({ source, target }) as string;
  }

  /** Create an SVG gradient between two strand colors, return `url(#id)`. */
  private createLinkGradient(a: NodePosition, b: NodePosition, id: string): string {
    const colorA = '#' + (a.color || 'ccc');
    const colorB = '#' + (b.color || 'ccc');
    const grad = this.defs.append('linearGradient')
      .attr('class', 'link-gradient')
      .attr('id', id)
      .attr('gradientUnits', 'userSpaceOnUse')
      .attr('x1', a.x).attr('y1', a.y)
      .attr('x2', b.x).attr('y2', b.y);
    // Keep pure colors for 30% at each end, blend in the middle
    grad.append('stop').attr('offset', '0%').attr('stop-color', colorA);
    grad.append('stop').attr('offset', '30%').attr('stop-color', colorA);
    grad.append('stop').attr('offset', '70%').attr('stop-color', colorB);
    grad.append('stop').attr('offset', '100%').attr('stop-color', colorB);
    return `url(#${id})`;
  }

  // -------------------------------------------------------------------
  // Column drag / wheel scroll
  // -------------------------------------------------------------------

  private setupDrag(svgHeight: number): void {
    const rightX = this.containerWidth - COLUMN_WIDTH;
    const self = this;

    const leftDrag = d3.drag().on('drag', function (event: any) {
      const maxScroll = Math.max(
        0,
        self.state.columnHeight(self.state.leftNodes) + HEADER_HEIGHT - svgHeight,
      );
      self.state.leftOffset = Math.max(-maxScroll, Math.min(0, self.state.leftOffset + event.dy));
      self.leftInner.attr('transform', `translate(0,${self.state.leftOffset})`);
      self.renderLinks();
    });

    const rightDrag = d3.drag().on('drag', function (event: any) {
      const maxScroll = Math.max(
        0,
        self.state.columnHeight(self.state.rightNodes) + HEADER_HEIGHT - svgHeight,
      );
      self.state.rightOffset = Math.max(
        -maxScroll,
        Math.min(0, self.state.rightOffset + event.dy),
      );
      self.rightInner.attr('transform', `translate(0,${self.state.rightOffset})`);
      self.renderLinks();
    });

    this.leftBg.call(leftDrag).style('cursor', 'grab');
    this.rightBg.call(rightDrag).style('cursor', 'grab');

    // Wheel scroll — attach once on the container element
    this.currentSvgHeight = svgHeight;
    if (!this.wheelAttached) {
      this.wheelAttached = true;
      this.containerEl.addEventListener('wheel', (event: WheelEvent) => {
        const rect = this.containerEl.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const delta = -event.deltaY;
        const h = this.currentSvgHeight;

        if (mouseX < this.containerWidth / 2) {
          const maxL = Math.max(
            0,
            this.state.columnHeight(this.state.leftNodes) + HEADER_HEIGHT - h,
          );
          if (maxL > 0) {
            event.preventDefault();
            this.state.leftOffset = Math.max(-maxL, Math.min(0, this.state.leftOffset + delta));
            this.leftInner.attr('transform', `translate(0,${this.state.leftOffset})`);
            this.renderLinks();
          }
        } else {
          const maxR = Math.max(
            0,
            this.state.columnHeight(this.state.rightNodes) + HEADER_HEIGHT - h,
          );
          if (maxR > 0) {
            event.preventDefault();
            this.state.rightOffset = Math.max(-maxR, Math.min(0, this.state.rightOffset + delta));
            this.rightInner.attr('transform', `translate(0,${this.state.rightOffset})`);
            this.renderLinks();
          }
        }
      }, { passive: false });
    }
  }
}
