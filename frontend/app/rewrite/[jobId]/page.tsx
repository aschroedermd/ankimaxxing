'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import {
  getJob,
  listJobNotes,
  approveNoteRewrite,
  rejectNoteRewrite,
  writeBackAll,
  cancelJob,
} from '@/lib/api';
import type { NoteRewrite, RewriteVariant } from '@/lib/api';
import { cn, statusColor, scoreColor, scoreLabel, formatDate, progressPercent } from '@/lib/utils';
import { Loader2, Check, X, Upload, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';

export default function JobReviewPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<string>('');
  const [expandedNote, setExpandedNote] = useState<number | null>(null);

  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    refetchInterval: (q) => q.state.data?.status === 'running' ? 3000 : false,
  });

  const notesQuery = useQuery({
    queryKey: ['job-notes', jobId, filter],
    queryFn: () => listJobNotes(jobId, { status: filter || undefined, limit: 100 }),
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, writeBack }: { id: number; writeBack: boolean }) =>
      approveNoteRewrite(id, [], writeBack),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['job-notes', jobId] }),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: number) => rejectNoteRewrite(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['job-notes', jobId] }),
  });

  const writeBackMutation = useMutation({
    mutationFn: () => writeBackAll(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['job-notes', jobId] }),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelJob(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['job', jobId] }),
  });

  const job = jobQuery.data;
  const notes = notesQuery.data ?? [];

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            {job?.deck_name || job?.query || 'Rewrite Job'}
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Job ID: {jobId.slice(0, 12)}...
          </p>
        </div>
        <div className="flex items-center gap-2">
          {job?.status === 'running' && (
            <button
              onClick={() => cancelMutation.mutate()}
              className="text-sm border border-gray-300 px-3 py-1.5 rounded-md text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
          )}
          {job?.status === 'complete' && (
            <button
              onClick={() => writeBackMutation.mutate()}
              disabled={writeBackMutation.isPending}
              className="flex items-center gap-1.5 text-sm bg-purple-600 text-white px-3 py-1.5 rounded-md hover:bg-purple-700 disabled:opacity-50"
            >
              {writeBackMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Upload className="h-3.5 w-3.5" />
              )}
              Write Back All Approved
            </button>
          )}
        </div>
      </div>

      {/* Job stats */}
      {job && (
        <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-gray-500">Status</div>
              <span className={cn('text-sm px-2 py-0.5 rounded-full font-medium', statusColor(job.status))}>
                {job.status}
              </span>
            </div>
            <div>
              <div className="text-xs text-gray-500">Progress</div>
              <div className="text-sm font-medium text-gray-800">
                {job.processed_notes}/{job.total_notes} notes
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Variants per card</div>
              <div className="text-sm font-medium text-gray-800">{job.variant_count}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Created</div>
              <div className="text-sm text-gray-600">{formatDate(job.created_at)}</div>
            </div>
          </div>
          {job.status === 'running' && job.total_notes > 0 && (
            <div className="mt-3">
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all"
                  style={{ width: `${progressPercent(job.processed_notes, job.total_notes)}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-2 mb-4">
        {['', 'pending', 'approved', 'rejected', 'written_back'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={cn(
              'text-xs px-3 py-1.5 rounded-full border transition-colors',
              filter === s
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
            )}
          >
            {s || 'All'}
          </button>
        ))}
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ['job-notes', jobId] })}
          className="ml-auto text-gray-400 hover:text-gray-600"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {/* Notes list */}
      {notesQuery.isLoading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-gray-400 animate-spin" />
        </div>
      )}

      {notes.length === 0 && !notesQuery.isLoading && (
        <div className="text-center py-16 text-gray-400">
          <p>No notes found. The job may still be running.</p>
        </div>
      )}

      <div className="space-y-3">
        {notes.map(note => (
          <NoteRewriteCard
            key={note.id}
            note={note}
            expanded={expandedNote === note.id}
            onToggle={() => setExpandedNote(expandedNote === note.id ? null : note.id)}
            onApprove={(writeBack) => approveMutation.mutate({ id: note.id, writeBack })}
            onReject={() => rejectMutation.mutate(note.id)}
            isApproving={approveMutation.isPending}
            isRejecting={rejectMutation.isPending}
          />
        ))}
      </div>
    </div>
  );
}


function NoteRewriteCard({
  note,
  expanded,
  onToggle,
  onApprove,
  onReject,
  isApproving,
  isRejecting,
}: {
  note: NoteRewrite;
  expanded: boolean;
  onToggle: () => void;
  onApprove: (writeBack: boolean) => void;
  onReject: () => void;
  isApproving: boolean;
  isRejecting: boolean;
}) {
  const validVariants = note.variants.filter(v => !v.error);
  const worstRating = validVariants.reduce((worst, v) => {
    const order = ['accurate', 'probably_accurate', 'possibly_inaccurate', 'likely_inaccurate', 'wrong'];
    const vRating = v.validation?.rating ?? 'accurate';
    return order.indexOf(vRating) > order.indexOf(worst) ? vRating : worst;
  }, 'accurate');

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full text-left px-5 py-3 flex items-center justify-between hover:bg-gray-50"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-xs text-gray-400 shrink-0">#{note.note_id}</span>
          <span className="text-sm text-gray-700 truncate">{note.model_name}</span>
          <span className="text-xs text-gray-400 shrink-0">{note.template_name}</span>
          {note.variants.length > 0 && (
            <span
              className={cn(
                'text-xs px-1.5 py-0.5 rounded font-medium shrink-0',
                scoreColor(worstRating)
              )}
            >
              {scoreLabel(worstRating)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', statusColor(note.status))}>
            {note.status}
          </span>
          {expanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 p-5">
          {/* Original */}
          <div className="mb-4">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Original Prompt ({note.prompt_field})
            </div>
            <div
              className="text-sm text-gray-800 bg-gray-50 rounded p-3 border border-gray-100"
              dangerouslySetInnerHTML={{ __html: note.original_prompt }}
            />
          </div>
          <div className="mb-5">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Answer ({note.answer_field})
            </div>
            <div
              className="text-sm text-gray-600 bg-gray-50 rounded p-3 border border-gray-100"
              dangerouslySetInnerHTML={{ __html: note.original_answer }}
            />
          </div>

          {/* Variants */}
          <div className="space-y-3 mb-4">
            {note.variants.map((variant, i) => (
              <VariantCard key={variant.id} variant={variant} index={i} />
            ))}
          </div>

          {/* Actions */}
          {note.status === 'pending' && (
            <div className="flex items-center gap-2 pt-3 border-t border-gray-100">
              <button
                onClick={() => onApprove(false)}
                disabled={isApproving}
                className="flex items-center gap-1.5 text-sm bg-green-600 text-white px-3 py-1.5 rounded-md hover:bg-green-700 disabled:opacity-50"
              >
                <Check className="h-3.5 w-3.5" /> Approve
              </button>
              <button
                onClick={() => onApprove(true)}
                disabled={isApproving}
                className="flex items-center gap-1.5 text-sm bg-purple-600 text-white px-3 py-1.5 rounded-md hover:bg-purple-700 disabled:opacity-50"
              >
                <Upload className="h-3.5 w-3.5" /> Approve &amp; Write Back
              </button>
              <button
                onClick={onReject}
                disabled={isRejecting}
                className="flex items-center gap-1.5 text-sm border border-red-300 text-red-600 px-3 py-1.5 rounded-md hover:bg-red-50 disabled:opacity-50"
              >
                <X className="h-3.5 w-3.5" /> Reject
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function VariantCard({ variant, index }: { variant: RewriteVariant; index: number }) {
  const styleColors: Record<string, string> = {
    conservative: 'bg-sky-50 border-sky-200 text-sky-700',
    moderate: 'bg-violet-50 border-violet-200 text-violet-700',
    aggressive: 'bg-orange-50 border-orange-200 text-orange-700',
  };
  const colorClass = styleColors[variant.style] ?? 'bg-gray-50 border-gray-200 text-gray-700';

  return (
    <div className={cn('border rounded-lg p-3', colorClass)}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wide">{variant.style}</span>
        {variant.validation && (
          <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', scoreColor(variant.validation.rating))}>
            {scoreLabel(variant.validation.rating)}
          </span>
        )}
      </div>
      {variant.error ? (
        <p className="text-xs text-red-600">Error: {variant.error}</p>
      ) : (
        <p className="text-sm text-gray-800">{variant.text_plain}</p>
      )}
      {variant.validation?.rationale && (
        <p className="text-xs text-gray-500 mt-2 italic">{variant.validation.rationale}</p>
      )}
      {variant.warnings.length > 0 && (
        <div className="mt-2">
          {variant.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-600">⚠ {w}</p>
          ))}
        </div>
      )}
    </div>
  );
}
