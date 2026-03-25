/** Context mode determines save behavior and UI chrome. */
export type ContextMode = 'view' | 'edit' | 'plan-edit';

/** Splice action mode from toolbar buttons. */
export type ActionMode = 'single' | 'sequential';

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
  debug?: boolean;
  readOnly: boolean;
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
  front_port_a_id: number | null;
  live_spliced_to: number | null;
  plan_entry_id: number | null;
  plan_spliced_to: number | null;
  protected: boolean;
  circuit_name: string | null;
  circuit_url: string | null;
}

/** Tray info from the API. */
export interface TrayData {
  id: number;
  name: string;
  role: 'splice_tray' | 'express_basket';
  capacity: number;
}

/** Tray assignment on a tube. */
export interface TrayAssignment {
  tray_id: number;
  tray_name: string;
  tray_url: string;
}

/** A tube group as returned by the API. */
export interface TubeData {
  id: number;
  name: string;
  color: string;
  marker_count: number;
  marker_color: string | null;
  marker_type: string;
  strand_count: number;
  strands: StrandData[];
  tray_assignment: TrayAssignment | null;
}

/** A cable group as returned by the API. */
export interface CableGroupData {
  fiber_cable_id: number;
  cable_label: string;
  cable_url: string;
  fiber_type: string;
  strand_count: number;
  far_device_name: string | null;
  far_device_url: string | null;
  tubes: TubeData[];
  loose_strands: StrandData[];
}

/** Full API response from ClosureStrandsAPIView. */
export interface StrandsApiResponse {
  cables: CableGroupData[];
  trays: TrayData[];
  plan_version: string | null;
}

/** Bulk update response. */
export interface BulkUpdateResponse {
  entries: Array<{ id: number; fiber_a: number; fiber_b: number; tray: number }>;
  plan_version: string | null;
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
  farDeviceName?: string | null;
  farDeviceUrl?: string | null;

  // Tube fields
  tubeId?: number;
  color?: string;
  markerCount?: number;
  markerColor?: string | null;
  markerType?: string;
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
  isProtected?: boolean;
  circuitName?: string | null;
  circuitUrl?: string | null;
  parentTubeNode?: LayoutNode;
}

/** A pending splice change (add or remove). */
export interface PendingChange {
  action: 'add' | 'remove';
  fiberA: number;    // strand ID (not front_port_a_id)
  fiberB: number;    // strand ID
  portA: number;     // front_port_a_id
  portB: number;     // front_port_a_id
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
  plan_version?: string | null;
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

/** A fiber claim from another plan on the same closure. */
export interface FiberClaim {
  fiber_a: number;
  fiber_b: number;
  plan_id: number;
  plan_name: string;
  project_name: string | null;
  status: string;
}

/* -------------------------------------------------------------------------
   Visual Component Types
   ------------------------------------------------------------------------- */

/** A single item in a legend section. */
export interface LegendItem {
  type: 'dot' | 'line' | 'icon';
  color?: string;
  dashed?: boolean;
  dashColor?: string;
  icon?: string;
  label: string;
}

/** A section in the legend. */
export interface LegendSection {
  title: string;
  items: LegendItem[];
}

/** A row in a detail card. */
export interface DetailRow {
  label: string;
  value: string;
  link?: string;
  badge?: string;
  color?: string;
}

/** A card in the detail panel. */
export interface DetailCard {
  heading: string;
  rows: DetailRow[];
  /** If true, render a horizontal separator before this card (for grouping). */
  separator?: boolean;
}

/** Stats for the stats bar. */
export interface StatsData {
  cableCount: number;
  strandCount: number;
  liveSpliceCount: number;
  plannedSpliceCount: number;
  pendingCount: number;
  planName: string | null;
  planStatus: string | null;
}
