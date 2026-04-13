'use client';

import { useQuery } from '@tanstack/react-query';
import { pingAnki, listJobs, listDecks } from '@/lib/api';
import { cn, statusColor, formatDate, progressPercent } from '@/lib/utils';
import { CheckCircle, XCircle, Loader2, RefreshCw, Layers } from 'lucide-react';
import Link from 'next/link';

export default function Dashboard() {
  const ankiQuery = useQuery({
    queryKey: ['anki-ping'],
    queryFn: pingAnki,
    retry: false,
    refetchInterval: 15_000,
  });

  const jobsQuery = useQuery({
    queryKey: ['jobs'],
    queryFn: () => listJobs(),
  });

  const decksQuery = useQuery({
    queryKey: ['decks'],
    queryFn: listDecks,
    enabled: !!ankiQuery.data,
  });

  const isAnkiOk = !!ankiQuery.data && !ankiQuery.isError;

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Dashboard</h2>

      {/* Status cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        {/* Anki status */}
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-2">
            {ankiQuery.isLoading ? (
              <Loader2 className="h-5 w-5 text-gray-400 animate-spin" />
            ) : isAnkiOk ? (
              <CheckCircle className="h-5 w-5 text-green-500" />
            ) : (
              <XCircle className="h-5 w-5 text-red-500" />
            )}
            <span className="font-semibold text-gray-800">AnkiConnect</span>
          </div>
          <p className="text-sm text-gray-500">
            {ankiQuery.isLoading
              ? 'Checking...'
              : isAnkiOk
              ? `Connected (API v${ankiQuery.data?.anki_connect_version ?? '?'})`
              : 'Not reachable — open Anki with AnkiConnect installed'}
          </p>
        </div>

        {/* Deck count */}
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-2">
            <Layers className="h-5 w-5 text-blue-500" />
            <span className="font-semibold text-gray-800">Decks</span>
          </div>
          <p className="text-sm text-gray-500">
            {decksQuery.isLoading
              ? 'Loading...'
              : decksQuery.data
              ? `${decksQuery.data.length} deck${decksQuery.data.length !== 1 ? 's' : ''} available`
              : 'Connect Anki to see decks'}
          </p>
        </div>

        {/* Recent jobs */}
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-2">
            <RefreshCw className="h-5 w-5 text-purple-500" />
            <span className="font-semibold text-gray-800">Jobs</span>
          </div>
          <p className="text-sm text-gray-500">
            {jobsQuery.data
              ? `${jobsQuery.data.length} rewrite job${jobsQuery.data.length !== 1 ? 's' : ''}`
              : 'No jobs yet'}
          </p>
        </div>
      </div>

      {/* AnkiConnect setup guide (shown when not connected) */}
      {!isAnkiOk && !ankiQuery.isLoading && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-5 mb-8">
          <h3 className="font-semibold text-amber-800 mb-2">Getting Started</h3>
          <ol className="text-sm text-amber-700 space-y-1 list-decimal list-inside">
            <li>Open Anki on your desktop</li>
            <li>Go to Tools → Add-ons → Browse &amp; Install</li>
            <li>Install add-on code: <code className="font-mono bg-amber-100 px-1 rounded">2055492159</code></li>
            <li>Restart Anki</li>
            <li>This app will connect automatically</li>
          </ol>
        </div>
      )}

      {/* Recent jobs table */}
      {jobsQuery.data && jobsQuery.data.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
            <h3 className="font-semibold text-gray-800">Recent Rewrite Jobs</h3>
            <Link href="/rewrite" className="text-sm text-blue-600 hover:text-blue-800">
              View all
            </Link>
          </div>
          <div className="divide-y divide-gray-100">
            {jobsQuery.data.slice(0, 5).map(job => (
              <div key={job.id} className="px-5 py-3 flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-gray-800">
                    {job.deck_name || job.query || job.id.slice(0, 8)}
                  </div>
                  <div className="text-xs text-gray-500">{formatDate(job.created_at)}</div>
                </div>
                <div className="flex items-center gap-3">
                  {job.status === 'running' && (
                    <span className="text-xs text-gray-500">
                      {job.processed_notes}/{job.total_notes}
                    </span>
                  )}
                  <span
                    className={cn(
                      'text-xs px-2 py-0.5 rounded-full font-medium',
                      statusColor(job.status)
                    )}
                  >
                    {job.status}
                  </span>
                  <Link
                    href={`/rewrite/${job.id}`}
                    className="text-xs text-blue-600 hover:text-blue-800"
                  >
                    Review
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
