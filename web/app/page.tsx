'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { venuesApi } from '@/lib/api';

export default function Home() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['venues'],
    queryFn: () => venuesApi.list().then((res) => res.data),
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Dashboard
        </h1>
        <Link
          href="/venues"
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
        >
          View All Venues
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Total Venues
          </h3>
          <p className="text-3xl font-bold text-gray-900 dark:text-white">
            {data?.total || 0}
          </p>
        </div>
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Total Images
          </h3>
          <p className="text-3xl font-bold text-gray-900 dark:text-white">
            {data?.venues.reduce((sum, v) => sum + v.images_count, 0) || 0}
          </p>
        </div>
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Ready Venues
          </h3>
          <p className="text-3xl font-bold text-gray-900 dark:text-white">
            {data?.venues.filter((v) => v.has_model).length || 0}
          </p>
        </div>
      </div>

      {/* Recent Venues */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Recent Venues
          </h2>
        </div>
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
          {isLoading ? (
            <div className="p-6 text-center text-gray-500">Loading...</div>
          ) : error ? (
            <div className="p-6 text-center text-red-500">
              Error loading venues. Make sure the API is running.
            </div>
          ) : data?.venues.length === 0 ? (
            <div className="p-6 text-center text-gray-500">
              No venues yet.{' '}
              <Link href="/venues" className="text-blue-600 hover:underline">
                Create one
              </Link>
            </div>
          ) : (
            data?.venues.slice(0, 5).map((venue) => (
              <Link
                key={venue.venue_id}
                href={`/venues/${venue.venue_id}`}
                className="block p-6 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-medium text-gray-900 dark:text-white">
                      {venue.name}
                    </h3>
                    <p className="text-sm text-gray-500">
                      {venue.sections_count} sections • {venue.images_count} images
                    </p>
                  </div>
                  <div className="flex items-center space-x-2">
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
                  </div>
                </div>
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
