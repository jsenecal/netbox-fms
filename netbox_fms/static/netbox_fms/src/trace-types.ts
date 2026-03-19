/** Configuration injected by Django template via window.TRACE_VIEW_CONFIG. */
export interface TraceConfig {
  pathId: number;
  traceUrl: string;
  detailBaseUrl: string;
  circuitName: string;
  pathPosition: number;
}

/** Port reference in a device hop. */
export interface PortRef {
  id: number;
  name: string;
}

/** Port pair (front_port + rear_port). */
export interface PortPair {
  front_port: PortRef;
  rear_port?: PortRef | null;
}

/** Splice info attached to a closure hop. */
export interface SpliceInfo {
  id: number;
  plan_name: string;
  tray: string | null;
  is_express: boolean;
}

/** A device hop (endpoint or closure). */
export interface DeviceHop {
  type: 'device';
  id: number;
  name: string;
  role: string | null;
  site: string | null;
  url: string;
  ports?: PortPair;
  ingress?: PortPair;
  egress?: PortPair;
  splice?: SpliceInfo;
}

/** A cable hop. */
export interface CableHop {
  type: 'cable';
  id: number;
  label: string;
  fiber_type?: string | null;
  strand_count?: number | null;
  strand_position?: number | null;
  strand_color?: string | null;
  tube_name?: string | null;
  tube_color?: string | null;
  fiber_cable_id?: number | null;
  fiber_cable_url?: string | null;
}

/** Union of all hop types. */
export type Hop = DeviceHop | CableHop;

/** Response from the trace API endpoint. */
export interface TraceResponse {
  circuit_id: number;
  circuit_name: string;
  circuit_url: string;
  path_position: number;
  is_complete: boolean;
  total_calculated_loss_db: string | null;
  total_actual_loss_db: string | null;
  wavelength_nm: number | null;
  hops: Hop[];
}
