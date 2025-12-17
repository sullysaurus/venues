'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { venuesApi, Venue } from '@/lib/api';

export default function VenuesPage() {
  const queryClient = useQueryClient();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newVenue, setNewVenue] = useState({ name: '', location: '' });
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['venues'],
    queryFn: () => venuesApi.list().then((res) => res.data),
  });

  const createMutation = useMutation({
    mutationFn: (data: { name: string; location?: string }) =>
      venuesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['venues'] });
      setShowCreateForm(false);
      setNewVenue({ name: '', location: '' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => venuesApi.delete(id),
    onMutate: async (id: string) => {
      setDeletingId(id);
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['venues'] });
      // Snapshot previous value
      const previousVenues = queryClient.getQueryData(['venues']);
      // Optimistically remove from list
      queryClient.setQueryData(['venues'], (old: { venues: Venue[] } | undefined) => ({
        venues: old?.venues.filter((v) => v.venue_id !== id) || [],
      }));
      return { previousVenues };
    },
    onError: (_err, _id, context) => {
      // Roll back on error
      if (context?.previousVenues) {
        queryClient.setQueryData(['venues'], context.previousVenues);
      }
    },
    onSettled: () => {
      setDeletingId(null);
      queryClient.invalidateQueries({ queryKey: ['venues'] });
    },
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (newVenue.name) {
      createMutation.mutate({
        name: newVenue.name,
        location: newVenue.location || undefined,
      });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Venues
        </h1>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
        >
          {showCreateForm ? 'Cancel' : 'Create Venue'}
        </button>
      </div>

      {/* Create Form */}
      {showCreateForm && (
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
            Create New Venue
          </h2>
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Name *
              </label>
              <input
                type="text"
                value={newVenue.name}
                onChange={(e) =>
                  setNewVenue({ ...newVenue, name: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                         bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                placeholder="Madison Square Garden"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Location
              </label>
              <input
                type="text"
                value={newVenue.location}
                onChange={(e) =>
                  setNewVenue({ ...newVenue, location: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                         bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                placeholder="New York, NY"
              />
            </div>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {createMutation.isPending ? 'Creating...' : 'Create Venue'}
            </button>
          </form>
        </div>
      )}

      {/* Venue List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        {isLoading ? (
          <div className="p-6 text-center text-gray-500">Loading venues...</div>
        ) : error ? (
          <div className="p-6 text-center">
            <p className="text-red-500 mb-2">Error loading venues</p>
            <p className="text-sm text-gray-500">
              API: {process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              {(error as Error).message}
            </p>
          </div>
        ) : data?.venues.length === 0 ? (
          <div className="p-6 text-center text-gray-500">
            No venues yet. Create one to get started.
          </div>
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {data?.venues.map((venue) => (
              <VenueRow
                key={venue.venue_id}
                venue={venue}
                onDelete={() => deleteMutation.mutate(venue.venue_id)}
                isDeleting={deletingId === venue.venue_id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function VenueRow({
  venue,
  onDelete,
  isDeleting,
}: {
  venue: Venue;
  onDelete: () => void;
  isDeleting: boolean;
}) {
  return (
    <div className="p-6 flex justify-between items-center hover:bg-gray-50 dark:hover:bg-gray-700">
      <Link href={`/venues/${venue.slug}`} className="flex-1">
        <div>
          <h3 className="font-medium text-gray-900 dark:text-white">
            {venue.name}
          </h3>
          <p className="text-sm text-gray-500">
            {venue.location && `${venue.location} • `}
            {venue.sections_count} sections • {venue.images_count} images
          </p>
        </div>
      </Link>
      <div className="flex items-center space-x-3">
        {venue.has_model && (
          <span className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">
            3D Ready
          </span>
        )}
        {venue.has_seatmap && (
          <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">
            Seatmap
          </span>
        )}
        <Link
          href={`/venues/${venue.slug}`}
          className="px-3 py-1 text-sm bg-purple-600 text-white rounded hover:bg-purple-700"
        >
          Open
        </Link>
        <button
          onClick={(e) => {
            e.preventDefault();
            if (confirm('Delete this venue?')) {
              onDelete();
            }
          }}
          disabled={isDeleting}
          className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700
                   disabled:opacity-50"
        >
          Delete
        </button>
      </div>
    </div>
  );
}
