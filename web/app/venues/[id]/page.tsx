'use client';

import { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { MapPin } from 'lucide-react';
import { venuesApi, imagesApi, seatmapsApi, pipelinesApi, PipelineProgress } from '@/lib/api';
import { CollapsibleSection, SectionStatus } from '@/components/CollapsibleSection';
import { UploadExtractSection, UploadExtractSummary } from '@/components/venue/UploadExtractSection';
import { SelectConfigureSection, SelectConfigureSummary } from '@/components/venue/SelectConfigureSection';

export default function VenueDetailPage() {
  const params = useParams();
  const venueId = params.id as string;
  const queryClient = useQueryClient();

  // Local state
  const [seatmapUrl, setSeatmapUrl] = useState<string | null>(null);
  const [referenceUrl, setReferenceUrl] = useState<string | null>(null);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [pipelineProgress, setPipelineProgress] = useState<PipelineProgress | null>(null);

  // Fetch venue data
  const { data: venue, isLoading: venueLoading } = useQuery({
    queryKey: ['venue', venueId],
    queryFn: () => venuesApi.get(venueId).then((res) => res.data),
  });

  // Fetch sections
  const { data: sectionsData } = useQuery({
    queryKey: ['sections', venueId],
    queryFn: () => venuesApi.getSections(venueId).then((res) => res.data),
  });

  // Fetch images
  const { data: imagesData } = useQuery({
    queryKey: ['images', venueId],
    queryFn: () => imagesApi.list(venueId).then((res) => res.data),
  });

  const sections = sectionsData?.sections || {};
  const images = imagesData?.images || [];
  const sectionsCount = Object.keys(sections).length;
  const imagesCount = images.length;
  const hasSeatmap = venue?.has_seatmap || false;

  // Poll for pipeline progress
  useEffect(() => {
    if (!workflowId) {
      console.log('[Polling] No workflowId, skipping poll');
      return;
    }

    console.log('[Polling] Starting poll for workflow:', workflowId);

    const pollProgress = async () => {
      try {
        console.log('[Polling] Fetching progress...');
        const response = await pipelinesApi.getProgress(workflowId);
        console.log('[Polling] Got progress:', response.data);
        setPipelineProgress(response.data);

        // Check for completion (note: stage is 'completed' not 'complete')
        if (response.data.stage === 'completed') {
          console.log('[Polling] Pipeline completed, refreshing images');
          queryClient.invalidateQueries({ queryKey: ['images', venueId] });
        }
      } catch (error) {
        console.error('[Polling] Failed to get progress:', error);
      }
    };

    pollProgress();
    const interval = setInterval(pollProgress, 2000);
    return () => {
      console.log('[Polling] Stopping poll');
      clearInterval(interval);
    };
  }, [workflowId, venueId, queryClient]);

  // Determine section statuses (simplified - just 2 steps now)
  const getSectionStatus = (step: number): SectionStatus => {
    const pipelineStage = pipelineProgress?.stage;
    const pipelineRunning = workflowId && pipelineStage && !['completed', 'failed', 'cancelled'].includes(pipelineStage);

    switch (step) {
      case 1: // Upload & Extract
        if (sectionsCount > 0) return 'completed';
        if (hasSeatmap) return 'current';
        return 'current';

      case 2: // Select, Configure & Generate
        if (pipelineRunning) return 'in_progress';
        if (imagesCount > 0) return 'completed';
        if (sectionsCount > 0) return 'current';
        return 'locked';

      default:
        return 'upcoming';
    }
  };

  // Handlers
  const handleSeatmapUpload = (url: string) => {
    setSeatmapUrl(url);
    queryClient.invalidateQueries({ queryKey: ['venue', venueId] });
  };

  const handleReferenceUpload = (url: string) => {
    setReferenceUrl(url);
  };

  const handleExtractionComplete = () => {
    queryClient.invalidateQueries({ queryKey: ['sections', venueId] });
  };

  const handleWorkflowStart = (id: string) => {
    setWorkflowId(id);
    setPipelineProgress(null);
  };

  const handlePipelineComplete = () => {
    queryClient.invalidateQueries({ queryKey: ['images', venueId] });
  };

  if (venueLoading) {
    return (
      <div className="p-6 text-center text-gray-500">Loading venue...</div>
    );
  }

  if (!venue) {
    return (
      <div className="p-6 text-center text-red-500">
        Venue not found. <Link href="/venues" className="text-blue-600 hover:underline">Back to venues</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <Link
            href="/venues"
            className="text-sm text-blue-600 hover:underline flex items-center gap-1"
          >
            &larr; Back to Venues
          </Link>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mt-2">
            {venue.name}
          </h1>
          {venue.location && (
            <p className="text-gray-500 flex items-center gap-1 mt-1">
              <MapPin className="w-4 h-4" />
              {venue.location}
            </p>
          )}
        </div>

        {/* Quick Stats */}
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

      {/* Simplified 2-Step Workflow */}
      <div className="space-y-3">
        {/* Step 1: Upload & Extract */}
        <CollapsibleSection
          title="Upload & Extract Sections"
          stepNumber={1}
          status={getSectionStatus(1)}
          summary={<UploadExtractSummary hasSeatmap={hasSeatmap} sectionsCount={sectionsCount} />}
        >
          <UploadExtractSection
            venueId={venueId}
            hasSeatmap={hasSeatmap}
            seatmapUrl={seatmapUrl}
            referenceUrl={referenceUrl}
            sectionsCount={sectionsCount}
            onSeatmapUpload={handleSeatmapUpload}
            onReferenceUpload={handleReferenceUpload}
            onExtractionComplete={handleExtractionComplete}
          />
        </CollapsibleSection>

        {/* Step 2: Select, Configure & Generate */}
        <CollapsibleSection
          title="Select, Configure & Generate"
          stepNumber={2}
          status={getSectionStatus(2)}
          summary={<SelectConfigureSummary sectionsCount={sectionsCount} progress={pipelineProgress} imagesCount={imagesCount} />}
        >
          <SelectConfigureSection
            venueId={venueId}
            sections={sections}
            hasReferenceImage={!!referenceUrl}
            workflowId={workflowId}
            progress={pipelineProgress}
            images={images}
            onWorkflowStart={handleWorkflowStart}
            onPipelineComplete={handlePipelineComplete}
          />
        </CollapsibleSection>
      </div>
    </div>
  );
}
