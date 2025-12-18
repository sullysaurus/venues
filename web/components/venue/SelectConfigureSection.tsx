'use client';

import { useState, useEffect } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { pipelinesApi, PipelineProgress, Section, imagesApi, SeatImage, VenueAssets } from '@/lib/api';
import {
  Play, Settings, Image as ImageIcon, Loader2, Box, Layers, Eye, Sparkles,
  Check, ChevronDown, ChevronUp, AlertCircle, ZoomIn, X
} from 'lucide-react';

const AI_MODELS = [
  { value: 'flux', label: 'Flux Depth Pro', description: 'Best for venues (depth-conditioned)', provider: 'Replicate', recommended: true },
  { value: 'flux-schnell', label: 'Flux Schnell', description: 'Fast generation', provider: 'Replicate' },
  { value: 'flux-dev', label: 'Flux Dev', description: 'Higher quality, slower', provider: 'Replicate' },
  { value: 'flux-2', label: 'Flux 2.0', description: 'Latest Flux model', provider: 'Replicate' },
  { value: 'sdxl', label: 'SDXL ControlNet', description: 'Stable Diffusion with depth', provider: 'Replicate' },
  { value: 'dall-e-3', label: 'DALL-E 3', description: 'OpenAI (no depth conditioning)', provider: 'OpenAI' },
];

// Pipeline step definitions
const PIPELINE_STEPS = [
  {
    id: 'model',
    label: 'Build 3D Model',
    icon: Box,
    description: 'Create arena geometry in Blender',
    activeStage: 'building_model',
    completedMessage: '3D model built successfully',
  },
  {
    id: 'depths',
    label: 'Render Depth Maps',
    icon: Eye,
    description: 'Render camera view from each seat',
    activeStage: 'rendering_depths',
    completedMessage: 'Depth maps rendered',
  },
  {
    id: 'images',
    label: 'Generate AI Views',
    icon: Sparkles,
    description: 'Create photorealistic images',
    activeStage: 'generating_images',
    completedMessage: 'AI images generated',
  },
];

interface SelectConfigureSectionProps {
  venueId: string;
  sections: Record<string, Section>;
  hasReferenceImage: boolean;
  workflowId: string | null;
  progress: PipelineProgress | null;
  images: SeatImage[];
  onWorkflowStart: (id: string) => void;
  onPipelineComplete: () => void;
}

// Track which step has been completed
type CompletedStep = 'none' | 'model' | 'depths' | 'images';

export function SelectConfigureSection({
  venueId,
  sections,
  hasReferenceImage,
  workflowId,
  progress,
  images,
  onWorkflowStart,
  onPipelineComplete,
}: SelectConfigureSectionProps) {
  const [selectedSections, setSelectedSections] = useState<Set<string>>(
    new Set(Object.keys(sections))
  );
  const [prompt, setPrompt] = useState(
    'A photorealistic view from a stadium seat showing the field/stage, crowd, and venue atmosphere'
  );
  const [model, setModel] = useState('flux');  // Flux Depth Pro - best for venues
  const [useIpAdapter, setUseIpAdapter] = useState(hasReferenceImage);
  const [ipAdapterScale, setIpAdapterScale] = useState(0.6);
  // Section selection is now in Step 2
  const [showSectionSelector, setShowSectionSelector] = useState(false);
  // AI settings are now in Step 3
  const [showAISettings, setShowAISettings] = useState(false);
  // State for completed steps and existing assets
  const [completedStep, setCompletedStep] = useState<CompletedStep>(images.length > 0 ? 'images' : 'none');
  const [existingAssets, setExistingAssets] = useState<VenueAssets | null>(null);
  const [modelPreviewUrl, setModelPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [depthMaps, setDepthMaps] = useState<Array<{id: string; url: string}>>([]);
  const [expandedImage, setExpandedImage] = useState<string | null>(null);
  const [showModelPreview, setShowModelPreview] = useState(false);
  const [showDepthMaps, setShowDepthMaps] = useState(false);
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  // Track which step triggered the current workflow (bridges gap between mutation and first poll)
  const [activeStep, setActiveStep] = useState<string | null>(null);

  // Check for existing assets on mount (for resume capability)
  useEffect(() => {
    const checkExistingAssets = async () => {
      try {
        const response = await imagesApi.getAssets(venueId);
        const assets = response.data;
        setExistingAssets(assets);
        console.log('[Assets] Existing assets:', assets);

        // Set completedStep based on what exists (if not already set from images prop)
        if (completedStep === 'none') {
          if (assets.has_images && assets.image_count > 0) {
            setCompletedStep('images');
          } else if (assets.has_depth_maps && assets.depth_map_count > 0) {
            setCompletedStep('depths');
          } else if (assets.has_model) {
            setCompletedStep('model');
          }
        }

        // Load preview if model exists
        if (assets.has_preview && assets.preview_url) {
          setModelPreviewUrl(assets.preview_url);
        }

        // Load depth maps if they exist
        if (assets.has_depth_maps && assets.depth_map_count > 0) {
          loadDepthMaps();
        }
      } catch (e) {
        console.error('[Assets] Failed to check existing assets:', e);
      }
    };
    checkExistingAssets();
  }, [venueId]);

  const sectionList = Object.values(sections);
  const sectionCount = Object.keys(sections).length;
  const selectedCount = selectedSections.size;
  const imageCount = selectedCount * 3; // 3 seats per section (Front, Middle, Back)

  // For Step 3, use actual depth map count if available (can only generate images for existing depth maps)
  const availableDepthMaps = depthMaps.length || existingAssets?.depth_map_count || 0;
  const generatableImageCount = availableDepthMaps > 0 ? availableDepthMaps : imageCount;

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

  // Determine current step based on progress and completion
  const getCurrentStepIndex = () => {
    if (!progress) {
      if (completedStep === 'images') return 3;
      if (completedStep === 'depths') return 2;
      if (completedStep === 'model') return 1;
      return 0;
    }

    if (progress.stage === 'building_model' || progress.stage === 'generating_seats') return 0;
    if (progress.stage === 'rendering_depths') return 1;
    if (progress.stage === 'generating_images') return 2;
    if (progress.stage === 'completed') {
      // Check what was completed based on results
      if (progress.images_generated > 0) return 3;
      if (progress.depth_maps_rendered > 0) return 2;
      return 1;
    }
    return 0;
  };

  // Update completed step when pipeline completes
  useEffect(() => {
    if (progress?.stage === 'completed') {
      console.log('[Progress] Pipeline completed, activeStep was:', activeStep);
      if (progress.images_generated > 0) {
        setCompletedStep('images');
      } else if (progress.depth_maps_rendered > 0) {
        setCompletedStep('depths');
        // Load depth maps from storage
        loadDepthMaps();
      } else {
        setCompletedStep('model');
      }
      setActiveStep(null); // Clear active step on completion
      onPipelineComplete();
    }
  }, [progress?.stage]);

  // Load preview whenever model is completed
  useEffect(() => {
    if (completedStep === 'model' || completedStep === 'depths' || completedStep === 'images') {
      loadModelPreview();
    }
  }, [completedStep, venueId]);

  const loadModelPreview = async () => {
    setPreviewError(null);
    // Always use the API route - it handles both Supabase and local fallback
    const url = `/api/images/${venueId}/preview`;
    console.log('[Preview] Loading from:', url);
    setModelPreviewUrl(url);
  };

  const loadDepthMaps = async () => {
    // Load depth maps from Supabase Storage via API
    try {
      const response = await fetch(`/api/images/${venueId}/depth-maps`);
      if (response.ok) {
        const data = await response.json();
        console.log('[DepthMaps] Loaded:', data);
        setDepthMaps(data.depth_maps || []);
      }
    } catch (e) {
      console.error('Failed to load depth maps:', e);
    }
  };

  // Pipeline mutations for each step
  const buildModelMutation = useMutation({
    mutationFn: () => {
      console.log('[Build] Starting build mutation...');
      setActiveStep('model'); // Track which step is running

      // Build model for ALL sections (not just selected)
      return pipelinesApi.start({
        venue_id: venueId,
        sections: sections,  // Use all sections
        prompt,
        model: 'flux',  // Default model for building
        stop_after_model: true,  // Stop after building model
        surface_type: 'rink',  // Default surface (event type is just a tag now)
      });
    },
    onSuccess: (response) => {
      console.log('[Build] Success:', response.data);
      onWorkflowStart(response.data.workflow_id);
    },
    onError: (error) => {
      console.error('[Build] Error:', error);
      setActiveStep(null);
    },
  });

  const renderDepthsMutation = useMutation({
    mutationFn: () => {
      console.log('[Render] Starting render mutation...');
      setActiveStep('depths'); // Track which step is running

      // Build sections data for SELECTED sections only
      const selectedSectionsData: Record<string, Section> = {};
      selectedSections.forEach((id) => {
        if (sections[id]) {
          selectedSectionsData[id] = sections[id];
        }
      });

      return pipelinesApi.start({
        venue_id: venueId,
        sections: selectedSectionsData,
        prompt,
        model: 'flux',
        stop_after_depths: true,  // Stop after depth maps
        skip_model_build: existingAssets?.has_model ?? false,  // Use existing model if available
        surface_type: 'rink',  // Default (event type is just a tag now)
      });
    },
    onSuccess: (response) => {
      console.log('[Render] Success:', response.data);
      onWorkflowStart(response.data.workflow_id);
    },
    onError: (error) => {
      console.error('[Render] Error:', error);
      setActiveStep(null);
    },
  });

  const generateImagesMutation = useMutation({
    mutationFn: () => {
      console.log('[Generate] Starting generate mutation...');
      setActiveStep('images'); // Track which step is running

      // Uses all sections since we're generating from existing depth maps
      const selectedSectionsData: Record<string, Section> = {};
      selectedSections.forEach((id) => {
        if (sections[id]) {
          selectedSectionsData[id] = sections[id];
        }
      });

      return pipelinesApi.start({
        venue_id: venueId,
        sections: selectedSectionsData,
        prompt,
        model: useIpAdapter ? 'ip_adapter' : model,
        ip_adapter_scale: useIpAdapter ? ipAdapterScale : 0,
        skip_ai_generation: false,  // Run full pipeline
        skip_model_build: existingAssets?.has_model ?? false,  // Use existing model
        skip_depth_render: existingAssets?.has_depth_maps ?? false,  // Use existing depth maps
        surface_type: 'rink',  // Default (event type is just a tag now)
      });
    },
    onSuccess: (response) => {
      console.log('[Generate] Success:', response.data);
      onWorkflowStart(response.data.workflow_id);
    },
    onError: (error) => {
      console.error('[Generate] Error:', error);
      setActiveStep(null);
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

  const handleSelectTier = (tier: string) => {
    const tierSectionIds = sectionsByTier[tier]?.map((s) => s.section_id) || [];
    const allSelected = tierSectionIds.every((id) => selectedSections.has(id));

    const newSelected = new Set(selectedSections);
    if (allSelected) {
      tierSectionIds.forEach((id) => newSelected.delete(id));
    } else {
      tierSectionIds.forEach((id) => newSelected.add(id));
    }
    setSelectedSections(newSelected);
  };

  const handleSelectAll = () => {
    setSelectedSections(new Set(Object.keys(sections)));
  };

  const handleSelectNone = () => {
    setSelectedSections(new Set());
  };

  const isPipelineRunning = workflowId && progress &&
    !['completed', 'failed', 'cancelled'].includes(progress.stage);
  const isPipelineFailed = progress?.stage === 'failed' || progress?.stage === 'cancelled';

  // Debug logging
  useEffect(() => {
    console.log('[SelectConfigure] State:', {
      workflowId,
      activeStep,
      progressStage: progress?.stage,
      isPipelineRunning,
      completedStep,
    });
  }, [workflowId, activeStep, progress?.stage, isPipelineRunning, completedStep]);

  const currentStepIndex = getCurrentStepIndex();

  if (sectionCount === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p className="text-lg">No sections available</p>
        <p className="text-sm mt-2">Extract sections from a seatmap first</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Simple Summary - All sections available for 3D model */}
      <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-blue-500 flex items-center justify-center">
              <Layers className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-medium text-blue-900 dark:text-blue-100">
                {sectionCount} sections ready
              </div>
              <div className="text-sm text-blue-600 dark:text-blue-400">
                3 views per section: Front, Middle, Back Row
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ============ PIPELINE STEPS ============ */}
      <div className="space-y-4">
        <h3 className="font-medium text-gray-900 dark:text-white">
          Generate Views (3 Steps)
        </h3>

        {/* Step Cards */}
        <div className="grid gap-4">
          {PIPELINE_STEPS.map((step, index) => {
            const Icon = step.icon;
            // Check if this step's mutation is pending (API call in progress)
            const isMutationPending = (
              (step.id === 'model' && buildModelMutation.isPending) ||
              (step.id === 'depths' && renderDepthsMutation.isPending) ||
              (step.id === 'images' && generateImagesMutation.isPending)
            );
            // Use activeStep to bridge the gap between mutation success and first progress poll
            // This prevents the UI from flickering back to "not running" state
            const isActiveStepWaiting = activeStep === step.id && (!progress || !['completed', 'failed', 'cancelled'].includes(progress.stage));
            const isProgressRunning = isPipelineRunning && progress?.stage === step.activeStage;
            const isCurrentlyRunning = isMutationPending || isActiveStepWaiting || isProgressRunning;
            const isCompleted = (
              (step.id === 'model' && (completedStep === 'model' || completedStep === 'depths' || completedStep === 'images')) ||
              (step.id === 'depths' && (completedStep === 'depths' || completedStep === 'images')) ||
              (step.id === 'images' && completedStep === 'images')
            );
            const isAvailable = (
              (step.id === 'model' && !isPipelineRunning && !isMutationPending) ||
              (step.id === 'depths' && completedStep === 'model' && !isPipelineRunning && !isMutationPending) ||
              (step.id === 'images' && completedStep === 'depths' && availableDepthMaps > 0 && !isPipelineRunning && !isMutationPending)
            );
            const isDisabled = !isAvailable && !isCompleted && !isCurrentlyRunning;

            const handleStepClick = () => {
              console.log(`[${step.id}] Button clicked`);
              if (step.id === 'model') buildModelMutation.mutate();
              else if (step.id === 'depths') renderDepthsMutation.mutate();
              else if (step.id === 'images') generateImagesMutation.mutate();
            };

            return (
              <div
                key={step.id}
                className={`border rounded-xl overflow-hidden transition-all ${
                  isCurrentlyRunning
                    ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20 shadow-lg shadow-purple-500/10'
                    : isCompleted
                      ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                      : isDisabled
                        ? 'border-gray-200 dark:border-gray-700 opacity-50'
                        : 'border-gray-200 dark:border-gray-700 hover:border-purple-300'
                }`}
              >
                {/* Step Header */}
                <div className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                      isCurrentlyRunning
                        ? 'bg-purple-500 text-white animate-pulse'
                        : isCompleted
                          ? 'bg-green-500 text-white'
                          : 'bg-gray-100 dark:bg-gray-800 text-gray-400'
                    }`}>
                      {isCompleted ? <Check className="w-6 h-6" /> : <Icon className="w-6 h-6" />}
                    </div>
                    <div>
                      <div className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        Step {index + 1}: {step.label}
                        {isCurrentlyRunning && (
                          <Loader2 className="w-4 h-4 animate-spin text-purple-600" />
                        )}
                      </div>
                      <div className="text-sm text-gray-500">{step.description}</div>
                    </div>
                  </div>

                  {/* Step Action Button */}
                  {isCompleted ? (
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1.5 px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-sm font-medium">
                        <Check className="w-4 h-4" />
                        Complete
                      </div>
                      <button
                        onClick={handleStepClick}
                        disabled={!!isPipelineRunning}
                        className="px-3 py-1.5 text-sm rounded-lg font-medium flex items-center gap-1.5
                                   border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400
                                   hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                      >
                        <Play className="w-3 h-3" />
                        Rerun
                      </button>
                    </div>
                  ) : isCurrentlyRunning ? (
                    <div className="flex items-center gap-2 px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400 rounded-full text-sm font-medium">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {isMutationPending ? 'Starting...' : (progress?.message || 'Processing...')}
                    </div>
                  ) : (
                    <button
                      onClick={handleStepClick}
                      disabled={isDisabled || (step.id === 'depths' && selectedCount === 0) || (step.id === 'images' && availableDepthMaps === 0)}
                      className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 transition-colors ${
                        isAvailable
                          ? 'bg-purple-600 text-white hover:bg-purple-700'
                          : 'bg-gray-200 text-gray-500 cursor-not-allowed'
                      }`}
                    >
                      <Play className="w-4 h-4" />
                      {step.id === 'model' ? 'Build Model' : step.id === 'depths' ? 'Render Depths' : 'Generate Images'}
                    </button>
                  )}
                </div>

                {/* Step 2: Section Selection UI (for Render Depth Maps) */}
                {step.id === 'depths' && !isCurrentlyRunning && !isCompleted && (
                  <div className="px-4 pb-2">
                    <button
                      onClick={() => setShowSectionSelector(!showSectionSelector)}
                      className="w-full text-left flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
                    >
                      <span className="font-medium text-gray-700 dark:text-gray-300">
                        {selectedCount === sectionCount ? 'All sections selected' : `${selectedCount} of ${sectionCount} sections selected`}
                      </span>
                      {showSectionSelector ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                    </button>
                    {showSectionSelector && (
                      <div className="mt-3 p-3 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900">
                        {/* Quick Actions */}
                        <div className="flex items-center gap-2 mb-3">
                          <button
                            onClick={handleSelectAll}
                            className="px-3 py-1 text-sm bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded-lg hover:bg-purple-200 dark:hover:bg-purple-900/50"
                          >
                            Select All
                          </button>
                          <button
                            onClick={handleSelectNone}
                            className="px-3 py-1 text-sm bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700"
                          >
                            Clear
                          </button>
                          <span className="ml-auto text-sm text-gray-500">
                            {selectedCount * 3} depth maps will be rendered
                          </span>
                        </div>

                        {/* Tier Groups */}
                        <div className="space-y-3 max-h-64 overflow-y-auto">
                          {tiers.map((tier) => {
                            const tierSections = sectionsByTier[tier] || [];
                            const tierSelected = tierSections.filter((s) => selectedSections.has(s.section_id)).length;
                            const allSelected = tierSelected === tierSections.length;

                            return (
                              <div key={tier} className={`p-2 rounded-lg ${getTierBgColor(tier)}`}>
                                <button
                                  onClick={() => handleSelectTier(tier)}
                                  className="flex items-center gap-2 w-full text-left mb-2"
                                >
                                  <div className={`w-4 h-4 rounded border ${
                                    allSelected
                                      ? 'bg-purple-600 border-purple-600'
                                      : tierSelected > 0
                                        ? 'bg-purple-300 border-purple-400'
                                        : 'border-gray-300 dark:border-gray-600'
                                  } flex items-center justify-center`}>
                                    {allSelected && <Check className="w-3 h-3 text-white" />}
                                  </div>
                                  <span className="font-medium capitalize text-gray-900 dark:text-white">
                                    {tier} Level
                                  </span>
                                  <span className="text-sm text-gray-500 ml-auto">
                                    {tierSelected}/{tierSections.length}
                                  </span>
                                </button>
                                <div className="flex flex-wrap gap-1 pl-6">
                                  {tierSections.map((section) => (
                                    <button
                                      key={section.section_id}
                                      onClick={() => handleToggleSection(section.section_id)}
                                      className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
                                        selectedSections.has(section.section_id)
                                          ? 'bg-purple-600 text-white'
                                          : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-600'
                                      }`}
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
                )}

                {/* Step 3: AI Settings UI (for Generate AI Views) */}
                {step.id === 'images' && !isCurrentlyRunning && completedStep === 'depths' && availableDepthMaps > 0 && (
                  <div className="px-4 pb-2">
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
                      <div className="mt-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 space-y-4">
                        {/* AI Model Selection */}
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            AI Model
                          </label>
                          <select
                            value={model}
                            onChange={(e) => setModel(e.target.value)}
                            disabled={useIpAdapter}
                            className="w-full p-2 border rounded-lg bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white disabled:opacity-50"
                          >
                            {AI_MODELS.map((m) => (
                              <option key={m.value} value={m.value}>
                                {m.label} {m.recommended ? '(Recommended)' : ''} - {m.description}
                              </option>
                            ))}
                          </select>
                        </div>

                        {/* Prompt */}
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Scene Prompt
                          </label>
                          <textarea
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            rows={3}
                            placeholder="Describe the venue atmosphere..."
                            className="w-full p-3 border rounded-lg bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white placeholder:text-gray-400 resize-none"
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            Tip: Include venue name, event type, and atmosphere details
                          </p>
                        </div>

                        {/* Reference Image / IP-Adapter */}
                        {hasReferenceImage && (
                          <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-200 dark:border-purple-800">
                            <div className="flex items-center justify-between mb-3">
                              <label className="flex items-center gap-2 text-sm font-medium text-purple-700 dark:text-purple-300">
                                <ImageIcon className="w-4 h-4" />
                                Use Reference Image (IP-Adapter)
                              </label>
                              <button
                                onClick={() => setUseIpAdapter(!useIpAdapter)}
                                className={`relative w-12 h-6 rounded-full transition-colors ${
                                  useIpAdapter ? 'bg-purple-600' : 'bg-gray-300 dark:bg-gray-600'
                                }`}
                              >
                                <span
                                  className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                                    useIpAdapter ? 'translate-x-7' : 'translate-x-1'
                                  }`}
                                />
                              </button>
                            </div>
                            {useIpAdapter && (
                              <div>
                                <label className="block text-xs text-purple-600 dark:text-purple-400 mb-1">
                                  Style Transfer Strength: {Math.round(ipAdapterScale * 100)}%
                                </label>
                                <input
                                  type="range"
                                  min="0"
                                  max="1"
                                  step="0.1"
                                  value={ipAdapterScale}
                                  onChange={(e) => setIpAdapterScale(parseFloat(e.target.value))}
                                  className="w-full"
                                />
                                <p className="text-xs text-purple-500 dark:text-purple-400 mt-1">
                                  Higher = more similar to reference image
                                </p>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Summary */}
                        <div className="pt-3 border-t border-gray-200 dark:border-gray-700">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-gray-500">Ready to generate:</span>
                            <span className="font-medium text-gray-900 dark:text-white">
                              {availableDepthMaps} images from depth maps
                            </span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Progress Bar - Always visible */}
                <div className="px-4 pb-4">
                  <div className={`h-2 rounded-full overflow-hidden ${
                    isCurrentlyRunning
                      ? 'bg-purple-200 dark:bg-purple-800'
                      : isCompleted
                        ? 'bg-green-200 dark:bg-green-800'
                        : 'bg-gray-200 dark:bg-gray-700'
                  }`}>
                    <div
                      className={`h-full transition-all duration-500 ${
                        isCurrentlyRunning
                          ? 'bg-purple-500'
                          : isCompleted
                            ? 'bg-green-500'
                            : 'bg-gray-300 dark:bg-gray-600'
                      }`}
                      style={{
                        width: isCompleted
                          ? '100%'
                          : isCurrentlyRunning
                            ? step.id === 'depths'
                              ? `${Math.max(5, Math.min((progress?.depth_maps_rendered || 0) / Math.max(imageCount, 1) * 100, 100))}%`
                              : step.id === 'images'
                                ? `${Math.max(5, Math.min((progress?.images_generated || 0) / Math.max(imageCount, 1) * 100, 100))}%`
                                : '50%'
                            : '0%'
                      }}
                    />
                  </div>
                  {/* Progress Text */}
                  <div className="mt-2 flex items-center justify-between text-sm">
                    {isCurrentlyRunning ? (
                      <>
                        {step.id === 'model' && (
                          <span className="text-purple-600 dark:text-purple-400">Building 3D model...</span>
                        )}
                        {step.id === 'depths' && (
                          <span className="text-purple-600 dark:text-purple-400">
                            {progress?.depth_maps_rendered || 0} of {imageCount} depth maps
                          </span>
                        )}
                        {step.id === 'images' && (
                          <span className="text-purple-600 dark:text-purple-400">
                            {progress?.images_generated || 0} of {generatableImageCount} images
                          </span>
                        )}
                        <span className="text-gray-400">
                          {step.id === 'depths' && `${Math.round((progress?.depth_maps_rendered || 0) / Math.max(imageCount, 1) * 100)}%`}
                          {step.id === 'images' && `${Math.round((progress?.images_generated || 0) / Math.max(generatableImageCount, 1) * 100)}%`}
                        </span>
                      </>
                    ) : isCompleted ? (
                      <>
                        <span className="text-green-600 dark:text-green-400">{step.completedMessage}</span>
                        <span className="text-green-500">100%</span>
                      </>
                    ) : (
                      <>
                        <span className="text-gray-400">
                          {step.id === 'model' && 'Creates 3D arena geometry'}
                          {step.id === 'depths' && `${imageCount} depth maps to render`}
                          {step.id === 'images' && (
                            availableDepthMaps > 0
                              ? `${availableDepthMaps} images to generate (from depth maps)`
                              : `${imageCount} images to generate`
                          )}
                        </span>
                        <span className="text-gray-400">0%</span>
                      </>
                    )}
                  </div>
                </div>

                {/* Step Results Preview */}
                {step.id === 'model' && isCompleted && (
                  <div className="p-4 pt-0">
                    <button
                      onClick={() => setShowModelPreview(!showModelPreview)}
                      className="w-full text-left flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
                    >
                      <span className="font-medium text-gray-700 dark:text-gray-300">
                        3D Arena Model Preview
                      </span>
                      {showModelPreview ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                    </button>
                    {showModelPreview && (
                      <div className="mt-4">
                        {previewError ? (
                          <div className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg text-sm text-amber-700 dark:text-amber-300">
                            Preview not available: {previewError}
                          </div>
                        ) : modelPreviewUrl ? (
                          <div
                            className="relative rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 bg-gray-900 cursor-pointer"
                            onClick={() => setExpandedImage(modelPreviewUrl)}
                          >
                            <img
                              src={modelPreviewUrl}
                              alt="3D Model Preview"
                              className="w-full max-h-64 object-contain"
                              onLoad={() => console.log('[Preview] Image loaded successfully')}
                              onError={(e) => {
                                console.error('[Preview] Failed to load:', modelPreviewUrl);
                                setPreviewError('Image failed to load');
                              }}
                            />
                            <div className="absolute top-2 right-2">
                              <ZoomIn className="w-4 h-4 text-white/80" />
                            </div>
                          </div>
                        ) : (
                          <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm text-gray-500">
                            Loading preview...
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {step.id === 'depths' && isCompleted && depthMaps.length > 0 && (
                  <div className="p-4 pt-0">
                    <button
                      onClick={() => setShowDepthMaps(!showDepthMaps)}
                      className="w-full text-left flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
                    >
                      <span className="font-medium text-gray-700 dark:text-gray-300">
                        {depthMaps.length} Depth Maps Generated
                      </span>
                      {showDepthMaps ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                    </button>
                    {showDepthMaps && (
                      <div className="mt-4 grid grid-cols-3 gap-2">
                        {depthMaps.slice(0, 9).map((dm) => (
                          <div
                            key={dm.id}
                            className="relative rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 cursor-pointer hover:border-purple-400"
                            onClick={() => setExpandedImage(dm.url)}
                          >
                            <img
                              src={dm.url}
                              alt={`Depth map ${dm.id}`}
                              className="w-full h-20 object-cover"
                            />
                            <div className="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-xs p-1 truncate">
                              {dm.id}
                            </div>
                          </div>
                        ))}
                        {depthMaps.length > 9 && (
                          <div className="flex items-center justify-center text-gray-500 text-sm">
                            +{depthMaps.length - 9} more
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Info: Show what images will be generated from depth maps */}
                {step.id === 'images' && completedStep === 'depths' && availableDepthMaps === 0 && !isCompleted && (
                  <div className="px-4 pb-4">
                    <div className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
                        <div className="text-sm">
                          <p className="font-medium text-amber-700 dark:text-amber-300">
                            No depth maps found
                          </p>
                          <p className="text-amber-600 dark:text-amber-400 mt-1">
                            Go back to Step 2 to render depth maps first.
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Error Display */}
      {(buildModelMutation.error || renderDepthsMutation.error || generateImagesMutation.error) && (
        <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <div className="flex items-center gap-2 text-red-600 dark:text-red-400 font-medium">
            <AlertCircle className="w-5 h-5" />
            Pipeline Error
          </div>
          <div className="text-red-500 dark:text-red-300 text-sm mt-1">
            {(buildModelMutation.error as any)?.response?.data?.detail ||
              (renderDepthsMutation.error as any)?.response?.data?.detail ||
              (generateImagesMutation.error as any)?.response?.data?.detail ||
              (buildModelMutation.error as Error)?.message ||
              (renderDepthsMutation.error as Error)?.message ||
              (generateImagesMutation.error as Error)?.message}
          </div>
        </div>
      )}

      {isPipelineFailed && (
        <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <div className="flex items-center gap-2 text-red-600 dark:text-red-400 font-medium">
            <AlertCircle className="w-5 h-5" />
            {progress?.stage === 'cancelled' ? 'Pipeline Cancelled' : 'Pipeline Failed'}
          </div>
          <div className="text-red-500 dark:text-red-300 text-sm mt-1">
            {progress?.message || 'An error occurred'}
          </div>
        </div>
      )}

      {/* ============ RESULTS SECTION ============ */}
      {images.length > 0 && (
        <div className="space-y-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-lg text-gray-900 dark:text-white flex items-center gap-2">
              <Check className="w-5 h-5 text-green-500" />
              Generated Views ({images.length})
            </h3>
            <div className="flex items-center gap-4">
              {/* Tier Filter */}
              <div className="flex gap-1">
                <button
                  onClick={() => setSelectedTier(null)}
                  className={`px-2 py-1 text-xs rounded-full transition-colors ${
                    selectedTier === null
                      ? 'bg-purple-600 text-white'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200'
                  }`}
                >
                  All
                </button>
                {[...new Set(images.map(img => img.tier))].sort().map(tier => (
                  <button
                    key={tier}
                    onClick={() => setSelectedTier(tier)}
                    className={`px-2 py-1 text-xs rounded-full transition-colors capitalize ${
                      selectedTier === tier
                        ? 'bg-purple-600 text-white'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200'
                    }`}
                  >
                    {tier}
                  </button>
                ))}
              </div>
              {/* Depth Map Toggle */}
              <button
                onClick={() => setShowDepthMaps(!showDepthMaps)}
                className={`flex items-center gap-1 px-2 py-1 text-xs rounded-full transition-colors ${
                  showDepthMaps
                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                    : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 hover:bg-gray-200'
                }`}
              >
                <Eye className="w-3 h-3" />
                Depths
              </button>
            </div>
          </div>

          {/* Image Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {images
              .filter(img => !selectedTier || img.tier === selectedTier)
              .map((image) => {
                const imageUrl = image.final_image_url || imagesApi.getImageUrl(venueId, image.seat_id);
                const depthUrl = image.depth_map_url || `${imagesApi.getImageUrl(venueId, image.seat_id)}_depth`;

                return (
                  <div
                    key={image.seat_id}
                    className="group relative bg-white dark:bg-gray-800 rounded-lg overflow-hidden shadow-sm
                               hover:shadow-md transition-all cursor-pointer border border-gray-100 dark:border-gray-700"
                    onClick={() => setExpandedImage(imageUrl)}
                  >
                    <div className="aspect-video relative overflow-hidden">
                      {showDepthMaps ? (
                        <div className="grid grid-cols-2 h-full">
                          <img src={depthUrl} alt="Depth" className="w-full h-full object-cover" />
                          <img src={imageUrl} alt={`Section ${image.section}`} className="w-full h-full object-cover" />
                        </div>
                      ) : (
                        <img
                          src={imageUrl}
                          alt={`Section ${image.section}, Row ${image.row}`}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        />
                      )}
                      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent
                                     opacity-0 group-hover:opacity-100 transition-opacity">
                        <ZoomIn className="absolute top-2 right-2 w-4 h-4 text-white/80" />
                      </div>
                    </div>
                    <div className="p-2">
                      <div className="font-medium text-sm text-gray-900 dark:text-white">
                        {image.section} · {image.row}
                      </div>
                      <div className="text-xs text-gray-500 capitalize">{image.tier}</div>
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Image Lightbox */}
      {expandedImage && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setExpandedImage(null)}
        >
          <button
            className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
            onClick={() => setExpandedImage(null)}
          >
            <X className="w-6 h-6 text-white" />
          </button>
          <img
            src={expandedImage}
            alt="Expanded view"
            className="max-w-full max-h-full rounded-lg"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
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

export function SelectConfigureSummary({
  sectionsCount,
  progress,
  imagesCount = 0,
}: {
  sectionsCount: number;
  progress: PipelineProgress | null;
  imagesCount?: number;
}) {
  if (progress && !['completed', 'failed', 'cancelled'].includes(progress.stage)) {
    return <span className="text-blue-600">Pipeline running...</span>;
  }
  if (imagesCount > 0) {
    return <span className="text-green-600">{imagesCount} views generated</span>;
  }
  if (sectionsCount > 0) {
    return <span>{sectionsCount} sections ready</span>;
  }
  return <span className="text-gray-400">Waiting for sections</span>;
}
