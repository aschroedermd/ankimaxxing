'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listNoteTypes, getPatchPlan, applyPatch, listPatches, rollbackPatch } from '@/lib/api';
import { cn, supportLevelColor } from '@/lib/utils';
import { Loader2, Wrench, RotateCcw, Eye, CheckCircle } from 'lucide-react';

export default function TemplatesPage() {
  const qc = useQueryClient();
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);

  const noteTypesQuery = useQuery({ queryKey: ['note-types'], queryFn: listNoteTypes });
  const patchesQuery = useQuery({ queryKey: ['patches'], queryFn: listPatches });

  const planQuery = useQuery({
    queryKey: ['patch-plan', selectedModel],
    queryFn: () => getPatchPlan(selectedModel!),
    enabled: !!selectedModel,
  });

  const applyMutation = useMutation({
    mutationFn: (modelName: string) => applyPatch(modelName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patches'] });
      qc.invalidateQueries({ queryKey: ['note-types'] });
      qc.invalidateQueries({ queryKey: ['patch-plan'] });
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: (patchId: number) => rollbackPatch(patchId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patches'] });
    },
  });

  const plan = planQuery.data;
  const patches = (patchesQuery.data ?? []) as any[];

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Template Management</h2>
      <p className="text-sm text-gray-500 mb-6">
        Clone and patch note types to inject the AI Rewriter JavaScript.
        Original templates are preserved for rollback. A human review diff is shown before applying.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Note type list */}
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-200">
            <h3 className="font-semibold text-gray-800">Note Types</h3>
          </div>
          {noteTypesQuery.isLoading && (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            </div>
          )}
          <div className="divide-y divide-gray-100 max-h-[60vh] overflow-auto">
            {noteTypesQuery.data?.map(nt => (
              <button
                key={nt.model_name}
                onClick={() => { setSelectedModel(nt.model_name); setShowDiff(false); }}
                className={cn(
                  'w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors',
                  selectedModel === nt.model_name && 'bg-blue-50'
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-gray-800 truncate">
                    {nt.model_name}
                  </span>
                  <span className={cn('text-xs px-1.5 py-0.5 rounded shrink-0', supportLevelColor(nt.support_level))}>
                    {nt.support_level.replace('_', ' ')}
                  </span>
                </div>
                {nt.is_app_managed && (
                  <div className="text-xs text-purple-600 mt-0.5 flex items-center gap-1">
                    <CheckCircle className="h-3 w-3" /> App-managed
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Patch plan + apply */}
        <div className="lg:col-span-2 space-y-4">
          {!selectedModel && (
            <div className="bg-white border border-gray-200 rounded-lg flex items-center justify-center h-48 text-gray-400">
              <p className="text-sm">Select a note type to preview patch plan</p>
            </div>
          )}

          {selectedModel && planQuery.isLoading && (
            <div className="bg-white border border-gray-200 rounded-lg flex items-center justify-center h-48">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          )}

          {plan && !planQuery.isLoading && (
            <div className="bg-white border border-gray-200 rounded-lg p-5">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="font-semibold text-gray-800">Patch Plan</h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {plan.original_model_name} → {plan.patched_model_name}
                  </p>
                </div>
                {plan.already_patched ? (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full font-medium">
                    Already patched
                  </span>
                ) : (
                  <button
                    onClick={() => applyMutation.mutate(selectedModel)}
                    disabled={applyMutation.isPending}
                    className="flex items-center gap-1.5 text-sm bg-blue-600 text-white px-3 py-1.5 rounded-md hover:bg-blue-700 disabled:opacity-50"
                  >
                    {applyMutation.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Wrench className="h-3.5 w-3.5" />
                    )}
                    Apply Patch
                  </button>
                )}
              </div>

              {plan.warnings.length > 0 && (
                <div className="mb-4 space-y-1">
                  {plan.warnings.map((w, i) => (
                    <p key={i} className="text-xs text-amber-600">⚠ {w}</p>
                  ))}
                </div>
              )}

              <div className="mb-4">
                <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Fields to add</div>
                {plan.fields_to_add.length === 0 ? (
                  <p className="text-xs text-gray-400">No new fields needed</p>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {plan.fields_to_add.map(f => (
                      <span key={f} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-mono">
                        {f}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Template diff toggle */}
              {plan.template_diffs.length > 0 && (
                <div>
                  <button
                    onClick={() => setShowDiff(!showDiff)}
                    className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 mb-2"
                  >
                    <Eye className="h-3.5 w-3.5" />
                    {showDiff ? 'Hide' : 'Show'} template diffs ({plan.template_diffs.length})
                  </button>

                  {showDiff && plan.template_diffs.map(diff => (
                    <div key={diff.template_name} className="mb-4 last:mb-0">
                      <div className="text-xs font-semibold text-gray-600 mb-2">{diff.template_name}</div>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <div className="text-xs text-gray-400 mb-1">Before</div>
                          <pre className="text-xs bg-red-50 border border-red-100 rounded p-2 overflow-auto max-h-32 whitespace-pre-wrap">
                            {diff.original_front}
                          </pre>
                        </div>
                        <div>
                          <div className="text-xs text-gray-400 mb-1">After</div>
                          <pre className="text-xs bg-green-50 border border-green-100 rounded p-2 overflow-auto max-h-32 whitespace-pre-wrap">
                            {diff.patched_front}
                          </pre>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Patch history */}
          {patches.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg">
              <div className="px-4 py-3 border-b border-gray-200">
                <h3 className="font-semibold text-gray-800">Patch History</h3>
              </div>
              <div className="divide-y divide-gray-100">
                {patches.map((p: any) => (
                  <div key={p.id} className="px-4 py-3 flex items-center justify-between gap-2">
                    <div>
                      <div className="text-sm text-gray-800">{p.patched_model_name}</div>
                      <div className="text-xs text-gray-500">
                        v{p.patch_version} · {p.status}
                        {p.fields_added?.length > 0 && ` · +${p.fields_added.join(', ')}`}
                      </div>
                    </div>
                    {p.status === 'active' && (
                      <button
                        onClick={() => rollbackMutation.mutate(p.id)}
                        disabled={rollbackMutation.isPending}
                        className="flex items-center gap-1 text-xs border border-orange-300 text-orange-600 px-2 py-1 rounded-md hover:bg-orange-50 disabled:opacity-50"
                      >
                        <RotateCcw className="h-3 w-3" /> Rollback
                      </button>
                    )}
                    {p.status === 'rolled_back' && (
                      <span className="text-xs text-gray-400">Rolled back</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
