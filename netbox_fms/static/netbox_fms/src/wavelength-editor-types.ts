export interface ChannelData {
  id: number;
  grid_position: number;
  wavelength_nm: number;
  label: string;
  front_port_id: number | null;
  front_port_name: string | null;
  status: 'available' | 'reserved' | 'lit';
  service_name: string | null;
}

export interface PortData {
  id: number;
  name: string;
}

export interface EditorConfig {
  nodeId: number;
  nodeType: string;
  lastUpdated: string;
  applyUrl: string;
  channels: ChannelData[];
  availablePorts: PortData[];
}
