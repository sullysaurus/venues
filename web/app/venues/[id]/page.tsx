'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  MapPin, Upload, Brain, Eye, Box, Sparkles, Image as ImageIcon,
  ChevronDown, ChevronUp, Check, Loader2, Play, X, ZoomIn, Settings, Tag,
  ChevronRight, AlertCircle
} from 'lucide-react';
import { venuesApi, imagesApi, seatmapsApi, pipelinesApi, PipelineProgress, Section, SeatImage, VenueAssets } from '@/lib/api';
import { CollapsibleSection, SectionStatus } from '@/components/CollapsibleSection';
import SeatmapUploader from '@/components/SeatmapUploader';

// Event type options
const EVENT_TYPES = [
  { value: 'hockey', label: 'Hockey', icon: '🏒' },
  { value: 'basketball', label: 'Basketball', icon: '🏀' },
  { value: 'concert', label: 'Concert', icon: '🎤' },
  { value: 'football', label: 'Football', icon: '🏈' },
];

// AI Models for image generation
const AI_MODELS = [
  { value: 'flux', label: 'Flux Depth Pro', description: 'Best for venues', recommended: true },
  { value: 'flux-schnell', label: 'Flux Schnell', description: 'Fast generation' },
  { value: 'flux-dev', label: 'Flux Dev', description: 'Higher quality, slower' },
];

interface ExtractedSection {
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

function getTierColor(tier: string): string {
  const colors: Record<string, string> = {
    floor: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300',
    lower: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
    mid: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
    upper: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300',
    club: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300',
  };
  return colors[tier.toLowerCase()] || 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300';
}

function getTierBgColor(tier: string): string {
  const colors: Record<string, string> = {
    floor: 'bg-yellow-50 dark:bg-yellow-900/20',
    lower: 'bg-green-50 dark:bg-green-900/20',
    mid: 'bg-blue-50 dark:bg-blue-900/20',
    upper: 'bg-purple-50 dark:bg-purple-900/20',
    club: 'bg-orange-50 dark:bg-orange-900/20',
  };
  return colors[tier.toLowerCase()] || 'bg-gray-50 dark:bg-gray-800';
}

export default function VenueDetailPage() {
  const params = useParams();
  const venueId = params.id as string;
  const queryClient = useQueryClient();

  // ============ STATE ============
  // Upload state
  const [seatmapUrl, setSeatmapUrl] = useState<string | null>(null);
  const [referenceUrl, setReferenceUrl] = useState<string | null>(null);
  const [eventType, setEventType] = useState<string>('hockey');
  const [showSeatmapPreview, setShowSeatmapPreview] = useState(false);

  // Extraction state
  const [extractionId, setExtractionId] = useState<string | null>(null);
  const [showExtractedSections, setShowExtractedSections] = useState(false);

  // Section review state
  const [selectedSections, setSelectedSections] = useState<Set<string>>(new Set());
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const [showConfirmedSections, setShowConfirmedSections] = useState(false);

  // Pipeline state
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [pipelineProgress, setPipelineProgress] = useState<PipelineProgress | null>(null);
  const [activeStep, setActiveStep] = useState<string | null>(null);
  const [existingAssets, setExistingAssets] = useState<VenueAssets | null>(null);

  // Model preview state
  const [modelPreviewUrl, setModelPreviewUrl] = useState<string | null>(null);
  const [showModelPreview, setShowModelPreview] = useState(false);

  // Depth maps state
  const [depthMaps, setDepthMaps] = useState<Array<{id: string; url: string}>>([]);
  const [showDepthMaps, setShowDepthMaps] = useState(false);
  const [sectionsForDepths, setSectionsForDepths] = useState<Set<string>>(new Set());
  const [showSectionSelector, setShowSectionSelector] = useState(false);

  // AI generation state
  const [model, setModel] = useState('flux');
  const [prompt, setPrompt] = useState('A photorealistic view from a stadium seat showing the field/stage, crowd, and venue atmosphere');
  const [useIpAdapter, setUseIpAdapter] = useState(false);
  const [ipAdapterScale, setIpAdapterScale] = useState(0.6);
  const [showAISettings, setShowAISettings] = useState(false);

  // Results state
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  const [expandedImage, setExpandedImage] = useState<string | null>(null);
  const [showGeneratedImages, setShowGeneratedImages] = useState(false);

  // ============ QUERIES ============
  const { data: venue, isLoading: venueLoading } = useQuery({
    queryKey: ['venue', venueId],
    queryFn: () => venuesApi.get(venueId).then((res) => res.data),
  });

  const { data: sectionsData } = useQuery({
    queryKey: ['sections', venueId],
    queryFn: () => venuesApi.getSections(venueId).then((res) => res.data),
  });

  const { data: imagesData } = useQuery({
    queryKey: ['images', venueId],
    queryFn: () => imagesApi.list(venueId).then((res) => res.data),
  });

  const { data: extractionStatus } = useQuery({
    queryKey: ['extraction', extractionId],
    queryFn: () => seatmapsApi.getExtraction(venueId, extractionId!).then((res) => res.data),
    enabled: !!extractionId,
    refetchInterval: (query) => {
      if (!query.state.data) return 2000;
      if (query.state.data.status === 'completed' || query.state.data.status === 'failed') return false;
      return 2000;
    },
  });

  // Derived data
  const sections = sectionsData?.sections || {};
  const images = imagesData?.images || [];
  const sectionsCount = Object.keys(sections).length;
  const imagesCount = images.length;
  const hasSeatmap = venue?.has_seatmap || false;
  const sectionList = Object.values(sections) as Section[];

  // Group sections by tier
  const sectionsByTier = sectionList.reduce((acc, section) => {
    const tier = section.tier || 'lower';
    if (!acc[tier]) acc[tier] = [];
    acc[tier].push(section);
    return acc;
  }, {} as Record<string, Section[]>);

  const tiers = Object.keys(sectionsByTier).sort((a, b) => {
    const order = ['floor', 'lower', 'mid', 'upper', 'club'];
    return order.indexOf(a) - order.indexOf(b);
  });

  // ============ EFFECTS ============
  // Initialize selected sections when sections load
  useEffect(() => {
    if (sectionsCount > 0 && sectionsForDepths.size === 0) {
      setSectionsForDepths(new Set(Object.keys(sections)));
    }
  }, [sectionsCount]);

  // Check for existing assets
  useEffect(() => {
    const checkAssets = async () => {
      try {
        const response = await imagesApi.getAssets(venueId);
        setExistingAssets(response.data);
        if (response.data.has_preview && response.data.preview_url) {
          setModelPreviewUrl(response.data.preview_url);
        }
        if (response.data.has_depth_maps) {
          loadDepthMaps();
        }
      } catch (e) {
        console.error('Failed to check assets:', e);
      }
    };
    checkAssets();
  }, [venueId]);

  // When extraction completes
  useEffect(() => {
    if (extractionStatus?.status === 'completed' && extractionStatus.extracted_sections) {
      const allSectionIds = extractionStatus.extracted_sections.map((s: ExtractedSection) => s.section_id);
      setSelectedSections(new Set(allSectionIds));
      setShowExtractedSections(true);
    }
  }, [extractionStatus?.status]);

  // Poll for pipeline progress
  useEffect(() => {
    if (!workflowId) return;
    const pollProgress = async () => {
      try {
        const response = await pipelinesApi.getProgress(workflowId);
        setPipelineProgress(response.data);
        if (response.data.stage === 'completed') {
          queryClient.invalidateQueries({ queryKey: ['images', venueId] });
          setActiveStep(null);
          // Reload assets
          const assets = await imagesApi.getAssets(venueId);
          setExistingAssets(assets.data);
          if (assets.data.has_preview) {
            setModelPreviewUrl(`/api/images/${venueId}/preview`);
          }
          if (assets.data.has_depth_maps) {
            loadDepthMaps();
          }
        }
      } catch (error) {
        console.error('Failed to get progress:', error);
      }
    };
    pollProgress();
    const interval = setInterval(pollProgress, 2000);
    return () => clearInterval(interval);
  }, [workflowId, venueId, queryClient]);

  // ============ HELPERS ============
  const loadDepthMaps = async () => {
    try {
      const response = await fetch(`/api/images/${venueId}/depth-maps`);
      if (response.ok) {
        const data = await response.json();
        setDepthMaps(data.depth_maps || []);
      }
    } catch (e) {
      console.error('Failed to load depth maps:', e);
    }
  };

  // ============ MUTATIONS ============
  const extractMutation = useMutation({
    mutationFn: () => seatmapsApi.startExtraction(venueId),
    onSuccess: (response) => {
      setExtractionId(response.data.extraction_id);
    },
  });

  const finalizeMutation = useMutation({
    mutationFn: () => seatmapsApi.finalizeExtraction(venueId, extractionId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections', venueId] });
      queryClient.invalidateQueries({ queryKey: ['venue', venueId] });
      setExtractionId(null);
      setShowExtractedSections(false);
    },
  });

  const buildModelMutation = useMutation({
    mutationFn: () => {
      setActiveStep('model');
      return pipelinesApi.start({
        venue_id: venueId,
        sections: sections,
        prompt,
        model: 'flux',
        stop_after_model: true,
        surface_type: 'rink',
      });
    },
    onSuccess: (response) => {
      setWorkflowId(response.data.workflow_id);
    },
    onError: () => setActiveStep(null),
  });

  const renderDepthsMutation = useMutation({
    mutationFn: () => {
      setActiveStep('depths');
      const selectedSectionsData: Record<string, Section> = {};
      sectionsForDepths.forEach((id) => {
        if (sections[id]) selectedSectionsData[id] = sections[id];
      });
      return pipelinesApi.start({
        venue_id: venueId,
        sections: selectedSectionsData,
        prompt,
        model: 'flux',
        stop_after_depths: true,
        skip_model_build: existingAssets?.has_model ?? false,
        surface_type: 'rink',
      });
    },
    onSuccess: (response) => {
      setWorkflowId(response.data.workflow_id);
    },
    onError: () => setActiveStep(null),
  });

  const generateImagesMutation = useMutation({
    mutationFn: () => {
      setActiveStep('images');
      return pipelinesApi.start({
        venue_id: venueId,
        sections: sections,
        prompt,
        model: useIpAdapter ? 'ip_adapter' : model,
        ip_adapter_scale: useIpAdapter ? ipAdapterScale : 0,
        skip_model_build: existingAssets?.has_model ?? false,
        skip_depth_render: existingAssets?.has_depth_maps ?? false,
        surface_type: 'rink',
      });
    },
    onSuccess: (response) => {
      setWorkflowId(response.data.workflow_id);
    },
    onError: () => setActiveStep(null),
  });

  // ============ HANDLERS ============
  const handleSeatmapUpload = (url: string) => {
    setSeatmapUrl(url);
    queryClient.invalidateQueries({ queryKey: ['venue', venueId] });
  };

  const handleToggleSection = (sectionId: string) => {
    const newSelected = new Set(selectedSections);
    if (newSelected.has(sectionId)) newSelected.delete(sectionId);
    else newSelected.add(sectionId);
    setSelectedSections(newSelected);
  };

  const handleToggleSectionForDepths = (sectionId: string) => {
    const newSelected = new Set(sectionsForDepths);
    if (newSelected.has(sectionId)) newSelected.delete(sectionId);
    else newSelected.add(sectionId);
    setSectionsForDepths(newSelected);
  };

  const handleSelectTierForDepths = (tier: string) => {
    const tierSectionIds = sectionsByTier[tier]?.map((s) => s.section_id) || [];
    const allSelected = tierSectionIds.every((id) => sectionsForDepths.has(id));
    const newSelected = new Set(sectionsForDepths);
    if (allSelected) tierSectionIds.forEach((id) => newSelected.delete(id));
    else tierSectionIds.forEach((id) => newSelected.add(id));
    setSectionsForDepths(newSelected);
  };

  // ============ STATUS HELPERS ============
  const isPipelineRunning = workflowId && pipelineProgress && !['completed', 'failed', 'cancelled'].includes(pipelineProgress.stage);
  const hasModel = existingAssets?.has_model || false;
  const hasDepthMaps = (existingAssets?.depth_map_count || 0) > 0;
  const depthMapCount = depthMaps.length || existingAssets?.depth_map_count || 0;

  const getSectionStatus = (step: number): SectionStatus => {
    switch (step) {
      case 1: // Upload
        if (hasSeatmap) return 'completed';
        return 'current';
      case 2: // Extract
        if (sectionsCount > 0) return 'completed';
        if (extractionStatus?.status === 'processing' || extractMutation.isPending) return 'in_progress';
        if (hasSeatmap) return 'current';
        return 'locked';
      case 3: // Review
        if (sectionsCount > 0) return 'completed';
        if (extractionStatus?.status === 'completed') return 'current';
        return 'locked';
      case 4: // Build Model
        if (activeStep === 'model' || (isPipelineRunning && pipelineProgress?.stage === 'building_model')) return 'in_progress';
        if (hasModel) return 'completed';
        if (sectionsCount > 0) return 'current';
        return 'locked';
      case 5: // Render Depths
        if (activeStep === 'depths' || (isPipelineRunning && pipelineProgress?.stage === 'rendering_depths')) return 'in_progress';
        if (hasDepthMaps) return 'completed';
        if (hasModel) return 'current';
        return 'locked';
      case 6: // Generate Images
        if (activeStep === 'images' || (isPipelineRunning && pipelineProgress?.stage === 'generating_images')) return 'in_progress';
        if (imagesCount > 0) return 'completed';
        if (hasDepthMaps) return 'current';
        return 'locked';
      default:
        return 'upcoming';
    }
  };

  // ============ RENDER ============
  if (venueLoading) {
    return <div className="p-6 text-center text-gray-500">Loading venue...</div>;
  }

  if (!venue) {
    return (
      <div className="p-6 text-center text-red-500">
        Venue not found. <Link href="/venues" className="text-blue-600 hover:underline">Back to venues</Link>
      </div>
    );
  }

  const extractedSections = extractionStatus?.extracted_sections as ExtractedSection[] || [];
  const isExtracting = extractMutation.isPending || (extractionId && extractionStatus?.status !== 'completed' && extractionStatus?.status !== 'failed');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <Link href="/venues" className="text-sm text-blue-600 hover:underline flex items-center gap-1">
            &larr; Back to Venues
          </Link>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mt-2">{venue.name}</h1>
          {venue.location && (
            <p className="text-gray-500 flex items-center gap-1 mt-1">
              <MapPin className="w-4 h-4" />
              {venue.location}
            </p>
          )}
        </div>
        <div className="flex gap-4 text-sm">
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{sectionsCount}</div>
            <div className="text-gray-500">Sections</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{imagesCount}</div>
            <div className="text-gray-500">Images</div>
          </div>
        </div>
      </div>

      {/* 6-Step Workflow */}
      <div className="space-y-3">

        {/* ============ STEP 1: UPLOAD SEATMAP ============ */}
        <CollapsibleSection
          title="Upload Seatmap"
          stepNumber={1}
          status={getSectionStatus(1)}
          summary={hasSeatmap ? <span className="text-green-600">Seatmap uploaded</span> : <span className="text-gray-400">Upload a seatmap image</span>}
        >
          <div className="space-y-4">
            {/* Upload Area */}
            <div>
              <p className="text-sm text-gray-500 mb-3">
                Upload a PNG or JPG image of the venue seatmap. The AI will detect all sections automatically.
              </p>
              <SeatmapUploader
                venueId={venueId}
                imageType="seatmap"
                onUploadComplete={handleSeatmapUpload}
                existingUrl={seatmapUrl || undefined}
              />
            </div>

            {/* Event Type Tag */}
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <Tag className="w-4 h-4 text-gray-500" />
                <span className="font-medium text-gray-900 dark:text-white">Event Type</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {EVENT_TYPES.map((type) => (
                  <button
                    key={type.value}
                    onClick={() => setEventType(type.value)}
                    className={`px-3 py-1.5 rounded-lg border-2 flex items-center gap-2 text-sm ${
                      eventType === type.value
                        ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300'
                        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <span>{type.icon}</span>
                    <span>{type.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Collapsible Preview */}
            {hasSeatmap && (
              <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => setShowSeatmapPreview(!showSeatmapPreview)}
                  className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  {showSeatmapPreview ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  Uploaded Seatmap
                </button>
                {showSeatmapPreview && seatmapUrl && (
                  <img src={seatmapUrl} alt="Seatmap" className="mt-3 w-full max-h-64 object-contain rounded-lg border" />
                )}
              </div>
            )}
          </div>
        </CollapsibleSection>

        {/* ============ STEP 2: EXTRACT SECTIONS ============ */}
        <CollapsibleSection
          title="Extract Sections"
          stepNumber={2}
          status={getSectionStatus(2)}
          summary={
            sectionsCount > 0 ? <span className="text-green-600">{sectionsCount} sections found</span> :
            isExtracting ? <span className="text-blue-600">Extracting...</span> :
            <span className="text-gray-400">Run AI extraction</span>
          }
        >
          <div className="space-y-4">
            {isExtracting ? (
              <div className="py-8 text-center">
                <Loader2 className="w-12 h-12 animate-spin mx-auto text-purple-500 mb-3" />
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Analyzing Seatmap</h3>
                <p className="text-gray-500 mt-1">GPT-4 Vision is detecting sections...</p>
                <div className="max-w-xs mx-auto mt-4">
                  <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div className="h-full bg-purple-500 rounded-full animate-pulse" style={{ width: '60%' }} />
                  </div>
                </div>
              </div>
            ) : extractionStatus?.status === 'completed' && extractedSections.length > 0 ? (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-green-600">
                    <Check className="w-5 h-5" />
                    <span className="font-medium">{extractedSections.length} sections detected</span>
                  </div>
                  <button
                    onClick={() => setShowExtractedSections(!showExtractedSections)}
                    className="text-sm text-gray-500 hover:text-gray-700"
                  >
                    {showExtractedSections ? 'Hide' : 'Show'} sections
                  </button>
                </div>
                {showExtractedSections && (
                  <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                    {extractedSections.map((s) => (
                      <div key={s.section_id} className="px-3 py-2 flex items-center justify-between text-sm">
                        <span className="font-medium">Section {s.section_id}</span>
                        <span className={`px-2 py-0.5 text-xs rounded ${getTierColor(s.tier)}`}>{s.tier}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : sectionsCount > 0 ? (
              <div className="flex items-center gap-3 p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
                <Check className="w-6 h-6 text-green-500" />
                <div>
                  <div className="font-medium text-green-800 dark:text-green-200">{sectionsCount} sections confirmed</div>
                  <div className="text-sm text-green-600 dark:text-green-400">Ready for 3D model building</div>
                </div>
                <button onClick={() => extractMutation.mutate()} className="ml-auto text-sm text-green-700 hover:underline">
                  Re-extract
                </button>
              </div>
            ) : (
              <div>
                <p className="text-sm text-gray-500 mb-4">
                  Use GPT-4 Vision to automatically detect all sections from your seatmap.
                </p>
                <button
                  onClick={() => extractMutation.mutate()}
                  disabled={!hasSeatmap || extractMutation.isPending}
                  className="w-full px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 font-medium"
                >
                  Extract All Sections
                </button>
              </div>
            )}
          </div>
        </CollapsibleSection>

        {/* ============ STEP 3: REVIEW & CONFIRM ============ */}
        <CollapsibleSection
          title="Review & Confirm Sections"
          stepNumber={3}
          status={getSectionStatus(3)}
          summary={
            sectionsCount > 0 ? <span className="text-green-600">{sectionsCount} sections confirmed</span> :
            extractionStatus?.status === 'completed' ? <span className="text-blue-600">Review extracted sections</span> :
            <span className="text-gray-400">Waiting for extraction</span>
          }
        >
          {extractionStatus?.status === 'completed' && extractedSections.length > 0 && !sectionsCount ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-500">Select which sections to include in your 3D model.</p>
                <div className="flex gap-2">
                  <button onClick={() => setSelectedSections(new Set(extractedSections.map(s => s.section_id)))} className="text-sm text-blue-600 hover:underline">
                    Select All
                  </button>
                  <button onClick={() => setSelectedSections(new Set())} className="text-sm text-gray-500 hover:underline">
                    Clear
                  </button>
                </div>
              </div>
              <div className="border rounded-lg divide-y max-h-64 overflow-y-auto">
                {extractedSections.map((section) => (
                  <div key={section.section_id} className={`px-3 py-2 flex items-center gap-3 ${selectedSections.has(section.section_id) ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                    <input
                      type="checkbox"
                      checked={selectedSections.has(section.section_id)}
                      onChange={() => handleToggleSection(section.section_id)}
                      className="w-4 h-4"
                    />
                    <div className="flex-1">
                      <span className="font-medium">Section {section.section_id}</span>
                      <span className={`ml-2 px-2 py-0.5 text-xs rounded ${getTierColor(section.tier)}`}>{section.tier}</span>
                    </div>
                    <span className="text-sm text-gray-500">{section.estimated_rows} rows</span>
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between pt-4 border-t">
                <span className="text-sm text-gray-600">{selectedSections.size} sections selected</span>
                <button
                  onClick={() => finalizeMutation.mutate()}
                  disabled={selectedSections.size === 0 || finalizeMutation.isPending}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium"
                >
                  {finalizeMutation.isPending ? 'Saving...' : 'Confirm Sections'}
                </button>
              </div>
            </div>
          ) : sectionsCount > 0 ? (
            <div className="space-y-3">
              <button
                onClick={() => setShowConfirmedSections(!showConfirmedSections)}
                className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                {showConfirmedSections ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                View {sectionsCount} confirmed sections
              </button>
              {showConfirmedSections && (
                <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                  {sectionList.map((section) => (
                    <div key={section.section_id} className="px-3 py-2 flex items-center justify-between text-sm">
                      <span className="font-medium">Section {section.section_id}</span>
                      <span className={`px-2 py-0.5 text-xs rounded ${getTierColor(section.tier)}`}>{section.tier}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-500">Extract sections first to review them.</p>
          )}
        </CollapsibleSection>

        {/* ============ STEP 4: BUILD 3D MODEL ============ */}
        <CollapsibleSection
          title="Build 3D Model"
          stepNumber={4}
          status={getSectionStatus(4)}
          summary={
            hasModel ? <span className="text-green-600">3D model built</span> :
            activeStep === 'model' ? <span className="text-blue-600">Building...</span> :
            <span className="text-gray-400">Build venue geometry</span>
          }
        >
          <div className="space-y-4">
            <p className="text-sm text-gray-500">
              Create a 3D model of the venue using all {sectionsCount} sections. This model is used to render depth maps from each seat position.
            </p>

            {hasModel ? (
              <>
                <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                  <Check className="w-5 h-5 text-green-500" />
                  <span className="text-green-700 dark:text-green-300 font-medium">3D model ready</span>
                  <button
                    onClick={() => buildModelMutation.mutate()}
                    disabled={!!isPipelineRunning}
                    className="ml-auto text-sm text-green-700 hover:underline"
                  >
                    Rebuild
                  </button>
                </div>
                <button
                  onClick={() => setShowModelPreview(!showModelPreview)}
                  className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  {showModelPreview ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  View 3D Model Preview
                </button>
                {showModelPreview && modelPreviewUrl && (
                  <img src={modelPreviewUrl} alt="3D Model" className="w-full max-h-64 object-contain rounded-lg border bg-gray-900" />
                )}
              </>
            ) : activeStep === 'model' || buildModelMutation.isPending ? (
              <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-5 h-5 animate-spin text-purple-500" />
                  <span className="text-purple-700 dark:text-purple-300">Building 3D model...</span>
                </div>
              </div>
            ) : (
              <button
                onClick={() => buildModelMutation.mutate()}
                disabled={sectionsCount === 0 || !!isPipelineRunning}
                className="w-full px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 font-medium flex items-center justify-center gap-2"
              >
                <Box className="w-5 h-5" />
                Build 3D Model
              </button>
            )}
          </div>
        </CollapsibleSection>

        {/* ============ STEP 5: SELECT & RENDER DEPTH MAPS ============ */}
        <CollapsibleSection
          title="Select Sections & Render Depth Maps"
          stepNumber={5}
          status={getSectionStatus(5)}
          summary={
            hasDepthMaps ? <span className="text-green-600">{depthMapCount} depth maps rendered</span> :
            activeStep === 'depths' ? <span className="text-blue-600">Rendering...</span> :
            <span className="text-gray-400">Select sections and render</span>
          }
        >
          <div className="space-y-4">
            <p className="text-sm text-gray-500">
              Select which sections to render depth maps for. Each section generates 3 depth maps (Front, Middle, Back row).
            </p>

            {/* Section Selector */}
            <div>
              <button
                onClick={() => setShowSectionSelector(!showSectionSelector)}
                className="w-full text-left flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  {sectionsForDepths.size === sectionsCount ? 'All sections selected' : `${sectionsForDepths.size} of ${sectionsCount} sections`}
                </span>
                {showSectionSelector ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
              </button>
              {showSectionSelector && (
                <div className="mt-3 p-3 border rounded-lg bg-white dark:bg-gray-900 space-y-3">
                  <div className="flex items-center gap-2">
                    <button onClick={() => setSectionsForDepths(new Set(Object.keys(sections)))} className="px-3 py-1 text-sm bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200">
                      Select All
                    </button>
                    <button onClick={() => setSectionsForDepths(new Set())} className="px-3 py-1 text-sm bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200">
                      Clear
                    </button>
                    <span className="ml-auto text-sm text-gray-500">{sectionsForDepths.size * 3} depth maps</span>
                  </div>
                  <div className="max-h-48 overflow-y-auto space-y-2">
                    {tiers.map((tier) => {
                      const tierSections = sectionsByTier[tier] || [];
                      const tierSelected = tierSections.filter((s) => sectionsForDepths.has(s.section_id)).length;
                      return (
                        <div key={tier} className={`p-2 rounded-lg ${getTierBgColor(tier)}`}>
                          <button onClick={() => handleSelectTierForDepths(tier)} className="flex items-center gap-2 w-full text-left mb-1">
                            <div className={`w-4 h-4 rounded border ${tierSelected === tierSections.length ? 'bg-purple-600 border-purple-600' : 'border-gray-300'} flex items-center justify-center`}>
                              {tierSelected === tierSections.length && <Check className="w-3 h-3 text-white" />}
                            </div>
                            <span className="font-medium capitalize">{tier} Level</span>
                            <span className="text-sm text-gray-500 ml-auto">{tierSelected}/{tierSections.length}</span>
                          </button>
                          <div className="flex flex-wrap gap-1 pl-6">
                            {tierSections.map((section) => (
                              <button
                                key={section.section_id}
                                onClick={() => handleToggleSectionForDepths(section.section_id)}
                                className={`px-2 py-0.5 text-xs rounded-full ${sectionsForDepths.has(section.section_id) ? 'bg-purple-600 text-white' : 'bg-white text-gray-600 border'}`}
                              >
                                {section.section_id}
                              </button>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {hasDepthMaps ? (
              <>
                <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                  <Check className="w-5 h-5 text-green-500" />
                  <span className="text-green-700 dark:text-green-300 font-medium">{depthMapCount} depth maps ready</span>
                  <button onClick={() => renderDepthsMutation.mutate()} disabled={!!isPipelineRunning} className="ml-auto text-sm text-green-700 hover:underline">
                    Re-render
                  </button>
                </div>
                <button onClick={() => setShowDepthMaps(!showDepthMaps)} className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  {showDepthMaps ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  View Depth Maps
                </button>
                {showDepthMaps && (
                  <div className="grid grid-cols-4 gap-2">
                    {depthMaps.slice(0, 8).map((dm) => (
                      <div key={dm.id} className="relative rounded-lg overflow-hidden border cursor-pointer hover:border-purple-400" onClick={() => setExpandedImage(dm.url)}>
                        <img src={dm.url} alt={dm.id} className="w-full h-16 object-cover" />
                        <div className="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-xs p-0.5 truncate">{dm.id}</div>
                      </div>
                    ))}
                    {depthMaps.length > 8 && <div className="flex items-center justify-center text-gray-500 text-sm">+{depthMaps.length - 8} more</div>}
                  </div>
                )}
              </>
            ) : activeStep === 'depths' || renderDepthsMutation.isPending ? (
              <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-5 h-5 animate-spin text-purple-500" />
                  <span className="text-purple-700 dark:text-purple-300">
                    Rendering depth maps... {pipelineProgress?.depth_maps_rendered || 0} / {sectionsForDepths.size * 3}
                  </span>
                </div>
              </div>
            ) : (
              <button
                onClick={() => renderDepthsMutation.mutate()}
                disabled={!hasModel || sectionsForDepths.size === 0 || !!isPipelineRunning}
                className="w-full px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 font-medium flex items-center justify-center gap-2"
              >
                <Eye className="w-5 h-5" />
                Render {sectionsForDepths.size * 3} Depth Maps
              </button>
            )}
          </div>
        </CollapsibleSection>

        {/* ============ STEP 6: GENERATE AI IMAGES ============ */}
        <CollapsibleSection
          title="Generate AI Images"
          stepNumber={6}
          status={getSectionStatus(6)}
          summary={
            imagesCount > 0 ? <span className="text-green-600">{imagesCount} images generated</span> :
            activeStep === 'images' ? <span className="text-blue-600">Generating...</span> :
            <span className="text-gray-400">Configure AI and generate</span>
          }
        >
          <div className="space-y-4">
            <p className="text-sm text-gray-500">
              Configure AI settings and generate photorealistic images from your depth maps.
            </p>

            {/* AI Settings */}
            <button
              onClick={() => setShowAISettings(!showAISettings)}
              className="w-full text-left flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              <span className="font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                <Settings className="w-4 h-4" />
                AI Generation Settings
              </span>
              {showAISettings ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </button>
            {showAISettings && (
              <div className="p-4 border rounded-lg bg-white dark:bg-gray-900 space-y-4">
                {/* Model Selector */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">AI Model</label>
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    disabled={useIpAdapter}
                    className="w-full p-2 border rounded-lg bg-white dark:bg-gray-800 disabled:opacity-50"
                  >
                    {AI_MODELS.map((m) => (
                      <option key={m.value} value={m.value}>{m.label} {m.recommended ? '(Recommended)' : ''}</option>
                    ))}
                  </select>
                </div>

                {/* Prompt */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Scene Prompt</label>
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    rows={3}
                    placeholder="Describe the venue atmosphere..."
                    className="w-full p-3 border rounded-lg bg-white dark:bg-gray-800 resize-none"
                  />
                </div>

                {/* Reference Image Upload */}
                <div className="pt-3 border-t">
                  <div className="flex items-center gap-2 mb-2">
                    <ImageIcon className="w-4 h-4 text-gray-500" />
                    <span className="font-medium text-gray-700 dark:text-gray-300">Reference Image (Optional)</span>
                  </div>
                  <p className="text-sm text-gray-500 mb-3">Upload a reference photo for style transfer using IP-Adapter.</p>
                  <SeatmapUploader
                    venueId={venueId}
                    imageType="reference"
                    onUploadComplete={(url) => {
                      setReferenceUrl(url);
                      setUseIpAdapter(true);
                    }}
                    existingUrl={referenceUrl || undefined}
                  />
                  {referenceUrl && (
                    <div className="mt-3 p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <label className="text-sm font-medium text-purple-700 dark:text-purple-300">Use IP-Adapter</label>
                        <button
                          onClick={() => setUseIpAdapter(!useIpAdapter)}
                          className={`w-12 h-6 rounded-full transition-colors ${useIpAdapter ? 'bg-purple-600' : 'bg-gray-300'}`}
                        >
                          <span className={`block w-4 h-4 rounded-full bg-white transform transition-transform ${useIpAdapter ? 'translate-x-7' : 'translate-x-1'}`} />
                        </button>
                      </div>
                      {useIpAdapter && (
                        <div>
                          <label className="block text-xs text-purple-600 mb-1">Style Strength: {Math.round(ipAdapterScale * 100)}%</label>
                          <input type="range" min="0" max="1" step="0.1" value={ipAdapterScale} onChange={(e) => setIpAdapterScale(parseFloat(e.target.value))} className="w-full" />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Generate Button / Status */}
            {imagesCount > 0 ? (
              <>
                <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                  <Check className="w-5 h-5 text-green-500" />
                  <span className="text-green-700 dark:text-green-300 font-medium">{imagesCount} images generated</span>
                  <button onClick={() => generateImagesMutation.mutate()} disabled={!!isPipelineRunning} className="ml-auto text-sm text-green-700 hover:underline">
                    Regenerate
                  </button>
                </div>

                {/* Collapsible Results Preview */}
                <button
                  onClick={() => setShowGeneratedImages(!showGeneratedImages)}
                  className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  {showGeneratedImages ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  View Generated Images ({imagesCount})
                </button>

                {showGeneratedImages && (
                  <div className="pt-3 border-t">
                    {/* Tier Filter */}
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="font-medium text-gray-900 dark:text-white">Generated Views</h4>
                      <div className="flex gap-1">
                        <button onClick={() => setSelectedTier(null)} className={`px-2 py-1 text-xs rounded-full ${selectedTier === null ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-600'}`}>
                          All
                        </button>
                        {[...new Set(images.map((img: SeatImage) => img.tier))].sort().map((tier: string) => (
                          <button key={tier} onClick={() => setSelectedTier(tier)} className={`px-2 py-1 text-xs rounded-full capitalize ${selectedTier === tier ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-600'}`}>
                            {tier}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Image Grid */}
                    <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                      {images.filter((img: SeatImage) => !selectedTier || img.tier === selectedTier).map((image: SeatImage) => {
                        const imageUrl = image.final_image_url || imagesApi.getImageUrl(venueId, image.seat_id);
                        return (
                          <div key={image.seat_id} className="group relative rounded-lg overflow-hidden cursor-pointer border border-gray-200 dark:border-gray-700" onClick={() => setExpandedImage(imageUrl)}>
                            <img src={imageUrl} alt={`${image.section} ${image.row}`} className="w-full h-24 object-cover group-hover:scale-105 transition-transform" />
                            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                              <ZoomIn className="absolute top-2 right-2 w-4 h-4 text-white/80" />
                            </div>
                            <div className="absolute bottom-0 left-0 right-0 p-1 bg-black/50 text-white text-xs">{image.section} · {image.row}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            ) : activeStep === 'images' || generateImagesMutation.isPending ? (
              <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-5 h-5 animate-spin text-purple-500" />
                  <span className="text-purple-700 dark:text-purple-300">
                    Generating images... {pipelineProgress?.images_generated || 0} / {depthMapCount}
                  </span>
                </div>
              </div>
            ) : (
              <button
                onClick={() => generateImagesMutation.mutate()}
                disabled={!hasDepthMaps || !!isPipelineRunning}
                className="w-full px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 font-medium flex items-center justify-center gap-2"
              >
                <Sparkles className="w-5 h-5" />
                Generate {depthMapCount} AI Images
              </button>
            )}
          </div>
        </CollapsibleSection>
      </div>

      {/* Image Lightbox */}
      {expandedImage && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={() => setExpandedImage(null)}>
          <button className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20" onClick={() => setExpandedImage(null)}>
            <X className="w-6 h-6 text-white" />
          </button>
          <img src={expandedImage} alt="Expanded view" className="max-w-full max-h-full rounded-lg" onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}
