'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'next/navigation';
import { listDecks, listProviders, createRewriteJob, listJobs } from '@/lib/api';
import { cn, statusColor, formatDate, progressPercent } from '@/lib/utils';
import { Loader2, Play, RefreshCw } from 'lucide-react';
import Link from 'next/link';

export default function RewritePage() {
  const searchParams = useSearchParams();
  const deckParam = searchParams.get('deck') ?? '';
  const qc = useQueryClient();

  const [deckName, setDeckName] = useState(deckParam);
  const [query, setQuery] = useState('');
  const [variantCount, setVariantCount] = useState(3);
  const [providerId, setProviderId] = useState<number | null>(null);
  const [validationEnabled, setValidationEnabled] = useState(true);
  const [approvalRequired, setApprovalRequired] = useState(true);

  const decksQuery = useQuery({ queryKey: ['decks'], queryFn: listDecks });
  const providersQuery = useQuery({ queryKey: ['providers'], queryFn: listProviders });
  const jobsQuery = useQuery({ queryKey: ['jobs'], queryFn: () => listJobs(), refetchInterval: 5000 });

  useEffect(() => {
    if (providersQuery.data?.length && !providerId) {
      setProviderId(providersQuery.data[0].id);
    }
  }, [providersQuery.data, providerId]);

  const createMutation = useMutation({
    mutationFn: createRewriteJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!providerId) return;
    createMutation.mutate({
      deck_name: deckName || undefined,
      query: query || undefined,
      variant_count: variantCount,
      provider_profile_id: providerId,
      validation_enabled: validationEnabled,
      approval_required: approvalRequired,
    });
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Rewrite Jobs</h2>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Create job form */}
        <div className="lg:col-span-2 bg-white border border-gray-200 rounded-lg p-5">
          <h3 className="font-semibold text-gray-800 mb-4">New Rewrite Job</h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Deck selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Deck</label>
              <select
                value={deckName}
                onChange={e => setDeckName(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">— Select a deck —</option>
                {decksQuery.data?.map(d => (
                  <option key={d.name} value={d.name}>{d.name} ({d.note_count})</option>
                ))}
              </select>
            </div>

            {/* Custom query */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Or custom query
              </label>
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder='e.g. "deck:MyDeck tag:anatomy"'
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Variant count */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Variants per card: <strong>{variantCount}</strong>
              </label>
              <input
                type="range"
                min={1}
                max={6}
                value={variantCount}
                onChange={e => setVariantCount(Number(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>1</span>
                <span>2 (mod+agg)</span>
                <span>3 (all styles)</span>
                <span>6</span>
              </div>
            </div>

            {/* Provider */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                LLM Provider
              </label>
              {providersQuery.data?.length === 0 ? (
                <p className="text-sm text-amber-600">
                  No providers configured.{' '}
                  <Link href="/settings" className="underline">Add one in Settings.</Link>
                </p>
              ) : (
                <select
                  value={providerId ?? ''}
                  onChange={e => setProviderId(Number(e.target.value))}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {providersQuery.data?.map(p => (
                    <option key={p.id} value={p.id}>{p.name} ({p.model})</option>
                  ))}
                </select>
              )}
            </div>

            {/* Toggles */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={validationEnabled}
                  onChange={e => setValidationEnabled(e.target.checked)}
                  className="rounded"
                />
                Enable fidelity validation
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={approvalRequired}
                  onChange={e => setApprovalRequired(e.target.checked)}
                  className="rounded"
                />
                Require manual approval before write-back
              </label>
            </div>

            <button
              type="submit"
              disabled={createMutation.isPending || (!deckName && !query) || !providerId}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {createMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Start Job
            </button>

            {createMutation.isError && (
              <p className="text-sm text-red-600">
                {String((createMutation.error as any)?.response?.data?.detail ?? 'Job creation failed')}
              </p>
            )}
          </form>
        </div>

        {/* Job list */}
        <div className="lg:col-span-3 bg-white border border-gray-200 rounded-lg">
          <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
            <h3 className="font-semibold text-gray-800">All Jobs</h3>
            <button
              onClick={() => qc.invalidateQueries({ queryKey: ['jobs'] })}
              className="text-gray-400 hover:text-gray-600"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
          {jobsQuery.isLoading && (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="h-6 w-6 text-gray-400 animate-spin" />
            </div>
          )}
          {jobsQuery.data?.length === 0 && (
            <div className="p-8 text-center text-sm text-gray-400">No jobs yet</div>
          )}
          <div className="divide-y divide-gray-100">
            {jobsQuery.data?.map(job => (
              <div key={job.id} className="px-5 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-800 truncate">
                      {job.deck_name || job.query || job.id.slice(0, 12) + '...'}
                    </div>
                    <div className="text-xs text-gray-500">{formatDate(job.created_at)}</div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
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
                      Review →
                    </Link>
                  </div>
                </div>
                {job.status === 'running' && job.total_notes > 0 && (
                  <div className="mt-2">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>{job.processed_notes}/{job.total_notes} notes</span>
                      <span>{progressPercent(job.processed_notes, job.total_notes)}%</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full transition-all"
                        style={{ width: `${progressPercent(job.processed_notes, job.total_notes)}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
