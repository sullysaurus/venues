import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Types
export interface Venue {
  venue_id: string;
  slug: string;
  name: string;
  location?: string;
  sections_count: number;
  has_seatmap: boolean;
  has_model: boolean;
  images_count: number;
  event_types_count: number;
  created_at?: string;
}

export interface Section {
  section_id: string;
  tier: string;
  angle: number;
  inner_radius: number;
  rows: number;
  row_depth: number;
  row_rise: number;
  base_height: number;
}

export interface PipelineProgress {
  workflow_id: string;
  stage: string;
  current_step: number;
  total_steps: number;
  message: string;
  seats_generated: number;
  depth_maps_rendered: number;
  images_generated: number;
  actual_cost: number;
  failed_items: string[];
}

export interface SeatImage {
  seat_id: string;
  section: string;
  row: string;
  seat: number;
  tier: string;
  depth_map_url?: string;
  final_image_url?: string;
}

// Event Type Types
export type SurfaceType = 'rink' | 'court' | 'stage' | 'field';
export type ExtractionStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type ExtractionProvider = 'replicate' | 'openai';

export interface SurfaceConfig {
  length: number;
  width: number;
  boards: boolean;
  boards_height: number;
  extra?: Record<string, any>;
}

export interface EventType {
  id: string;
  venue_id: string;
  name: string;
  display_name: string;
  seatmap_url?: string;
  reference_image_url?: string;
  surface_type: SurfaceType;
  surface_config: SurfaceConfig;
  is_default: boolean;
  sections_count: number;
  created_at?: string;
}

export interface ExtractedSection {
  section_id: string;
  tier: string;
  angle: number;
  estimated_rows: number;
  inner_radius: number;
  row_depth: number;
  row_rise: number;
  base_height: number;
  confidence: number;
  position_description?: string;
}

export interface SeatmapExtraction {
  id: string;
  venue_id: string;
  event_type_id?: string;
  seatmap_url: string;
  provider: ExtractionProvider;
  status: ExtractionStatus;
  extracted_sections?: ExtractedSection[];
  confidence_scores?: Record<string, number>;
  error_message?: string;
  created_at?: string;
}

// Venues API
export const venuesApi = {
  list: () => api.get<{ venues: Venue[]; total: number }>('/venues/'),
  get: (id: string) => api.get<Venue>(`/venues/${id}`),
  create: (data: { name: string; location?: string }) => api.post<Venue>('/venues/', data),
  delete: (id: string) => api.delete(`/venues/${id}`),
  getSections: (id: string) => api.get<{ sections: Record<string, Section> }>(`/venues/${id}/sections`),
};

// Pipelines API
export const pipelinesApi = {
  start: (data: {
    venue_id: string;
    sections: Record<string, any>;
    event_type_id?: string;
    prompt?: string;
    model?: string;
    ip_adapter_scale?: number;
    skip_ai_generation?: boolean;
    stop_after_model?: boolean;    // Stop after building 3D model (for preview)
    stop_after_depths?: boolean;   // Stop after rendering depth maps
    surface_type?: 'rink' | 'court' | 'stage' | 'field';
  }) => api.post<{ workflow_id: string }>('/pipelines/', data),

  getProgress: (workflowId: string) =>
    api.get<PipelineProgress>(`/pipelines/${workflowId}`),

  cancel: (workflowId: string) =>
    api.post(`/pipelines/${workflowId}/cancel`),
};

// Images API
export const imagesApi = {
  list: (venueId: string, filters?: { tier?: string; section?: string }) =>
    api.get<{ venue_id: string; images: SeatImage[]; total: number }>(
      `/images/${venueId}`,
      { params: filters }
    ),

  getImageUrl: (venueId: string, seatId: string) =>
    `${API_URL}/images/${venueId}/${seatId}`,
};

// Event Types API
export const eventTypesApi = {
  list: (venueId: string) =>
    api.get<{ event_types: EventType[]; total: number }>(
      `/venues/${venueId}/event-types`
    ),

  get: (venueId: string, eventTypeId: string) =>
    api.get<EventType>(`/venues/${venueId}/event-types/${eventTypeId}`),

  create: (venueId: string, data: {
    name: string;
    display_name: string;
    surface_type?: SurfaceType;
    surface_config?: Partial<SurfaceConfig>;
    is_default?: boolean;
  }) => api.post<EventType>(`/venues/${venueId}/event-types`, data),

  getSections: (venueId: string, eventTypeId: string) =>
    api.get<{ sections: Record<string, Section>; total: number }>(
      `/venues/${venueId}/event-types/${eventTypeId}/sections`
    ),
};

// Seatmaps API
export const seatmapsApi = {
  upload: async (venueId: string, file: File, imageType: 'seatmap' | 'reference' = 'seatmap') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('image_type', imageType);

    return api.post<{ status: string; url: string; image_type: string; venue_id: string }>(
      `/venues/${venueId}/seatmaps/upload`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
  },

  startExtraction: (venueId: string) =>
    api.post<{ extraction_id: string; status: string; message: string }>(
      `/venues/${venueId}/seatmaps/extract`
    ),

  getExtraction: (venueId: string, extractionId: string) =>
    api.get<SeatmapExtraction>(`/venues/${venueId}/seatmaps/extractions/${extractionId}`),

  listExtractions: (venueId: string, eventTypeId?: string) =>
    api.get<{ extractions: SeatmapExtraction[]; total: number }>(
      `/venues/${venueId}/seatmaps/extractions`,
      { params: eventTypeId ? { event_type_id: eventTypeId } : undefined }
    ),

  adjustExtraction: (venueId: string, extractionId: string, sections: Record<string, ExtractedSection>) =>
    api.put<{ status: string; sections_count: number }>(
      `/venues/${venueId}/seatmaps/extractions/${extractionId}/adjust`,
      { sections }
    ),

  finalizeExtraction: (venueId: string, extractionId: string) =>
    api.post<{ status: string; sections_count: number; venue_id: string }>(
      `/venues/${venueId}/seatmaps/extractions/${extractionId}/finalize`
    ),
};
