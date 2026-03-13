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
  private onSpliceClick: (entry: SpliceEntry) => void;
  private onTubeToggle: (node: LayoutNode, nodes: LayoutNode[]) => void;

  private containerWidth: number;

  // D3 selections — typed as `any` because d3 is an untyped global.
  private svg: any;
  private defs: any;
  private leftBg: any;
  private rightBg: any;
  private rightHeader: any;
  private linksGroup: any;
  private leftGroup: any;
  private leftInner: any;
  private rightGroup: any;
  private rightInner: any;
  private linkGen: any;

  constructor(
    state: EditorState,
    containerEl: HTMLElement,
    onStrandClick: (node: LayoutNode, side: 'left' | 'right') => void,
    onSpliceClick: (entry: SpliceEntry) => void,
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

    // Clip paths for left / right columns
    this.defs = this.svg.append('defs');
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

    // Column backgrounds
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

    // Column headers
    this.svg
      .append('text')
      .attr('class', 'column-header')
      .attr('x', COLUMN_WIDTH / 2)
      .attr('y', 18)
      .text('LEFT SIDE');
    this.rightHeader = this.svg
      .append('text')
      .attr('class', 'column-header')
      .attr('y', 18)
      .text('RIGHT SIDE');

    // Render order: links behind, columns on top
    this.linksGroup = this.svg.append('g').attr('class', 'links-group');
    this.leftGroup = this.svg.append('g').attr('clip-path', 'url(#clip-left)');
    this.leftInner = this.leftGroup.append('g');
    this.rightGroup = this.svg.append('g');
    this.rightInner = this.rightGroup.append('g');

    // D3 horizontal link generator
    this.linkGen = d3
      .linkHorizontal()
      .x((d: NodePosition) => d.x)
      .y((d: NodePosition) => d.y);
  }

  // -------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------

  /** Full re-render of the SVG contents. */
  render(): void {
    const leftHeight = this.state.columnHeight(this.state.leftNodes);
    const rightHeight = this.state.columnHeight(this.state.rightNodes);
    const svgHeight = Math.max(leftHeight, rightHeight, MIN_HEIGHT) + HEADER_HEIGHT;
    const rightX = this.containerWidth - COLUMN_WIDTH;

    this.svg.attr('height', svgHeight);

    // Update backgrounds
    this.leftBg.attr('height', svgHeight);
    this.rightBg.attr('x', rightX).attr('height', svgHeight);

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
        .attr('font-size', '9px')
        .attr('fill', '#6c757d')
        .text(sub.join(' \u2022 '));
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
    const sg = g
      .append('g')
      .attr('class', 'strand-node')
      .classed('spliced', isSpliced)
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

    // Strand fiber dot (EIA-598 color)
    sg.append('circle')
      .attr('class', 'strand-dot')
      .attr('cx', dotX)
      .attr('cy', node.y)
      .attr('r', STRAND_DOT_R)
      .attr('fill', '#' + (node.color || 'ccc'));

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

    // Hover title
    let title = node.label ?? '';
    if (node.tubeName) title += ' | Tube: ' + node.tubeName;
    if (node.ribbonName) title += ' | Ribbon: ' + node.ribbonName;
    if (node.frontPortId) title += ' | Port: #' + node.frontPortId;
    sg.append('title').text(title);

    sg.on('click', (event: Event) => {
      event.stopPropagation();
      this.onStrandClick(node, side);
    });
  }

  // -------------------------------------------------------------------
  // Links
  // -------------------------------------------------------------------

  private renderLinks(): void {
    this.linksGroup.selectAll('*').remove();

    const rightX = this.containerWidth - COLUMN_WIDTH;
    const nodeMap = new Map<number, NodePosition>();

    // Build position map for all strands
    for (const n of this.state.leftNodes) {
      if (n.type === 'strand' && n.id !== undefined) {
        nodeMap.set(n.id, {
          x: COLUMN_WIDTH - 14,
          y: n.y + HEADER_HEIGHT + this.state.leftOffset,
          hidden: n.hidden,
        });
      }
    }
    for (const n of this.state.rightNodes) {
      if (n.type === 'strand' && n.id !== undefined) {
        nodeMap.set(n.id, {
          x: rightX + 14,
          y: n.y + HEADER_HEIGHT + this.state.rightOffset,
          hidden: n.hidden,
        });
      }
    }

    // Track strands involved in re-splices so we can avoid double-rendering
    const reSplices = this.state.getReSplices();
    const reSpliceOldPairs = new Set<string>();
    for (const [strandId, info] of reSplices) {
      const key1 = Math.min(strandId, info.oldTarget) + '-' + Math.max(strandId, info.oldTarget);
      reSpliceOldPairs.add(key1);
    }

    // --- Existing splice entries ---
    for (const entry of this.state.spliceEntries) {
      const a = nodeMap.get(entry.sourceId);
      const b = nodeMap.get(entry.targetId);
      if (!a || !b) continue;

      const pathD = this.buildLinkPath(a, b);
      const isPendingDelete = this.state.isSplicePendingDelete(entry.sourceId, entry.targetId);
      const entryKey =
        Math.min(entry.sourceId, entry.targetId) + '-' + Math.max(entry.sourceId, entry.targetId);
      const isReSpliceOld = reSpliceOldPairs.has(entryKey);

      if (isPendingDelete || isReSpliceOld) {
        // Ghost line (faded original)
        this.linksGroup
          .append('path')
          .attr('class', 'splice-link')
          .attr('d', pathD)
          .attr('opacity', 0.2)
          .attr('stroke-width', 1)
          .datum(entry);

        // Dashed red overlay
        this.linksGroup
          .append('path')
          .attr('class', 'splice-link pending-delete')
          .attr('d', pathD)
          .attr('stroke', '#dc3545')
          .attr('stroke-dasharray', '4,3')
          .attr('stroke-width', 1.5)
          .attr('opacity', 0.7)
          .attr('fill', 'none')
          .datum(entry)
          .on('click', (_event: Event, d: SpliceEntry) => {
            this.onSpliceClick(d);
          });
      } else {
        // Normal splice link
        const sameSide = Math.abs(a.x - b.x) < 10;
        const path = this.linksGroup
          .append('path')
          .attr('class', 'splice-link')
          .classed('same-side', sameSide)
          .attr('d', pathD)
          .datum(entry);

        // Dim links to collapsed strands
        if (a.hidden || b.hidden) {
          path.attr('opacity', 0.2).attr('stroke-dasharray', '3,3');
        }

        path.on('click', (_event: Event, d: SpliceEntry) => {
          this.onSpliceClick(d);
        });
      }
    }

    // --- Pending add changes ---
    for (const pc of this.state.pendingChanges) {
      if (pc.action !== 'add') continue;

      const a = nodeMap.get(pc.fiberA);
      const b = nodeMap.get(pc.fiberB);
      if (!a || !b) continue;

      const pathD = this.buildLinkPath(a, b);

      this.linksGroup
        .append('path')
        .attr('class', 'splice-link pending-add')
        .attr('d', pathD)
        .attr('stroke', '#28a745')
        .attr('stroke-width', 2)
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

    // Wheel scroll — detect which column half the cursor is in
    this.svg.on('wheel', (event: WheelEvent) => {
      event.preventDefault();
      const mouseX: number = d3.pointer(event, this.svg.node())[0];
      const delta = -event.deltaY;

      if (mouseX < this.containerWidth / 2) {
        const maxL = Math.max(
          0,
          this.state.columnHeight(this.state.leftNodes) + HEADER_HEIGHT - svgHeight,
        );
        this.state.leftOffset = Math.max(-maxL, Math.min(0, this.state.leftOffset + delta));
        this.leftInner.attr('transform', `translate(0,${this.state.leftOffset})`);
      } else {
        const maxR = Math.max(
          0,
          this.state.columnHeight(this.state.rightNodes) + HEADER_HEIGHT - svgHeight,
        );
        this.state.rightOffset = Math.max(-maxR, Math.min(0, this.state.rightOffset + delta));
        this.rightInner.attr('transform', `translate(0,${this.state.rightOffset})`);
      }
      this.renderLinks();
    });
  }
}
