'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listDecks, listProviders, startAudit, listAuditResults, getAuditSummary } from '@/lib/api';
import { cn, scoreColor, scoreLabel, formatDate } from '@/lib/utils';
import { Loader2, ShieldCheck } from 'lucide-react';
import Link from 'next/link';

const SCORE_FILTERS = [
  { value: '', label: 'All' },
  { value: 'wrong', label: 'Wrong' },
  { value: 'likely_inaccurate', label: 'Likely Inaccurate' },
  { value: 'possibly_inaccurate', label: 'Possibly Inaccurate' },
  { value: 'probably_accurate', label: 'Probably Accurate' },
  { value: 'accurate', label: 'Accurate' },
];

export default function AuditPage() {
  const qc = useQueryClient();
  const [deckName, setDeckName] = useState('');
  const [providerId, setProviderId] = useState<number | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [scoreFilter, setScoreFilter] = useState('');

  const decksQuery = useQuery({ queryKey: ['decks'], queryFn: listDecks });
  const providersQuery = useQuery({ queryKey: ['providers'], queryFn: listProviders });

  const resultsQuery = useQuery({
    queryKey: ['audit-results', activeJobId, scoreFilter],
    queryFn: () => listAuditResults({ job_id: activeJobId ?? undefined, score: scoreFilter || undefined, limit: 100 }),
    enabled: true,
  });

  const summaryQuery = useQuery({
    queryKey: ['audit-summary', activeJobId],
    queryFn: () => getAuditSummary(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: activeJobId ? 5000 : false,
  });

  const startMutation = useMutation({
    mutationFn: startAudit,
    onSuccess: (data) => {
      setActiveJobId(data.job_id);
      qc.invalidateQueries({ queryKey: ['audit-results'] });
    },
  });

  const handleStart = (e: React.FormEvent) => {
    e.preventDefault();
    if (!deckName || !providerId) return;
    startMutation.mutate({ deck_name: deckName, provider_profile_id: providerId });
  };

  const summary = summaryQuery.data;

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Deck Audit</h2>
      <p className="text-sm text-gray-500 mb-6">
        Evaluate cards for factual accuracy without generating rewrites.
        This is a separate function from variant fidelity validation.
      </p>

      {/* Launch form */}
      <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
        <h3 className="font-semibold text-gray-800 mb-4">Start Audit</h3>
        <form onSubmit={handleStart} className="flex items-end gap-3 flex-wrap">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Deck</label>
            <select
              value={deckName}
              onChange={e => setDeckName(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 min-w-48"
            >
              <option value="">— Select a deck —</option>
              {decksQuery.data?.map(d => (
                <option key={d.name} value={d.name}>{d.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
            <select
              value={providerId ?? ''}
              onChange={e => setProviderId(Number(e.target.value))}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 min-w-48"
            >
              <option value="">— Select provider —</option>
              {providersQuery.data?.map(p => (
                <option key={p.id} value={p.id}>{p.name} ({p.model})</option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={startMutation.isPending || !deckName || !providerId}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {startMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ShieldCheck className="h-4 w-4" />
            )}
            Run Audit
          </button>
        </form>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
          {[
            { key: 'accurate', label: 'Accurate', val: summary.accurate },
            { key: 'probably_accurate', label: 'Probably OK', val: summary.probably_accurate },
            { key: 'possibly_inaccurate', label: 'Possibly Wrong', val: summary.possibly_inaccurate },
            { key: 'likely_inaccurate', label: 'Likely Wrong', val: summary.likely_inaccurate },
            { key: 'wrong', label: 'Wrong', val: summary.wrong },
          ].map(({ key, label, val }) => (
            <div
              key={key}
              onClick={() => setScoreFilter(scoreFilter === key ? '' : key)}
              className={cn(
                'bg-white border rounded-lg p-3 text-center cursor-pointer transition-all',
                scoreFilter === key ? 'border-blue-500 shadow-sm' : 'border-gray-200 hover:border-gray-300'
              )}
            >
              <div className={cn('text-2xl font-bold', scoreColor(key).split(' ')[0])}>
                {val}
              </div>
              <div className="text-xs text-gray-500 mt-0.5">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-2 mb-4">
        {SCORE_FILTERS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setScoreFilter(value)}
            className={cn(
              'text-xs px-3 py-1.5 rounded-full border transition-colors',
              scoreFilter === value
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Results */}
      {resultsQuery.isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 text-gray-400 animate-spin" />
        </div>
      )}

      {resultsQuery.data?.length === 0 && !resultsQuery.isLoading && (
        <div className="text-center py-12 text-gray-400">
          <ShieldCheck className="h-10 w-10 mx-auto mb-2 opacity-30" />
          <p>No audit results yet. Start an audit above.</p>
        </div>
      )}

      <div className="space-y-2">
        {resultsQuery.data?.map(result => (
          <div key={result.id} className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-gray-400">Note #{result.note_id}</span>
                  {result.model_name && (
                    <span className="text-xs text-gray-500">{result.model_name}</span>
                  )}
                </div>
                {result.rationale && (
                  <p className="text-sm text-gray-700">{result.rationale}</p>
                )}
                {result.category_tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {result.category_tags.map(tag => (
                      <span
                        key={tag}
                        className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full"
                      >
                        {tag.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="shrink-0">
                <span className={cn('text-xs px-2 py-1 rounded-full font-medium', scoreColor(result.overall_score))}>
                  {scoreLabel(result.overall_score)}
                </span>
              </div>
            </div>
            <div className="text-xs text-gray-400 mt-2">{formatDate(result.created_at)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
