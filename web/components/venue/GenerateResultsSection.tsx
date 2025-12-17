'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { pipelinesApi, imagesApi, PipelineProgress } from '@/lib/api';
import {
  Loader2, X, Check, AlertCircle, Eye, Box, Layers, Sparkles,
  ChevronDown, ChevronUp, ZoomIn
} from 'lucide-react';

interface SeatImage {
  seat_id: string;
  section: string;
  row: string;
  seat: number;
  tier: string;
  depth_map_url?: string;
  final_image_url?: string;
}

interface GenerateResultsSectionProps {
  venueId: string;
  workflowId: string | null;
  progress: PipelineProgress | null;
  images: SeatImage[];
  sections: Record<string, { tier: string; rows: number }>;
  onPipelineComplete: () => void;
}

// Stage configuration with clear descriptions
const STAGES = [
  {
    key: 'generating_seats',
    label: 'Coordinates',
    icon: Box,
    description: 'Calculating camera positions for each seat'
  },
  {
    key: 'building_model',
    label: '3D Model',
    icon: Layers,
    description: 'Building the arena in Blender'
  },
  {
    key: 'rendering_depths',
    label: 'Depth Maps',
    icon: Eye,
    description: 'Rendering perspective from each seat'
  },
  {
    key: 'generating_images',
    label: 'AI Views',
    icon: Sparkles,
    description: 'Generating photorealistic images'
  },
];

export function GenerateResultsSection({
  venueId,
  workflowId,
  progress,
  images,
  sections,
  onPipelineComplete,
}: GenerateResultsSectionProps) {
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  const [showDepthMaps, setShowDepthMaps] = useState(false);
  const [expandedImage, setExpandedImage] = useState<string | null>(null);

  const cancelMutation = useMutation({
    mutationFn: () => pipelinesApi.cancel(workflowId!),
    onSuccess: onPipelineComplete,
  });

  const isPipelineRunning = workflowId && progress &&
    !['completed', 'failed', 'cancelled'].includes(progress.stage);
  const isPipelineComplete = progress?.stage === 'completed';
  const isPipelineFailed = progress?.stage === 'failed' || progress?.stage === 'cancelled';

  // Filter images
  const tiers = [...new Set(images.map((img) => img.tier))].sort();
  const filteredImages = selectedTier
    ? images.filter((img) => img.tier === selectedTier)
    : images;

  // Get current stage index
  const getCurrentStageIndex = () => {
    if (!progress) return -1;
    return STAGES.findIndex(s => s.key === progress.stage);
  };

  // Calculate progress
  const getProgressInfo = () => {
    if (!progress) return { percent: 0, label: 'Starting...' };

    const stageIndex = getCurrentStageIndex();
    const basePercent = ((stageIndex + 1) / STAGES.length) * 100;

    // Calculate sub-progress within current stage
    let subProgress = 0;
    const totalViews = progress.total_steps || 3;

    if (progress.stage === 'rendering_depths') {
      subProgress = (progress.depth_maps_rendered / totalViews) * (100 / STAGES.length);
    } else if (progress.stage === 'generating_images') {
      subProgress = (progress.images_generated / totalViews) * (100 / STAGES.length);
    }

    const percent = Math.min(basePercent + subProgress, 100);
    const stage = STAGES[stageIndex];

    return {
      percent,
      label: stage?.description || 'Processing...',
      stageName: stage?.label || 'Processing'
    };
  };

  // Empty state
  if (!workflowId && images.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4">
        <div className="w-20 h-20 rounded-full bg-gradient-to-br from-purple-100 to-blue-100 dark:from-purple-900/30 dark:to-blue-900/30 flex items-center justify-center mb-6">
          <Sparkles className="w-10 h-10 text-purple-500" />
        </div>
        <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
          Ready to Generate Views
        </h3>
        <p className="text-gray-500 text-center max-w-md">
          Select sections above and click "Generate Views" to create photorealistic seat perspectives
        </p>
      </div>
    );
  }

  // Pipeline running
  if (isPipelineRunning) {
    const { percent, label, stageName } = getProgressInfo();
    const currentIndex = getCurrentStageIndex();

    return (
      <div className="space-y-8 py-4">
        {/* Main Progress */}
        <div className="text-center space-y-4">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-purple-100 dark:bg-purple-900/30">
            <Loader2 className="w-8 h-8 animate-spin text-purple-600" />
          </div>
          <div>
            <h3 className="text-2xl font-bold text-gray-900 dark:text-white">
              {stageName}
            </h3>
            <p className="text-gray-500 mt-1">{label}</p>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="space-y-3">
          <div className="flex justify-between items-center text-sm">
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {progress?.images_generated || 0} of {progress?.total_steps || '?'} seat views
            </span>
            <span className="font-mono text-purple-600">{Math.round(percent)}%</span>
          </div>
          <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-purple-500 via-purple-600 to-blue-500 transition-all duration-700 ease-out"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>

        {/* Stage Steps */}
        <div className="relative">
          {/* Connection Line */}
          <div className="absolute top-6 left-8 right-8 h-0.5 bg-gray-200 dark:bg-gray-700" />

          <div className="relative flex justify-between">
            {STAGES.map((stage, idx) => {
              const Icon = stage.icon;
              const isComplete = idx < currentIndex;
              const isCurrent = idx === currentIndex;
              const isPending = idx > currentIndex;

              return (
                <div key={stage.key} className="flex flex-col items-center z-10">
                  <div
                    className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-300 ${
                      isComplete
                        ? 'bg-green-500 text-white shadow-lg shadow-green-500/30'
                        : isCurrent
                          ? 'bg-purple-500 text-white shadow-lg shadow-purple-500/30 animate-pulse'
                          : 'bg-gray-100 dark:bg-gray-800 text-gray-400'
                    }`}
                  >
                    {isComplete ? <Check className="w-5 h-5" /> : <Icon className="w-5 h-5" />}
                  </div>
                  <span className={`mt-2 text-xs font-medium ${
                    isCurrent ? 'text-purple-600' : isComplete ? 'text-green-600' : 'text-gray-400'
                  }`}>
                    {stage.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Live Stats */}
        {(progress?.depth_maps_rendered > 0 || progress?.images_generated > 0) && (
          <div className="grid grid-cols-3 gap-4 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl">
            <StatCard
              label="Seats Calculated"
              value={progress?.seats_generated || 0}
              color="blue"
            />
            <StatCard
              label="Depth Maps"
              value={progress?.depth_maps_rendered || 0}
              color="amber"
            />
            <StatCard
              label="AI Views"
              value={progress?.images_generated || 0}
              color="purple"
            />
          </div>
        )}

        {/* Cancel Button */}
        <button
          onClick={() => cancelMutation.mutate()}
          disabled={cancelMutation.isPending}
          className="w-full py-3 border-2 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400
                   rounded-xl hover:border-red-300 hover:text-red-500 transition-colors
                   disabled:opacity-50 flex items-center justify-center gap-2 font-medium"
        >
          <X className="w-4 h-4" />
          {cancelMutation.isPending ? 'Cancelling...' : 'Cancel Generation'}
        </button>
      </div>
    );
  }

  // Pipeline failed
  if (isPipelineFailed) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
          <AlertCircle className="w-8 h-8 text-red-500" />
        </div>
        <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
          {progress?.stage === 'cancelled' ? 'Generation Cancelled' : 'Generation Failed'}
        </h3>
        <p className="text-gray-500 text-center max-w-md">
          {progress?.message || 'An error occurred during generation'}
        </p>
        {images.length > 0 && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Check className="w-4 h-4 text-green-500" />
            {images.length} views were saved before stopping
          </div>
        )}
      </div>
    );
  }

  // Results view
  return (
    <div className="space-y-6">
      {/* Success Header */}
      {isPipelineComplete && (
        <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-xl border border-green-200 dark:border-green-800">
          <div className="w-12 h-12 rounded-full bg-green-500 flex items-center justify-center flex-shrink-0">
            <Check className="w-6 h-6 text-white" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-green-800 dark:text-green-200">
              All Views Generated Successfully
            </h3>
            <p className="text-sm text-green-600 dark:text-green-400">
              {images.length} photorealistic seat views ready to use
            </p>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Tier Filter */}
        {tiers.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            <FilterPill
              active={selectedTier === null}
              onClick={() => setSelectedTier(null)}
              count={images.length}
            >
              All Tiers
            </FilterPill>
            {tiers.map((tier) => (
              <FilterPill
                key={tier}
                active={selectedTier === tier}
                onClick={() => setSelectedTier(tier)}
                count={images.filter((img) => img.tier === tier).length}
              >
                {tier}
              </FilterPill>
            ))}
          </div>
        )}

        {/* View Toggle */}
        <button
          onClick={() => setShowDepthMaps(!showDepthMaps)}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            showDepthMaps
              ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
              : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 hover:bg-gray-200'
          }`}
        >
          <Eye className="w-4 h-4" />
          {showDepthMaps ? 'Hide' : 'Show'} Depth Maps
        </button>
      </div>

      {/* Image Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredImages.map((image) => (
          <ImageCard
            key={image.seat_id}
            venueId={venueId}
            image={image}
            showDepthMap={showDepthMaps}
            onExpand={() => setExpandedImage(image.seat_id)}
          />
        ))}
      </div>

      {/* Empty filter result */}
      {filteredImages.length === 0 && images.length > 0 && (
        <div className="text-center py-8 text-gray-500">
          No images in this tier. Try selecting a different filter.
        </div>
      )}

      {/* Lightbox */}
      {expandedImage && (
        <ImageLightbox
          venueId={venueId}
          image={images.find(img => img.seat_id === expandedImage)!}
          onClose={() => setExpandedImage(null)}
          showDepthMap={showDepthMaps}
        />
      )}
    </div>
  );
}

// Stat Card Component
function StatCard({ label, value, color }: { label: string; value: number; color: 'blue' | 'amber' | 'purple' }) {
  const colors = {
    blue: 'text-blue-600',
    amber: 'text-amber-600',
    purple: 'text-purple-600',
  };

  return (
    <div className="text-center">
      <div className={`text-2xl font-bold ${colors[color]}`}>{value}</div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
    </div>
  );
}

// Filter Pill Component
function FilterPill({
  children,
  active,
  onClick,
  count
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: () => void;
  count: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
        active
          ? 'bg-purple-600 text-white shadow-md shadow-purple-500/20'
          : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
      }`}
    >
      <span className="capitalize">{children}</span>
      <span className={`ml-1.5 ${active ? 'text-purple-200' : 'text-gray-400'}`}>
        {count}
      </span>
    </button>
  );
}

// Image Card Component
function ImageCard({
  venueId,
  image,
  showDepthMap,
  onExpand
}: {
  venueId: string;
  image: SeatImage;
  showDepthMap: boolean;
  onExpand: () => void;
}) {
  const imageUrl = image.final_image_url || imagesApi.getImageUrl(venueId, image.seat_id);
  const depthUrl = image.depth_map_url || `${imagesApi.getImageUrl(venueId, image.seat_id)}_depth`;

  return (
    <div
      className="group relative bg-white dark:bg-gray-800 rounded-xl overflow-hidden shadow-sm
                 hover:shadow-lg transition-all duration-300 cursor-pointer border border-gray-100 dark:border-gray-700"
      onClick={onExpand}
    >
      {/* Image */}
      <div className="aspect-video relative overflow-hidden">
        {showDepthMap ? (
          <div className="grid grid-cols-2 h-full">
            <img
              src={depthUrl}
              alt="Depth map"
              className="w-full h-full object-cover"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
              }}
            />
            <img
              src={imageUrl}
              alt={`Section ${image.section}`}
              className="w-full h-full object-cover"
              onError={(e) => {
                (e.target as HTMLImageElement).src = '/placeholder.png';
              }}
            />
          </div>
        ) : (
          <img
            src={imageUrl}
            alt={`Section ${image.section}, Row ${image.row}`}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            onError={(e) => {
              (e.target as HTMLImageElement).src = '/placeholder.png';
            }}
          />
        )}

        {/* Hover Overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent
                       opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end p-3">
          <ZoomIn className="absolute top-3 right-3 w-5 h-5 text-white/80" />
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-semibold text-gray-900 dark:text-white">
              Section {image.section}
            </div>
            <div className="text-sm text-gray-500">
              {image.row} Row
            </div>
          </div>
          <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${getTierColor(image.tier)}`}>
            {image.tier}
          </span>
        </div>
      </div>
    </div>
  );
}

// Lightbox Component
function ImageLightbox({
  venueId,
  image,
  onClose,
  showDepthMap
}: {
  venueId: string;
  image: SeatImage;
  onClose: () => void;
  showDepthMap: boolean;
}) {
  const imageUrl = image.final_image_url || imagesApi.getImageUrl(venueId, image.seat_id);
  const depthUrl = image.depth_map_url || `${imagesApi.getImageUrl(venueId, image.seat_id)}_depth`;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <button
        className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
        onClick={onClose}
      >
        <X className="w-6 h-6 text-white" />
      </button>

      <div className="max-w-5xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className={`grid ${showDepthMap ? 'grid-cols-2 gap-4' : 'grid-cols-1'}`}>
          {showDepthMap && (
            <div className="space-y-2">
              <div className="text-sm text-gray-400 font-medium">Depth Map</div>
              <img
                src={depthUrl}
                alt="Depth map"
                className="w-full rounded-lg"
              />
            </div>
          )}
          <div className="space-y-2">
            {showDepthMap && <div className="text-sm text-gray-400 font-medium">AI Generated View</div>}
            <img
              src={imageUrl}
              alt={`Section ${image.section}`}
              className="w-full rounded-lg"
            />
          </div>
        </div>

        <div className="mt-4 text-center">
          <h3 className="text-xl font-semibold text-white">
            Section {image.section} · {image.row} Row
          </h3>
          <p className="text-gray-400 mt-1 capitalize">{image.tier} Level</p>
        </div>
      </div>
    </div>
  );
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

export function GenerateResultsSummary({
  progress,
  imagesCount,
}: {
  progress: PipelineProgress | null;
  imagesCount: number;
}) {
  if (progress && !['completed', 'failed', 'cancelled'].includes(progress.stage)) {
    const stageLabels: Record<string, string> = {
      generating_seats: 'Calculating...',
      building_model: 'Building 3D...',
      rendering_depths: 'Rendering...',
      generating_images: 'AI generating...',
    };
    return (
      <span className="flex items-center gap-2 text-purple-600">
        <Loader2 className="w-4 h-4 animate-spin" />
        {stageLabels[progress.stage] || 'Processing...'}
      </span>
    );
  }
  if (imagesCount > 0) {
    return <span className="text-green-600 font-medium">{imagesCount} views ready</span>;
  }
  return <span className="text-gray-400">Ready to generate</span>;
}
