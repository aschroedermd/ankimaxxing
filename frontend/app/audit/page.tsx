'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  listDecks, 
  listProviders, 
  startAudit, 
  listAuditJobs, 
  getAuditJob,
  pauseAuditJob,
  resumeAuditJob,
  cancelAuditJob,
  getNoteDetail
} from '@/lib/api';
import { cn, scoreColor, scoreLabel, formatDate } from '@/lib/utils';
import { 
  Loader2, 
  ShieldCheck, 
  History, 
  Play, 
  Pause, 
  X, 
  ChevronRight, 
  ExternalLink,
  Search,
  AlertCircle
} from 'lucide-react';

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
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [scoreFilter, setScoreFilter] = useState('');
  const [viewingNoteId, setViewingNoteId] = useState<number | null>(null);

  // --- Queries ---

  const decksQuery = useQuery({ queryKey: ['decks'], queryFn: listDecks });
  const providersQuery = useQuery({ queryKey: ['providers'], queryFn: listProviders });
  
  const jobsQuery = useQuery({ 
    queryKey: ['audit-jobs'], 
    queryFn: listAuditJobs,
    refetchInterval: 10000 
  });

  const jobDetailQuery = useQuery({
    queryKey: ['audit-job-detail', selectedJobId],
    queryFn: () => getAuditJob(selectedJobId!),
    enabled: !!selectedJobId,
    refetchInterval: (query) => {
      const job = query.state.data;
      return (job?.status === 'running' || job?.status === 'pending') ? 3000 : false;
    }
  });

  const noteDetailQuery = useQuery({
    queryKey: ['note-detail', viewingNoteId],
    queryFn: () => getNoteDetail(viewingNoteId!),
    enabled: !!viewingNoteId
  });

  // --- Mutations ---

  const startMutation = useMutation({
    mutationFn: startAudit,
    onSuccess: (data) => {
      setSelectedJobId(data.job_id);
      qc.invalidateQueries({ queryKey: ['audit-jobs'] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: pauseAuditJob,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['audit-job-detail', selectedJobId] }),
  });

  const resumeMutation = useMutation({
    mutationFn: resumeAuditJob,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['audit-job-detail', selectedJobId] }),
  });

  const cancelMutation = useMutation({
    mutationFn: cancelAuditJob,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['audit-job-detail', selectedJobId] }),
  });

  // --- Handlers ---

  const handleStart = (e: React.FormEvent) => {
    e.preventDefault();
    if (!deckName || !providerId) return;
    startMutation.mutate({ deck_name: deckName, provider_profile_id: providerId });
  };

  const job = jobDetailQuery.data;
  const filteredResults = job?.results.filter(r => !scoreFilter || r.overall_score === scoreFilter);

  return (
    <div className="p-8 max-w-7xl mx-auto flex gap-8 h-[calc(100vh-64px)] overflow-hidden">
      {/* Sidebar: Job History */}
      <div className="w-80 flex flex-col shrink-0 border-r border-gray-200 pr-6">
        <h2 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-2">
          <History className="h-5 w-5 text-gray-400" />
          Audit History
        </h2>

        <div className="flex-1 overflow-y-auto space-y-3 pb-6">
          {jobsQuery.data?.map(j => (
            <button
              key={j.id}
              onClick={() => setSelectedJobId(j.id)}
              className={cn(
                'w-full text-left p-3 rounded-lg border transition-all text-sm group',
                selectedJobId === j.id
                  ? 'bg-blue-50 border-blue-200 ring-1 ring-blue-100'
                  : 'bg-white border-gray-100 hover:border-gray-300'
              )}
            >
              <div className="flex justify-between items-start mb-1">
                <span className="font-semibold text-gray-800 truncate">
                  {j.deck_name || 'Custom Query'}
                </span>
                <span className={cn(
                  'text-[10px] px-1.5 py-0.5 rounded uppercase font-bold tracking-tight',
                  j.status === 'complete' ? 'bg-green-100 text-green-700' :
                  j.status === 'running' ? 'bg-blue-100 text-blue-700' :
                  j.status === 'paused' ? 'bg-amber-100 text-amber-700' :
                  'bg-gray-100 text-gray-600'
                )}>
                  {j.status}
                </span>
              </div>
              <div className="text-xs text-gray-500 mb-2">{formatDate(j.created_at)}</div>
              {j.total_notes > 0 && (
                <div className="w-full bg-gray-100 h-1 rounded-full overflow-hidden">
                  <div 
                    className="bg-blue-500 h-full transition-all" 
                    style={{ width: `${(j.processed_notes / j.total_notes) * 100}%` }} 
                  />
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header / New Audit toggle */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {job ? (job.deck_name || 'Query Audit') : 'Deck Audit'}
            </h1>
            {job && <span className="text-xs text-gray-400 font-mono uppercase">{job.id}</span>}
          </div>
          <button
            onClick={() => setSelectedJobId(null)}
            className="text-sm font-medium text-blue-600 hover:text-blue-800 flex items-center gap-1"
          >
            <ShieldCheck className="h-4 w-4" />
            New Audit
          </button>
        </div>

        {!selectedJobId ? (
          /* Create New Audit View */
          <div className="bg-white border border-gray-200 rounded-xl p-8 shadow-sm max-w-2xl mx-auto mt-12">
            <h3 className="text-lg font-semibold text-gray-900 mb-6">Evaluate Card Accuracy</h3>
            <form onSubmit={handleStart} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Select Deck</label>
                <select
                  value={deckName}
                  onChange={e => setDeckName(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-blue-500 bg-gray-50/50"
                >
                  <option value="">— Choose a deck —</option>
                  {decksQuery.data?.map(d => (
                    <option key={d.name} value={d.name}>{d.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Audit Provider (AI Model)</label>
                <select
                  value={providerId ?? ''}
                  onChange={e => setProviderId(Number(e.target.value))}
                  className="w-full border border-gray-200 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-blue-500 bg-gray-50/50"
                >
                  <option value="">— Choose an AI —</option>
                  {providersQuery.data?.map(p => (
                    <option key={p.id} value={p.id}>{p.name} ({p.model})</option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                disabled={startMutation.isPending || !deckName || !providerId}
                className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white py-4 rounded-xl font-bold hover:bg-blue-700 transition-colors disabled:opacity-50 shadow-lg shadow-blue-500/20"
              >
                {startMutation.isPending ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <ShieldCheck className="h-5 w-5" />
                )}
                Start Mission
              </button>
            </form>
          </div>
        ) : (
          /* Job View */
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            {/* Control Bar */}
            <div className="flex items-center gap-4 bg-gray-50 border border-gray-200 rounded-xl p-4 mb-6 shrink-0">
               <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="font-semibold text-gray-900">Job Progress</span>
                    <span className="text-xs text-gray-500">{job?.processed_notes} / {job?.total_notes} cards</span>
                  </div>
                  <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                    <div 
                      className="bg-blue-500 h-full transition-all duration-700" 
                      style={{ width: `${((job?.processed_notes ?? 0) / (job?.total_notes || 1)) * 100}%` }} 
                    />
                  </div>
               </div>

               <div className="flex items-center gap-2 border-l border-gray-200 pl-4">
                  {job?.status === 'running' && (
                    <button 
                      onClick={() => pauseMutation.mutate(job.id)}
                      className="p-2 text-amber-600 hover:bg-amber-100 rounded-lg transition-colors"
                      title="Pause"
                    >
                      <Pause className="h-5 w-5 fill-current" />
                    </button>
                  )}
                  {job?.status === 'paused' && (
                    <button 
                      onClick={() => resumeMutation.mutate(job.id)}
                      className="p-2 text-green-600 hover:bg-green-100 rounded-lg transition-colors"
                      title="Resume"
                    >
                      <Play className="h-5 w-5 fill-current" />
                    </button>
                  )}
                  {(job?.status === 'running' || job?.status === 'paused') && (
                    <button 
                      onClick={() => cancelMutation.mutate(job.id)}
                      className="p-2 text-red-600 hover:bg-red-100 rounded-lg transition-colors"
                      title="Stop"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  )}
               </div>
            </div>

            {/* Filter Ribbons */}
            <div className="flex flex-wrap items-center gap-2 mb-6 shrink-0">
              {SCORE_FILTERS.map(f => (
                <button
                  key={f.value}
                  onClick={() => setScoreFilter(f.value)}
                  className={cn(
                    'text-xs px-4 py-2 rounded-full border transition-all font-medium',
                    scoreFilter === f.value
                      ? 'bg-blue-600 text-white border-blue-600 shadow-md transform scale-105'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                  )}
                >
                  {f.label}
                  {job?.results && f.value && (
                    <span className="ml-2 opacity-60">
                      ({job.results.filter(r => r.overall_score === f.value).length})
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Results Grid */}
            <div className="flex-1 overflow-y-auto pr-2 space-y-4 pb-8">
              {filteredResults?.map(result => (
                <div key={result.id} className="group bg-white border border-gray-200 rounded-xl p-5 hover:border-blue-300 hover:shadow-md transition-all">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2">
                        <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider', scoreColor(result.overall_score))}>
                          {scoreLabel(result.overall_score)}
                        </span>
                        <span className="text-xs text-gray-400 font-mono">#{result.note_id}</span>
                        <span className="text-xs text-gray-500 font-medium truncate">{result.model_name}</span>
                      </div>
                      <p className="text-sm font-medium text-gray-800 leading-relaxed mb-3">
                        {result.rationale}
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {result.category_tags.map(tag => (
                          <span key={tag} className="text-[10px] bg-gray-50 text-gray-500 px-2 py-0.5 border border-gray-100 rounded uppercase font-bold">
                            {tag.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    </div>
                    
                    <button 
                      onClick={() => setViewingNoteId(result.note_id)}
                      className="shrink-0 flex items-center gap-1.5 text-xs text-blue-600 hover:bg-blue-50 px-3 py-2 rounded-lg transition-colors font-semibold"
                    >
                      Inspect Card
                      <ExternalLink className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              ))}
              
              {filteredResults?.length === 0 && (
                <div className="flex flex-col items-center justify-center py-24 text-gray-300">
                  <Search className="h-10 w-10 mb-4 opacity-20" />
                  <p className="text-sm font-medium">No results matching this filter.</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Note Detail Modal */}
      {viewingNoteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl w-full max-w-2xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
               <div>
                  <h3 className="text-lg font-bold text-gray-900">Card Inspector</h3>
                  <p className="text-xs text-gray-500 font-mono">Note ID: {viewingNoteId}</p>
               </div>
               <button onClick={() => setViewingNoteId(null)} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
                  <X className="h-5 w-5 text-gray-500" />
               </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {noteDetailQuery.isLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
                </div>
              ) : noteDetailQuery.data ? (
                <>
                  <div className="space-y-4">
                    <h4 className="text-sm font-bold text-gray-400 uppercase tracking-widest border-b pb-2">Anki Fields</h4>
                    {Object.entries(noteDetailQuery.data.fields).map(([name, value]) => (
                      <div key={name} className="space-y-1">
                        <label className="text-[10px] font-bold text-gray-400 uppercase ml-1">{name}</label>
                        <div 
                          className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-sm text-gray-800 prose prose-sm max-w-full"
                          dangerouslySetInnerHTML={{ __html: value }}
                        />
                      </div>
                    ))}
                  </div>

                  <div className="space-y-3">
                    <h4 className="text-sm font-bold text-gray-400 uppercase tracking-widest border-b pb-2">Metadata</h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-blue-50 rounded-lg p-3">
                        <div className="text-[10px] font-bold text-blue-400 uppercase mb-1">Model</div>
                        <div className="text-sm font-semibold text-blue-900">{noteDetailQuery.data.model_name}</div>
                      </div>
                      <div className="bg-purple-50 rounded-lg p-3">
                        <div className="text-[10px] font-bold text-purple-400 uppercase mb-1">Tags</div>
                        <div className="flex flex-wrap gap-1">
                           {noteDetailQuery.data.tags.map(t => (
                             <span key={t} className="text-[10px] font-bold text-purple-700 bg-purple-200/50 px-1.5 py-0.5 rounded">{t}</span>
                           ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-amber-600 bg-amber-50 rounded-xl">
                  <AlertCircle className="h-10 w-10 mb-2" />
                  <p className="font-semibold text-sm">Failed to load note from Anki.</p>
                  <p className="text-xs opacity-70">Make sure Anki is open and AnkiConnect is active.</p>
                </div>
              )}
            </div>

            <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex justify-end">
              <button 
                onClick={() => setViewingNoteId(null)}
                className="bg-gray-900 text-white px-6 py-2 rounded-xl text-sm font-bold hover:bg-black transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
