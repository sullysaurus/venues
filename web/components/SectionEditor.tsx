'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { seatmapsApi, ExtractedSection } from '@/lib/api';

// Tier colors for visualization
const TIER_COLORS: Record<string, { fill: string; stroke: string; label: string }> = {
  floor: { fill: 'rgba(147, 51, 234, 0.3)', stroke: '#9333ea', label: 'Floor' },
  lower: { fill: 'rgba(59, 130, 246, 0.3)', stroke: '#3b82f6', label: 'Lower' },
  mid: { fill: 'rgba(34, 197, 94, 0.3)', stroke: '#22c55e', label: 'Mid' },
  upper: { fill: 'rgba(249, 115, 22, 0.3)', stroke: '#f97316', label: 'Upper' },
};

interface SectionEditorProps {
  venueId: string;
  extractionId: string;
  seatmapUrl: string;
  initialSections: ExtractedSection[];
  onFinalize?: () => void;
  className?: string;
}

export default function SectionEditor({
  venueId,
  extractionId,
  seatmapUrl,
  initialSections,
  onFinalize,
  className = '',
}: SectionEditorProps) {
  const [sections, setSections] = useState<ExtractedSection[]>(initialSections);
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 });
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSection, setNewSection] = useState<Partial<ExtractedSection>>({
    section_id: '',
    tier: 'lower',
    angle: 0,
    estimated_rows: 15,
    inner_radius: 18,
    row_depth: 0.85,
    row_rise: 0.4,
    base_height: 2,
    confidence: 1.0,
  });

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const queryClient = useQueryClient();

  // Adjust extraction mutation
  const adjustMutation = useMutation({
    mutationFn: (sectionsData: Record<string, ExtractedSection>) =>
      seatmapsApi.adjustExtraction(venueId, extractionId, sectionsData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['extraction', extractionId] });
    },
  });

  // Finalize mutation
  const finalizeMutation = useMutation({
    mutationFn: () => seatmapsApi.finalizeExtraction(venueId, extractionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['eventTypes', venueId] });
      queryClient.invalidateQueries({ queryKey: ['extractions', venueId] });
      if (onFinalize) {
        onFinalize();
      }
    },
  });

  // Load image
  useEffect(() => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imageRef.current = img;
      setImageDimensions({ width: img.width, height: img.height });
      setImageLoaded(true);
    };
    img.src = seatmapUrl;
  }, [seatmapUrl]);

  // Calculate section position on canvas based on angle
  const getSectionPosition = useCallback((section: ExtractedSection, canvasWidth: number, canvasHeight: number) => {
    const centerX = canvasWidth / 2;
    const centerY = canvasHeight / 2;

    // Convert angle to radians (0 = top, clockwise)
    const angleRad = ((section.angle - 90) * Math.PI) / 180;

    // Calculate radius based on tier
    const tierRadii: Record<string, number> = {
      floor: 0.15,
      lower: 0.25,
      mid: 0.35,
      upper: 0.45,
    };
    const radius = (tierRadii[section.tier] || 0.3) * Math.min(canvasWidth, canvasHeight);

    // Calculate position
    const x = centerX + Math.cos(angleRad) * radius;
    const y = centerY + Math.sin(angleRad) * radius;

    return { x, y };
  }, []);

  // Draw canvas
  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx || !imageLoaded || !imageRef.current) return;

    // Set canvas size to match container
    const container = containerRef.current;
    if (!container) return;

    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;

    // Calculate aspect ratio
    const imgAspect = imageDimensions.width / imageDimensions.height;
    const containerAspect = containerWidth / containerHeight;

    let drawWidth, drawHeight, offsetX, offsetY;

    if (imgAspect > containerAspect) {
      // Image is wider
      drawWidth = containerWidth;
      drawHeight = containerWidth / imgAspect;
      offsetX = 0;
      offsetY = (containerHeight - drawHeight) / 2;
    } else {
      // Image is taller
      drawHeight = containerHeight;
      drawWidth = containerHeight * imgAspect;
      offsetX = (containerWidth - drawWidth) / 2;
      offsetY = 0;
    }

    canvas.width = containerWidth;
    canvas.height = containerHeight;

    // Clear canvas
    ctx.clearRect(0, 0, containerWidth, containerHeight);

    // Draw image
    ctx.drawImage(imageRef.current, offsetX, offsetY, drawWidth, drawHeight);

    // Draw sections
    sections.forEach((section) => {
      const pos = getSectionPosition(section, drawWidth, drawHeight);
      const x = pos.x + offsetX;
      const y = pos.y + offsetY;
      const isSelected = section.section_id === selectedSection;
      const tierColor = TIER_COLORS[section.tier] || TIER_COLORS.lower;

      // Draw section marker
      const size = isSelected ? 40 : 30;

      // Outer circle
      ctx.beginPath();
      ctx.arc(x, y, size, 0, 2 * Math.PI);
      ctx.fillStyle = isSelected ? tierColor.stroke : tierColor.fill;
      ctx.fill();
      ctx.strokeStyle = tierColor.stroke;
      ctx.lineWidth = isSelected ? 3 : 2;
      ctx.stroke();

      // Section ID label
      ctx.fillStyle = isSelected ? '#fff' : tierColor.stroke;
      ctx.font = `bold ${isSelected ? 14 : 12}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(section.section_id, x, y);

      // Confidence indicator (small arc)
      if (section.confidence < 1) {
        const confAngle = section.confidence * 2 * Math.PI;
        ctx.beginPath();
        ctx.arc(x, y, size + 5, -Math.PI / 2, -Math.PI / 2 + confAngle);
        ctx.strokeStyle = section.confidence > 0.7 ? '#22c55e' : section.confidence > 0.4 ? '#f59e0b' : '#ef4444';
        ctx.lineWidth = 3;
        ctx.stroke();
      }
    });
  }, [sections, selectedSection, imageLoaded, imageDimensions, getSectionPosition]);

  // Redraw on changes
  useEffect(() => {
    drawCanvas();
  }, [drawCanvas]);

  // Redraw on resize
  useEffect(() => {
    const handleResize = () => {
      drawCanvas();
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [drawCanvas]);

  // Handle canvas click
  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || !imageLoaded) return;

    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    // Calculate image positioning
    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;
    const imgAspect = imageDimensions.width / imageDimensions.height;
    const containerAspect = containerWidth / containerHeight;

    let drawWidth, drawHeight, offsetX, offsetY;
    if (imgAspect > containerAspect) {
      drawWidth = containerWidth;
      drawHeight = containerWidth / imgAspect;
      offsetX = 0;
      offsetY = (containerHeight - drawHeight) / 2;
    } else {
      drawHeight = containerHeight;
      drawWidth = containerHeight * imgAspect;
      offsetX = (containerWidth - drawWidth) / 2;
      offsetY = 0;
    }

    // Find clicked section
    let clickedSection: string | null = null;
    let minDist = Infinity;

    sections.forEach((section) => {
      const pos = getSectionPosition(section, drawWidth, drawHeight);
      const x = pos.x + offsetX;
      const y = pos.y + offsetY;
      const dist = Math.sqrt((clickX - x) ** 2 + (clickY - y) ** 2);

      if (dist < 40 && dist < minDist) {
        minDist = dist;
        clickedSection = section.section_id;
      }
    });

    setSelectedSection(clickedSection);
  }, [sections, imageLoaded, imageDimensions, getSectionPosition]);

  // Update section
  const updateSection = (sectionId: string, updates: Partial<ExtractedSection>) => {
    setSections(prev =>
      prev.map(s =>
        s.section_id === sectionId ? { ...s, ...updates } : s
      )
    );
  };

  // Delete section
  const deleteSection = (sectionId: string) => {
    setSections(prev => prev.filter(s => s.section_id !== sectionId));
    if (selectedSection === sectionId) {
      setSelectedSection(null);
    }
  };

  // Add new section
  const addSection = () => {
    if (!newSection.section_id) return;

    const sectionToAdd: ExtractedSection = {
      section_id: newSection.section_id!,
      tier: newSection.tier || 'lower',
      angle: newSection.angle || 0,
      estimated_rows: newSection.estimated_rows || 15,
      inner_radius: newSection.inner_radius || 18,
      row_depth: newSection.row_depth || 0.85,
      row_rise: newSection.row_rise || 0.4,
      base_height: newSection.base_height || 2,
      confidence: 1.0,
    };

    setSections(prev => [...prev, sectionToAdd]);
    setNewSection({
      section_id: '',
      tier: 'lower',
      angle: 0,
      estimated_rows: 15,
      inner_radius: 18,
      row_depth: 0.85,
      row_rise: 0.4,
      base_height: 2,
      confidence: 1.0,
    });
    setShowAddForm(false);
  };

  // Save adjustments
  const handleSave = () => {
    const sectionsMap: Record<string, ExtractedSection> = {};
    sections.forEach(s => {
      sectionsMap[s.section_id] = s;
    });
    adjustMutation.mutate(sectionsMap);
  };

  // Finalize
  const handleFinalize = () => {
    if (confirm('Finalize these sections? This will commit them to the database and they can be used in pipelines.')) {
      // Save first, then finalize
      const sectionsMap: Record<string, ExtractedSection> = {};
      sections.forEach(s => {
        sectionsMap[s.section_id] = s;
      });
      adjustMutation.mutate(sectionsMap, {
        onSuccess: () => {
          finalizeMutation.mutate();
        },
      });
    }
  };

  const selectedSectionData = sections.find(s => s.section_id === selectedSection);

  return (
    <div className={`flex flex-col lg:flex-row gap-4 ${className}`}>
      {/* Canvas Area */}
      <div className="flex-1">
        <div
          ref={containerRef}
          className="relative bg-gray-100 dark:bg-gray-800 rounded-lg overflow-hidden"
          style={{ minHeight: '400px', aspectRatio: imageDimensions.width && imageDimensions.height ? `${imageDimensions.width}/${imageDimensions.height}` : '16/9' }}
        >
          {!imageLoaded && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-gray-500">Loading seatmap...</div>
            </div>
          )}
          <canvas
            ref={canvasRef}
            onClick={handleCanvasClick}
            className="absolute inset-0 cursor-pointer"
            style={{ width: '100%', height: '100%' }}
          />
        </div>

        {/* Legend */}
        <div className="mt-3 flex flex-wrap gap-3 text-sm">
          {Object.entries(TIER_COLORS).map(([tier, { fill, stroke, label }]) => (
            <div key={tier} className="flex items-center gap-1">
              <div
                className="w-4 h-4 rounded-full border-2"
                style={{ backgroundColor: fill, borderColor: stroke }}
              />
              <span className="text-gray-600 dark:text-gray-400">{label}</span>
            </div>
          ))}
        </div>

        {/* Section count */}
        <div className="mt-2 text-sm text-gray-500">
          {sections.length} sections detected • Click a section to edit
        </div>
      </div>

      {/* Properties Panel */}
      <div className="lg:w-80 space-y-4">
        {/* Selected Section Editor */}
        {selectedSectionData ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-semibold text-gray-900 dark:text-white">
                Section {selectedSectionData.section_id}
              </h3>
              <button
                onClick={() => deleteSection(selectedSectionData.section_id)}
                className="text-red-500 hover:text-red-600 text-sm"
              >
                Delete
              </button>
            </div>

            {/* Confidence */}
            <div className="mb-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600 dark:text-gray-400">Confidence:</span>
                <span className={`text-sm font-medium ${
                  selectedSectionData.confidence > 0.7 ? 'text-green-600' :
                  selectedSectionData.confidence > 0.4 ? 'text-yellow-600' : 'text-red-600'
                }`}>
                  {Math.round(selectedSectionData.confidence * 100)}%
                </span>
              </div>
            </div>

            {/* Tier */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Tier
              </label>
              <select
                value={selectedSectionData.tier}
                onChange={(e) => updateSection(selectedSectionData.section_id, { tier: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                         bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              >
                <option value="floor">Floor</option>
                <option value="lower">Lower</option>
                <option value="mid">Mid</option>
                <option value="upper">Upper</option>
              </select>
            </div>

            {/* Angle */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Angle (0-360)
              </label>
              <input
                type="number"
                min="0"
                max="360"
                step="5"
                value={selectedSectionData.angle}
                onChange={(e) => updateSection(selectedSectionData.section_id, { angle: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                         bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>

            {/* Estimated Rows */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Rows
              </label>
              <input
                type="number"
                min="1"
                max="50"
                value={selectedSectionData.estimated_rows}
                onChange={(e) => updateSection(selectedSectionData.section_id, { estimated_rows: parseInt(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                         bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>

            {/* Inner Radius */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Inner Radius (m)
              </label>
              <input
                type="number"
                min="5"
                max="100"
                step="0.5"
                value={selectedSectionData.inner_radius}
                onChange={(e) => updateSection(selectedSectionData.section_id, { inner_radius: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                         bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>

            {/* Row Depth */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Row Depth (m)
              </label>
              <input
                type="number"
                min="0.5"
                max="2"
                step="0.05"
                value={selectedSectionData.row_depth}
                onChange={(e) => updateSection(selectedSectionData.section_id, { row_depth: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                         bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>

            {/* Row Rise */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Row Rise (m)
              </label>
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={selectedSectionData.row_rise}
                onChange={(e) => updateSection(selectedSectionData.section_id, { row_rise: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                         bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>

            {/* Base Height */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Base Height (m)
              </label>
              <input
                type="number"
                min="0"
                max="30"
                step="0.5"
                value={selectedSectionData.base_height}
                onChange={(e) => updateSection(selectedSectionData.section_id, { base_height: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                         bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>

            {selectedSectionData.position_description && (
              <div className="mt-3 p-2 bg-gray-100 dark:bg-gray-700 rounded text-xs text-gray-600 dark:text-gray-400">
                {selectedSectionData.position_description}
              </div>
            )}
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
            <p className="text-gray-500 dark:text-gray-400 text-sm text-center">
              Click a section on the seatmap to edit its properties
            </p>
          </div>
        )}

        {/* Add Section */}
        {showAddForm ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Add Section</h3>

            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Section ID
                </label>
                <input
                  type="text"
                  value={newSection.section_id || ''}
                  onChange={(e) => setNewSection({ ...newSection, section_id: e.target.value })}
                  placeholder="e.g., 101, A1"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                           bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Tier
                </label>
                <select
                  value={newSection.tier}
                  onChange={(e) => setNewSection({ ...newSection, tier: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                           bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                >
                  <option value="floor">Floor</option>
                  <option value="lower">Lower</option>
                  <option value="mid">Mid</option>
                  <option value="upper">Upper</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Angle
                </label>
                <input
                  type="number"
                  min="0"
                  max="360"
                  step="5"
                  value={newSection.angle}
                  onChange={(e) => setNewSection({ ...newSection, angle: parseFloat(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                           bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Rows
                </label>
                <input
                  type="number"
                  min="1"
                  max="50"
                  value={newSection.estimated_rows}
                  onChange={(e) => setNewSection({ ...newSection, estimated_rows: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                           bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                />
              </div>

              <div className="flex gap-2">
                <button
                  onClick={addSection}
                  disabled={!newSection.section_id}
                  className="flex-1 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700
                           disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  Add
                </button>
                <button
                  onClick={() => setShowAddForm(false)}
                  className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                           text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 text-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowAddForm(true)}
            className="w-full px-3 py-2 border-2 border-dashed border-gray-300 dark:border-gray-600
                     rounded-lg text-gray-500 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500
                     hover:text-gray-600 dark:hover:text-gray-300 text-sm"
          >
            + Add Section
          </button>
        )}

        {/* Section List */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">All Sections</h3>
          <div className="max-h-60 overflow-y-auto space-y-2">
            {sections.map((section) => {
              const tierColor = TIER_COLORS[section.tier] || TIER_COLORS.lower;
              const isSelected = section.section_id === selectedSection;

              return (
                <button
                  key={section.section_id}
                  onClick={() => setSelectedSection(section.section_id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    isSelected
                      ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500'
                      : 'bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600'
                  } border`}
                  style={{ borderColor: isSelected ? tierColor.stroke : 'transparent' }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: tierColor.stroke }}
                      />
                      <span className="font-medium text-gray-900 dark:text-white">
                        {section.section_id}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500">
                      {tierColor.label} • {section.estimated_rows} rows
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="space-y-2">
          <button
            onClick={handleSave}
            disabled={adjustMutation.isPending}
            className="w-full px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700
                     disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {adjustMutation.isPending ? 'Saving...' : 'Save Changes'}
          </button>
          <button
            onClick={handleFinalize}
            disabled={finalizeMutation.isPending || adjustMutation.isPending}
            className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700
                     disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {finalizeMutation.isPending ? 'Finalizing...' : 'Finalize & Commit'}
          </button>
        </div>

        {/* Status Messages */}
        {adjustMutation.isSuccess && (
          <div className="text-sm text-green-600 dark:text-green-400 text-center">
            Changes saved successfully
          </div>
        )}
        {finalizeMutation.isSuccess && (
          <div className="text-sm text-green-600 dark:text-green-400 text-center">
            Sections finalized! Ready for pipeline.
          </div>
        )}
        {(adjustMutation.error || finalizeMutation.error) && (
          <div className="text-sm text-red-500 text-center">
            Error: {((adjustMutation.error || finalizeMutation.error) as Error)?.message}
          </div>
        )}
      </div>
    </div>
  );
}
