'use client';

import { useState, useCallback, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { seatmapsApi } from '@/lib/api';

interface SeatmapUploaderProps {
  venueId: string;
  imageType?: 'seatmap' | 'reference';
  onUploadComplete?: (url: string) => void;
  existingUrl?: string;
  className?: string;
}

export default function SeatmapUploader({
  venueId,
  imageType = 'seatmap',
  onUploadComplete,
  existingUrl,
  className = '',
}: SeatmapUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [preview, setPreview] = useState<string | null>(existingUrl || null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const uploadMutation = useMutation({
    mutationFn: (file: File) => seatmapsApi.upload(venueId, file, imageType),
    onSuccess: (response) => {
      setUploadProgress(null);
      queryClient.invalidateQueries({ queryKey: ['eventTypes', venueId] });
      if (onUploadComplete) {
        onUploadComplete(response.data.url);
      }
    },
    onError: () => {
      setUploadProgress(null);
    },
  });

  const handleFile = useCallback((file: File) => {
    // Validate file type
    if (!file.type.startsWith('image/')) {
      alert('Please upload an image file (PNG, JPG, etc.)');
      return;
    }

    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      alert('File size must be less than 10MB');
      return;
    }

    // Create preview
    const reader = new FileReader();
    reader.onload = (e) => {
      setPreview(e.target?.result as string);
    };
    reader.readAsDataURL(file);

    // Upload
    setUploadProgress(0);
    uploadMutation.mutate(file);
  }, [uploadMutation]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      handleFile(file);
    }
  }, [handleFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFile(file);
    }
  }, [handleFile]);

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const handleRemove = () => {
    setPreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const label = imageType === 'seatmap' ? 'Seatmap Image' : 'Reference Photo';
  const description = imageType === 'seatmap'
    ? 'Upload a PNG/JPG seatmap to extract sections'
    : 'Upload a reference photo for IP-Adapter style transfer';

  return (
    <div className={className}>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        {label}
      </label>

      {preview ? (
        // Preview mode
        <div className="relative">
          <div className="relative aspect-video bg-gray-100 dark:bg-gray-800 rounded-lg overflow-hidden">
            <img
              src={preview}
              alt={label}
              className="w-full h-full object-contain"
            />
            {uploadMutation.isPending && (
              <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                <div className="text-white text-center">
                  <div className="w-8 h-8 border-2 border-white border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                  <div className="text-sm">Uploading...</div>
                </div>
              </div>
            )}
          </div>
          <div className="mt-2 flex justify-between items-center">
            <span className="text-sm text-green-600 dark:text-green-400">
              {uploadMutation.isSuccess ? 'Uploaded' : uploadMutation.isPending ? 'Uploading...' : 'Ready to upload'}
            </span>
            <button
              onClick={handleRemove}
              disabled={uploadMutation.isPending}
              className="text-sm text-red-600 hover:text-red-700 disabled:opacity-50"
            >
              Remove
            </button>
          </div>
        </div>
      ) : (
        // Upload mode
        <div
          onClick={handleClick}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`
            border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
            ${isDragging
              ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
              : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500'
            }
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileInput}
            className="hidden"
          />
          <div className="space-y-2">
            <div className="text-4xl">
              {imageType === 'seatmap' ? '🗺️' : '📷'}
            </div>
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {isDragging ? 'Drop image here' : 'Click or drag to upload'}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {description}
            </div>
            <div className="text-xs text-gray-400 dark:text-gray-500">
              PNG, JPG up to 10MB
            </div>
          </div>
        </div>
      )}

      {uploadMutation.error && (
        <div className="mt-2 text-sm text-red-500">
          Upload failed: {(uploadMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}
