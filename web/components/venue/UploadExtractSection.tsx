'use client';

import { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { seatmapsApi } from '@/lib/api';
import { Loader2, Upload, Image as ImageIcon, ChevronDown, ChevronRight, Brain, Sparkles, Tag } from 'lucide-react';
import SeatmapUploader from '@/components/SeatmapUploader';

// Event type options (just tags for now)
const EVENT_TYPES = [
  { value: 'hockey', label: 'Hockey', icon: '🏒' },
  { value: 'basketball', label: 'Basketball', icon: '🏀' },
  { value: 'concert', label: 'Concert', icon: '🎤' },
  { value: 'football', label: 'Football', icon: '🏈' },
];

// Extraction model options
const EXTRACTION_MODELS = [
  {
    value: 'openai',
    label: 'GPT-4 Vision',
    description: 'OpenAI GPT-4 Turbo with vision',
    icon: '🧠',
    recommended: true,
  },
  {
    value: 'replicate',
    label: 'LLaVA 34B',
    description: 'Meta LLaVA v1.6 on Replicate',
    icon: '🦙',
    disabled: true,  // Not currently implemented
  },
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

interface UploadExtractSectionProps {
  venueId: string;
  hasSeatmap: boolean;
  seatmapUrl: string | null;
  referenceUrl: string | null;
  sectionsCount: number;
  eventType: string;
  onSeatmapUpload: (url: string) => void;
  onReferenceUpload: (url: string) => void;
  onExtractionComplete: () => void;
  onEventTypeChange: (eventType: string) => void;
}

export function UploadExtractSection({
  venueId,
  hasSeatmap,
  seatmapUrl,
  referenceUrl,
  sectionsCount,
  eventType,
  onSeatmapUpload,
  onReferenceUpload,
  onExtractionComplete,
  onEventTypeChange,
}: UploadExtractSectionProps) {
  const [extractionId, setExtractionId] = useState<string | null>(null);
  const [showReview, setShowReview] = useState(false);
  const [selectedSections, setSelectedSections] = useState<Set<string>>(new Set());
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const [showReferenceUpload, setShowReferenceUpload] = useState(false);
  const [extractionModel, setExtractionModel] = useState('openai');
  const queryClient = useQueryClient();

  // Start extraction mutation
  const extractMutation = useMutation({
    mutationFn: () => seatmapsApi.startExtraction(venueId),
    onSuccess: (response) => {
      setExtractionId(response.data.extraction_id);
    },
  });

  // Poll extraction status
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

  // When extraction completes, show review
  useEffect(() => {
    if (extractionStatus?.status === 'completed' && extractionStatus.extracted_sections) {
      setShowReview(true);
      const allSectionIds = extractionStatus.extracted_sections.map((s: ExtractedSection) => s.section_id);
      setSelectedSections(new Set(allSectionIds));
    }
  }, [extractionStatus?.status, extractionStatus?.extracted_sections]);

  // Finalize mutation
  const finalizeMutation = useMutation({
    mutationFn: () => seatmapsApi.finalizeExtraction(venueId, extractionId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections', venueId] });
      queryClient.invalidateQueries({ queryKey: ['venue', venueId] });
      setShowReview(false);
      setExtractionId(null);
      onExtractionComplete();
    },
  });

  const handleToggleSection = (sectionId: string) => {
    const newSelected = new Set(selectedSections);
    if (newSelected.has(sectionId)) {
      newSelected.delete(sectionId);
    } else {
      newSelected.add(sectionId);
    }
    setSelectedSections(newSelected);
  };

  const handleToggleExpand = (sectionId: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(sectionId)) {
      newExpanded.delete(sectionId);
    } else {
      newExpanded.add(sectionId);
    }
    setExpandedSections(newExpanded);
  };

  const isExtracting = extractMutation.isPending || (extractionId && extractionStatus?.status !== 'completed' && extractionStatus?.status !== 'failed');

  // If we already have sections and not in review mode, show success state
  if (sectionsCount > 0 && !showReview) {
    const currentEventType = EVENT_TYPES.find(t => t.value === eventType);
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3 p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
          <div className="w-10 h-10 rounded-full bg-green-500 flex items-center justify-center">
            <span className="text-white text-lg">✓</span>
          </div>
          <div className="flex-1">
            <div className="font-medium text-green-800 dark:text-green-200">
              {sectionsCount} sections extracted
            </div>
            <div className="text-sm text-green-600 dark:text-green-400">
              Ready to build 3D model and generate views
            </div>
          </div>
          <button
            onClick={() => extractMutation.mutate()}
            className="px-3 py-1 text-sm border border-green-300 dark:border-green-700 rounded
                     text-green-700 dark:text-green-300 hover:bg-green-100 dark:hover:bg-green-800"
          >
            Re-extract
          </button>
        </div>

        {/* Event Type Tag and Images */}
        <div className="flex items-center gap-4">
          {/* Event Type */}
          <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-100 dark:bg-purple-900/30 rounded-full">
            <span>{currentEventType?.icon || '🏟️'}</span>
            <span className="text-sm font-medium text-purple-700 dark:text-purple-300">
              {currentEventType?.label || 'Venue'}
            </span>
          </div>

          {/* Change Event Type */}
          <div className="flex gap-1">
            {EVENT_TYPES.filter(t => t.value !== eventType).map((type) => (
              <button
                key={type.value}
                onClick={() => onEventTypeChange(type.value)}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
                title={`Change to ${type.label}`}
              >
                <span className="text-sm">{type.icon}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Show uploaded images */}
        <div className="flex gap-4">
          {seatmapUrl && (
            <div className="flex-1">
              <div className="text-xs text-gray-500 mb-1">Seatmap</div>
              <img src={seatmapUrl} alt="Seatmap" className="w-full h-32 object-cover rounded-lg border" />
            </div>
          )}
        </div>
      </div>
    );
  }

  // Show extraction in progress
  if (isExtracting) {
    const status = extractionStatus?.status || 'pending';
    const selectedModel = EXTRACTION_MODELS.find(m => m.value === extractionModel) || EXTRACTION_MODELS[0];

    // Progress stages
    const stages = [
      { key: 'pending', label: 'Starting', description: 'Preparing extraction...' },
      { key: 'processing', label: 'Analyzing', description: `${selectedModel.label} is detecting sections...` },
    ];

    const currentStageIndex = stages.findIndex(s => s.key === status);
    const progressPercent = status === 'pending' ? 15 : status === 'processing' ? 60 : 30;
    const currentStage = stages.find(s => s.key === status) || stages[0];

    return (
      <div className="py-8 space-y-6">
        {/* Header */}
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin mx-auto text-purple-500 mb-3" />
          <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
            Analyzing Seatmap
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {currentStage.description}
          </p>
          <div className="mt-2 inline-flex items-center gap-2 px-3 py-1 bg-blue-100 dark:bg-blue-900/30 rounded-full text-sm text-blue-700 dark:text-blue-300">
            <span>{selectedModel.icon}</span>
            <span>Using {selectedModel.label}</span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="max-w-md mx-auto space-y-2">
          <div className="flex justify-between text-sm text-gray-500">
            <span>{currentStage.label}</span>
            <span>{progressPercent}%</span>
          </div>
          <div className="w-full h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-purple-500 to-blue-500 rounded-full transition-all duration-1000 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Stage indicators */}
        <div className="flex justify-center gap-8 text-sm">
          {stages.map((stage, idx) => {
            const isActive = stage.key === status;
            const isComplete = currentStageIndex > idx;
            return (
              <div key={stage.key} className="flex items-center gap-2">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                  isComplete ? 'bg-green-500 text-white' :
                  isActive ? 'bg-purple-500 text-white animate-pulse' :
                  'bg-gray-200 dark:bg-gray-700 text-gray-500'
                }`}>
                  {isComplete ? '✓' : idx + 1}
                </div>
                <span className={isActive ? 'text-purple-600 font-medium' : 'text-gray-500'}>
                  {stage.label}
                </span>
              </div>
            );
          })}
        </div>

        <p className="text-center text-sm text-gray-400">
          This typically takes 30-60 seconds
        </p>
      </div>
    );
  }

  // Show review UI
  if (showReview && extractionStatus?.extracted_sections) {
    const sections = extractionStatus.extracted_sections as ExtractedSection[];

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              {sections.length} Sections Found
            </h3>
            <p className="text-sm text-gray-500">
              Review and confirm the extracted sections
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setSelectedSections(new Set(sections.map(s => s.section_id)))}
              className="px-3 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded"
            >
              Select All
            </button>
            <button
              onClick={() => setSelectedSections(new Set())}
              className="px-3 py-1 text-sm text-gray-600 hover:bg-gray-50 rounded"
            >
              Clear
            </button>
          </div>
        </div>

        {/* Section List */}
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg divide-y divide-gray-200 dark:divide-gray-700 max-h-80 overflow-y-auto">
          {sections.map((section) => {
            const isSelected = selectedSections.has(section.section_id);
            const isExpanded = expandedSections.has(section.section_id);

            return (
              <div key={section.section_id} className="bg-white dark:bg-gray-800">
                <div
                  className={`flex items-center p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 ${
                    isSelected ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => handleToggleSection(section.section_id)}
                    className="w-4 h-4 mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <button
                    onClick={() => handleToggleExpand(section.section_id)}
                    className="mr-2 text-gray-400 hover:text-gray-600"
                  >
                    {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </button>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 dark:text-white">
                        Section {section.section_id}
                      </span>
                      <span className={`px-2 py-0.5 text-xs rounded ${getTierColor(section.tier)}`}>
                        {section.tier}
                      </span>
                    </div>
                    <div className="text-sm text-gray-500">
                      {section.estimated_rows} rows · {section.angle.toFixed(0)}°
                    </div>
                  </div>
                </div>
                {isExpanded && (
                  <div className="px-12 pb-3 text-sm text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50">
                    <div className="grid grid-cols-2 gap-2 py-2">
                      <div>Angle: {section.angle.toFixed(1)}°</div>
                      <div>Rows: {section.estimated_rows}</div>
                      <div>Tier: {section.tier}</div>
                      <div>Confidence: {Math.round(section.confidence * 100)}%</div>
                    </div>
                    {section.position_description && (
                      <div className="text-xs text-gray-400 mt-1">{section.position_description}</div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="text-sm text-gray-600">
            <span className="font-medium">{selectedSections.size}</span> of {sections.length} sections selected
            <span className="ml-2 text-gray-400">
              ({selectedSections.size * 3} images will be generated)
            </span>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => {
                setShowReview(false);
                setExtractionId(null);
              }}
              className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
            >
              Re-extract
            </button>
            <button
              onClick={() => finalizeMutation.mutate()}
              disabled={selectedSections.size === 0 || finalizeMutation.isPending}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700
                       disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              {finalizeMutation.isPending ? 'Saving...' : `Confirm ${selectedSections.size} Sections`}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Show upload UI
  return (
    <div className="space-y-6">
      {/* Seatmap Upload */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Upload className="w-4 h-4 text-gray-500" />
          <span className="font-medium text-gray-900 dark:text-white">Seatmap Image</span>
          <span className="text-red-500">*</span>
        </div>
        <p className="text-sm text-gray-500 mb-3">
          Upload a PNG or JPG image of the venue seatmap. The AI will detect all sections automatically.
        </p>
        <SeatmapUploader
          venueId={venueId}
          imageType="seatmap"
          onUploadComplete={onSeatmapUpload}
          existingUrl={seatmapUrl || undefined}
        />
      </div>

      {/* Event Type Tag */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Tag className="w-4 h-4 text-gray-500" />
          <span className="font-medium text-gray-900 dark:text-white">Event Type</span>
        </div>
        <p className="text-sm text-gray-500 mb-3">
          Tag what kind of events this venue hosts. This helps organize your venues.
        </p>
        <div className="flex flex-wrap gap-2">
          {EVENT_TYPES.map((type) => (
            <button
              key={type.value}
              onClick={() => onEventTypeChange(type.value)}
              className={`px-4 py-2 rounded-lg border-2 flex items-center gap-2 transition-all ${
                eventType === type.value
                  ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 text-gray-700 dark:text-gray-300'
              }`}
            >
              <span>{type.icon}</span>
              <span className="font-medium">{type.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Extraction Model Selector */}
      {hasSeatmap && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Brain className="w-4 h-4 text-gray-500" />
            <span className="font-medium text-gray-900 dark:text-white">Extraction Model</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {EXTRACTION_MODELS.map((model) => (
              <button
                key={model.value}
                onClick={() => !model.disabled && setExtractionModel(model.value)}
                disabled={model.disabled}
                className={`p-3 rounded-lg border-2 text-left transition-all relative ${
                  extractionModel === model.value
                    ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20'
                    : model.disabled
                      ? 'border-gray-200 dark:border-gray-700 opacity-50 cursor-not-allowed'
                      : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                }`}
              >
                {model.recommended && (
                  <span className="absolute -top-2 -right-2 px-1.5 py-0.5 bg-green-500 text-white text-xs rounded-full">
                    Active
                  </span>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-xl">{model.icon}</span>
                  <div>
                    <div className="font-medium text-gray-900 dark:text-white text-sm">{model.label}</div>
                    <div className="text-xs text-gray-500">{model.description}</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Reference Image (Optional, collapsible) */}
      <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
        <button
          onClick={() => setShowReferenceUpload(!showReferenceUpload)}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          {showReferenceUpload ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          <ImageIcon className="w-4 h-4" />
          <span>Reference Image (Optional)</span>
          {referenceUrl && <span className="text-green-600 ml-2">Uploaded</span>}
        </button>

        {showReferenceUpload && (
          <div className="mt-3 pl-6">
            <p className="text-sm text-gray-500 mb-3">
              Upload a reference photo for style transfer. This helps generate more realistic venue-specific images.
            </p>
            <SeatmapUploader
              venueId={venueId}
              imageType="reference"
              onUploadComplete={onReferenceUpload}
              existingUrl={referenceUrl || undefined}
            />
          </div>
        )}
      </div>

      {/* Extract Button */}
      {hasSeatmap && (
        <button
          onClick={() => extractMutation.mutate()}
          disabled={extractMutation.isPending}
          className="w-full px-4 py-4 bg-purple-600 text-white rounded-lg hover:bg-purple-700
                   disabled:opacity-50 disabled:cursor-not-allowed font-medium text-lg"
        >
          {extractMutation.isPending ? 'Starting...' : 'Extract All Sections'}
        </button>
      )}

      {extractionStatus?.status === 'failed' && (
        <div className="text-center py-4 text-red-500">
          Extraction failed: {extractionStatus.error_message || 'Unknown error'}
        </div>
      )}
    </div>
  );
}

function getTierColor(tier: string): string {
  const colors: Record<string, string> = {
    floor: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300',
    lower: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
    mid: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
    upper: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300',
  };
  return colors[tier.toLowerCase()] || 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300';
}

export function UploadExtractSummary({ hasSeatmap, sectionsCount }: { hasSeatmap: boolean; sectionsCount: number }) {
  if (sectionsCount > 0) {
    return <span className="text-green-600">{sectionsCount} sections ready</span>;
  }
  if (hasSeatmap) {
    return <span className="text-blue-600">Ready to extract</span>;
  }
  return <span className="text-gray-400">Upload a seatmap to start</span>;
}
