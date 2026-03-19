declare const d3: any;
declare const htmx: any;

import type { TraceConfig, TraceResponse, Hop, DeviceHop, CableHop } from './trace-types';

// Layout constants
const NODE_WIDTH = 220;
const NODE_HEIGHT = 56;
const NODE_RX = 8;
const EDGE_HEIGHT = 80;
const TOP_PAD = 30;

const EXPANDED_ENDPOINT_HEIGHT = 100;
const EXPANDED_CLOSURE_HEIGHT = 160;
const EXPANDED_CABLE_HEIGHT = 120;

/** Internal layout entry for each hop. */
interface LayoutEntry {
  hop: Hop;
  x: number;
  y: number;
  width: number;
  height: number;
  expanded: boolean;
}

/** Theme colors for dark/light mode. */
interface ThemeColors {
  deviceFill: string;
  closureFill: string;
  cableLine: string;
  text: string;
  selectedStroke: string;
  background: string;
  subtitleText: string;
  badgeFill: string;
  badgeText: string;
  incompleteDash: string;
}

function getThemeColors(isDark: boolean): ThemeColors {
  if (isDark) {
    return {
      deviceFill: '#1a2d3d',
      closureFill: '#1a3a2a',
      cableLine: '#4a6a7a',
      text: '#e0e0e0',
      selectedStroke: '#4dc9f6',
      background: '#0d1117',
      subtitleText: '#8b949e',
      badgeFill: '#21262d',
      badgeText: '#c9d1d9',
      incompleteDash: '#f85149',
    };
  }
  return {
    deviceFill: '#e3f2fd',
    closureFill: '#e8f5e9',
    cableLine: '#adb5bd',
    text: '#212529',
    selectedStroke: '#0d6efd',
    background: '#f8f9fa',
    subtitleText: '#6c757d',
    badgeFill: '#f0f0f0',
    badgeText: '#495057',
    incompleteDash: '#dc3545',
  };
}

function isDeviceHop(hop: Hop): hop is DeviceHop {
  return hop.type === 'device';
}

function isCableHop(hop: Hop): hop is CableHop {
  return hop.type === 'cable';
}

function isClosure(hop: DeviceHop): boolean {
  return !!(hop.ingress || hop.egress);
}

/**
 * D3-based SVG renderer for the fiber circuit path trace visualization.
 *
 * Renders a vertical top-to-bottom node chain showing device endpoints,
 * closures, and cable edges. Supports overview and zoomed-in (expanded) states.
 */
export class TraceRenderer {
  private container: HTMLElement;
  private data: TraceResponse;
  private config: TraceConfig;
  private svg: any;
  private mainGroup: any;
  private layout: LayoutEntry[];
  private selectedIndex: number | null;

  constructor(container: HTMLElement, data: TraceResponse, config: TraceConfig) {
    this.container = container;
    this.data = data;
    this.config = config;
    this.layout = [];
    this.selectedIndex = null;

    this.setupEventListeners();
  }

  /** Initial render: compute layout and draw the SVG. */
  render(): void {
    this.computeLayout();
    this.drawSvg();
  }

  // -------------------------------------------------------------------
  // Event listeners
  // -------------------------------------------------------------------

  private setupEventListeners(): void {
    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Escape' && this.selectedIndex !== null) {
        this.deselect();
      }
    });

    document.addEventListener('trace:deselect', () => {
      if (this.selectedIndex !== null) {
        this.deselect();
      }
    });
  }

  // -------------------------------------------------------------------
  // Layout computation
  // -------------------------------------------------------------------

  private computeLayout(): void {
    const containerWidth = this.container.clientWidth || 600;
    const centerX = containerWidth / 2;

    this.layout = [];
    let y = TOP_PAD;

    for (let i = 0; i < this.data.hops.length; i++) {
      const hop = this.data.hops[i];
      const expanded = this.selectedIndex === i;
      let height: number;

      if (expanded) {
        if (isDeviceHop(hop)) {
          height = isClosure(hop) ? EXPANDED_CLOSURE_HEIGHT : EXPANDED_ENDPOINT_HEIGHT;
        } else {
          height = EXPANDED_CABLE_HEIGHT;
        }
      } else {
        height = isDeviceHop(hop) ? NODE_HEIGHT : EDGE_HEIGHT;
      }

      this.layout.push({
        hop,
        x: centerX - NODE_WIDTH / 2,
        y,
        width: NODE_WIDTH,
        height,
        expanded,
      });

      y += height;

      // Add spacing between elements
      if (isDeviceHop(hop)) {
        // No extra gap after devices — cable edge connects directly
      } else {
        // Small gap after cable edges before next device
      }
    }
  }

  // -------------------------------------------------------------------
  // SVG drawing
  // -------------------------------------------------------------------

  private drawSvg(): void {
    // Clear existing SVG
    const existing = this.container.querySelector('svg.trace-svg');
    if (existing) {
      existing.remove();
    }

    const isDark = document.body.getAttribute('data-bs-theme') === 'dark';
    const colors = getThemeColors(isDark);
    const containerWidth = this.container.clientWidth || 600;

    // Calculate total SVG height
    const lastEntry = this.layout[this.layout.length - 1];
    const totalHeight = lastEntry ? lastEntry.y + lastEntry.height + TOP_PAD : 200;

    // Incomplete path indicator height
    const extraHeight = this.data.is_complete ? 0 : 60;

    this.svg = d3
      .select(this.container)
      .append('svg')
      .attr('class', 'trace-svg')
      .attr('width', containerWidth)
      .attr('height', totalHeight + extraHeight)
      .style('cursor', 'default');

    this.mainGroup = this.svg.append('g');

    // Background click to deselect
    this.svg.on('click', () => {
      if (this.selectedIndex !== null) {
        this.deselect();
      }
    });

    // Draw all entries
    for (let i = 0; i < this.layout.length; i++) {
      const entry = this.layout[i];

      if (isDeviceHop(entry.hop)) {
        this.drawDeviceNode(entry, i, isDark, colors);
      } else if (isCableHop(entry.hop)) {
        this.drawCableEdge(entry, i, isDark, colors);
      }
    }

    // Draw incomplete indicator at bottom
    if (!this.data.is_complete && lastEntry) {
      this.drawIncompleteIndicator(lastEntry, colors);
    }
  }

  // -------------------------------------------------------------------
  // Device node drawing
  // -------------------------------------------------------------------

  private drawDeviceNode(
    entry: LayoutEntry,
    index: number,
    isDark: boolean,
    colors: ThemeColors,
  ): void {
    const hop = entry.hop as DeviceHop;
    const isSelected = this.selectedIndex === index;
    const dimmed = this.selectedIndex !== null && !isSelected;
    const closure = isClosure(hop);

    const g = this.mainGroup.append('g')
      .attr('class', 'trace-device-node')
      .attr('transform', `translate(${entry.x}, ${entry.y})`)
      .style('cursor', 'pointer')
      .style('opacity', dimmed ? 0.5 : 1);

    // Click handler
    g.on('click', (event: Event) => {
      event.stopPropagation();
      this.selectNode(index);
    });

    // Selection glow
    if (isSelected) {
      g.append('rect')
        .attr('x', -4)
        .attr('y', -4)
        .attr('width', entry.width + 8)
        .attr('height', entry.height + 8)
        .attr('rx', NODE_RX + 2)
        .attr('fill', 'none')
        .attr('stroke', colors.selectedStroke)
        .attr('stroke-width', 2)
        .attr('stroke-opacity', 0.5);
    }

    // Node rectangle
    const fill = closure ? colors.closureFill : colors.deviceFill;
    const strokeColor = isSelected ? colors.selectedStroke : (isDark ? '#2d4a5a' : '#b0bec5');
    g.append('rect')
      .attr('x', 0)
      .attr('y', 0)
      .attr('width', entry.width)
      .attr('height', entry.height)
      .attr('rx', NODE_RX)
      .attr('fill', fill)
      .attr('stroke', strokeColor)
      .attr('stroke-width', isSelected ? 2 : 1);

    // Hover effect
    g.on('mouseover', function () {
      d3.select(this).select('rect').attr('stroke-width', isSelected ? 2.5 : 2);
    });
    g.on('mouseout', function () {
      d3.select(this).select('rect').attr('stroke-width', isSelected ? 2 : 1);
    });

    // Device name (bold)
    g.append('text')
      .attr('x', entry.width / 2)
      .attr('y', 22)
      .attr('text-anchor', 'middle')
      .attr('fill', colors.text)
      .attr('font-size', '13px')
      .attr('font-weight', '600')
      .text(hop.name);

    // Role + site subtitle
    const subtitleParts: string[] = [];
    if (hop.role) subtitleParts.push(hop.role);
    if (hop.site) subtitleParts.push(hop.site);
    if (subtitleParts.length > 0) {
      g.append('text')
        .attr('x', entry.width / 2)
        .attr('y', 38)
        .attr('text-anchor', 'middle')
        .attr('fill', colors.subtitleText)
        .attr('font-size', '10px')
        .text(subtitleParts.join(' \u2022 '));
    }

    // Closure indicator
    if (closure) {
      g.append('text')
        .attr('x', entry.width / 2)
        .attr('y', 50)
        .attr('text-anchor', 'middle')
        .attr('fill', colors.subtitleText)
        .attr('font-size', '9px')
        .attr('font-style', 'italic')
        .text('closure');
    }

    // Expanded details
    if (entry.expanded) {
      this.drawExpandedDevice(g, entry, hop, colors);
    }
  }

  private drawExpandedDevice(
    g: any,
    entry: LayoutEntry,
    hop: DeviceHop,
    colors: ThemeColors,
  ): void {
    let detailY = 62;

    // Separator line
    g.append('line')
      .attr('x1', 10)
      .attr('y1', detailY - 6)
      .attr('x2', entry.width - 10)
      .attr('y2', detailY - 6)
      .attr('stroke', colors.subtitleText)
      .attr('stroke-opacity', 0.3);

    // Port information
    if (hop.ports) {
      g.append('text')
        .attr('x', 14)
        .attr('y', detailY + 6)
        .attr('fill', colors.subtitleText)
        .attr('font-size', '10px')
        .text('FP: ' + hop.ports.front_port.name);
      if (hop.ports.rear_port) {
        g.append('text')
          .attr('x', 14)
          .attr('y', detailY + 20)
          .attr('fill', colors.subtitleText)
          .attr('font-size', '10px')
          .text('RP: ' + hop.ports.rear_port.name);
      }
      detailY += 30;
    }

    // Ingress/egress for closures
    if (hop.ingress) {
      g.append('text')
        .attr('x', 14)
        .attr('y', detailY + 6)
        .attr('fill', colors.subtitleText)
        .attr('font-size', '10px')
        .text('In: ' + hop.ingress.front_port.name);
      detailY += 14;
    }
    if (hop.egress) {
      g.append('text')
        .attr('x', 14)
        .attr('y', detailY + 6)
        .attr('fill', colors.subtitleText)
        .attr('font-size', '10px')
        .text('Out: ' + hop.egress.front_port.name);
      detailY += 14;
    }

    // Splice info
    if (hop.splice) {
      const spliceText = hop.splice.is_express ? 'Express splice' : 'Splice: ' + hop.splice.plan_name;
      g.append('text')
        .attr('x', 14)
        .attr('y', detailY + 6)
        .attr('fill', colors.subtitleText)
        .attr('font-size', '10px')
        .attr('font-style', 'italic')
        .text(spliceText);
      if (hop.splice.tray) {
        g.append('text')
          .attr('x', 14)
          .attr('y', detailY + 20)
          .attr('fill', colors.subtitleText)
          .attr('font-size', '10px')
          .text('Tray: ' + hop.splice.tray);
      }
    }
  }

  // -------------------------------------------------------------------
  // Cable edge drawing
  // -------------------------------------------------------------------

  private drawCableEdge(
    entry: LayoutEntry,
    index: number,
    isDark: boolean,
    colors: ThemeColors,
  ): void {
    const hop = entry.hop as CableHop;
    const isSelected = this.selectedIndex === index;
    const dimmed = this.selectedIndex !== null && !isSelected;

    const centerX = entry.x + entry.width / 2;
    const g = this.mainGroup.append('g')
      .attr('class', 'trace-cable-edge')
      .style('cursor', 'pointer')
      .style('opacity', dimmed ? 0.5 : 1);

    // Click handler
    g.on('click', (event: Event) => {
      event.stopPropagation();
      this.selectNode(index);
    });

    // Vertical connection line
    const lineStroke = isSelected ? colors.selectedStroke : colors.cableLine;
    const lineWidth = isSelected ? 3 : 2;
    g.append('line')
      .attr('x1', centerX)
      .attr('y1', entry.y)
      .attr('x2', centerX)
      .attr('y2', entry.y + entry.height)
      .attr('stroke', lineStroke)
      .attr('stroke-width', lineWidth);

    // Hover effect on line
    g.on('mouseover', function () {
      d3.select(this).select('line').attr('stroke-width', lineWidth + 1);
    });
    g.on('mouseout', function () {
      d3.select(this).select('line').attr('stroke-width', lineWidth);
    });

    // Label badge
    const badgeY = entry.y + entry.height / 2;
    const labelText = hop.label || 'Cable';

    // Badge background
    const badgeWidth = Math.max(80, labelText.length * 7 + 20);
    g.append('rect')
      .attr('x', centerX - badgeWidth / 2)
      .attr('y', badgeY - 12)
      .attr('width', badgeWidth)
      .attr('height', 24)
      .attr('rx', 4)
      .attr('fill', colors.badgeFill)
      .attr('stroke', isSelected ? colors.selectedStroke : colors.cableLine)
      .attr('stroke-width', isSelected ? 1.5 : 0.5);

    // Label text
    g.append('text')
      .attr('x', centerX)
      .attr('y', badgeY + 4)
      .attr('text-anchor', 'middle')
      .attr('fill', colors.text)
      .attr('font-size', '11px')
      .attr('font-weight', '500')
      .text(labelText);

    // Strand count + fiber type badge below label
    const infoParts: string[] = [];
    if (hop.strand_count) infoParts.push(hop.strand_count + 'F');
    if (hop.fiber_type) infoParts.push(hop.fiber_type);
    if (infoParts.length > 0) {
      g.append('text')
        .attr('x', centerX)
        .attr('y', badgeY + 20)
        .attr('text-anchor', 'middle')
        .attr('fill', colors.subtitleText)
        .attr('font-size', '9px')
        .text(infoParts.join(' \u2022 '));
    }

    // Expanded details
    if (entry.expanded) {
      this.drawExpandedCable(g, entry, hop, centerX, badgeY, colors);
    }
  }

  private drawExpandedCable(
    g: any,
    entry: LayoutEntry,
    hop: CableHop,
    centerX: number,
    badgeY: number,
    colors: ThemeColors,
  ): void {
    let detailY = badgeY + 36;

    // Strand position
    if (hop.strand_position != null) {
      g.append('text')
        .attr('x', centerX)
        .attr('y', detailY)
        .attr('text-anchor', 'middle')
        .attr('fill', colors.subtitleText)
        .attr('font-size', '10px')
        .text('Strand #' + hop.strand_position);
      detailY += 14;
    }

    // Strand color dot
    if (hop.strand_color) {
      g.append('circle')
        .attr('cx', centerX - 20)
        .attr('cy', detailY - 4)
        .attr('r', 5)
        .attr('fill', '#' + hop.strand_color)
        .attr('stroke', colors.cableLine)
        .attr('stroke-width', 1);
      g.append('text')
        .attr('x', centerX - 10)
        .attr('y', detailY)
        .attr('fill', colors.subtitleText)
        .attr('font-size', '10px')
        .text('strand color');
      detailY += 14;
    }

    // Tube info
    if (hop.tube_name) {
      if (hop.tube_color) {
        g.append('circle')
          .attr('cx', centerX - 20)
          .attr('cy', detailY - 4)
          .attr('r', 5)
          .attr('fill', '#' + hop.tube_color)
          .attr('stroke', colors.cableLine)
          .attr('stroke-width', 1);
      }
      g.append('text')
        .attr('x', centerX - 10)
        .attr('y', detailY)
        .attr('fill', colors.subtitleText)
        .attr('font-size', '10px')
        .text('Tube: ' + hop.tube_name);
    }
  }

  // -------------------------------------------------------------------
  // Incomplete path indicator
  // -------------------------------------------------------------------

  private drawIncompleteIndicator(lastEntry: LayoutEntry, colors: ThemeColors): void {
    const centerX = lastEntry.x + lastEntry.width / 2;
    const y = lastEntry.y + lastEntry.height;

    // Dashed line
    this.mainGroup.append('line')
      .attr('x1', centerX)
      .attr('y1', y)
      .attr('x2', centerX)
      .attr('y2', y + 30)
      .attr('stroke', colors.incompleteDash)
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '6,4');

    // Label
    this.mainGroup.append('text')
      .attr('x', centerX)
      .attr('y', y + 48)
      .attr('text-anchor', 'middle')
      .attr('fill', colors.incompleteDash)
      .attr('font-size', '11px')
      .attr('font-style', 'italic')
      .text('Incomplete path');
  }

  // -------------------------------------------------------------------
  // Selection
  // -------------------------------------------------------------------

  private selectNode(index: number): void {
    if (this.selectedIndex === index) {
      this.deselect();
      return;
    }

    this.selectedIndex = index;
    this.computeLayout();
    this.drawSvg();
    this.updateBreadcrumb();

    // Load sidebar detail via HTMX
    const entry = this.layout[index];
    if (entry) {
      const hop = entry.hop;
      const nodeType = isDeviceHop(hop) ? 'device' : 'cable';
      const detailUrl = this.config.detailBaseUrl + nodeType + '/' + hop.id + '/';

      if (typeof htmx !== 'undefined') {
        htmx.ajax('GET', detailUrl, { target: '#trace-detail-panel' });
      }
    }
  }

  private deselect(): void {
    this.selectedIndex = null;
    this.computeLayout();
    this.drawSvg();
    this.updateBreadcrumb();
  }

  // -------------------------------------------------------------------
  // Breadcrumb
  // -------------------------------------------------------------------

  private updateBreadcrumb(): void {
    const el = document.getElementById('trace-breadcrumb');
    if (!el) return;

    // Clear existing content
    while (el.firstChild) {
      el.removeChild(el.firstChild);
    }

    // Circuit name segment
    const circuitSpan = document.createElement('span');
    circuitSpan.textContent = this.data.circuit_name || 'Circuit';
    el.appendChild(circuitSpan);

    // Path segment
    const sep1 = document.createElement('span');
    sep1.textContent = ' > ';
    el.appendChild(sep1);

    const pathSpan = document.createElement('span');
    pathSpan.textContent = 'Path #' + this.data.path_position;
    el.appendChild(pathSpan);

    // Node name segment (if selected)
    if (this.selectedIndex !== null) {
      const entry = this.layout[this.selectedIndex];
      if (entry) {
        const sep2 = document.createElement('span');
        sep2.textContent = ' > ';
        el.appendChild(sep2);

        const nodeSpan = document.createElement('span');
        const hop = entry.hop;
        if (isDeviceHop(hop)) {
          nodeSpan.textContent = hop.name;
        } else if (isCableHop(hop)) {
          nodeSpan.textContent = hop.label || 'Cable';
        }
        el.appendChild(nodeSpan);
      }
    }
  }
}
