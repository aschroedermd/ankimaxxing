'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listProviders, createProvider, updateProvider, deleteProvider, testProvider } from '@/lib/api';
import type { ProviderProfile } from '@/lib/api';
import { Loader2, Plus, Trash2, TestTube2, CheckCircle, XCircle, Edit } from 'lucide-react';

const PROVIDER_KINDS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'openai_compatible', label: 'OpenAI-Compatible (local)' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'google', label: 'Google Gemini' },
];

const DEFAULT_MODELS: Record<string, string> = {
  openai: 'gpt-4o-mini',
  openai_compatible: 'llama3.1',
  anthropic: 'claude-haiku-4-5-20251001',
  google: 'gemini-1.5-flash',
};

interface FormState {
  name: string;
  provider_kind: string;
  model: string;
  base_url: string;
  api_key: string;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  concurrency_cap: number;
}

const emptyForm = (): FormState => ({
  name: '',
  provider_kind: 'openai',
  model: 'gpt-4o-mini',
  base_url: '',
  api_key: '',
  temperature: 0.7,
  max_tokens: 2000,
  timeout_seconds: 60,
  concurrency_cap: 3,
});

export default function SettingsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState<FormState>(emptyForm());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, 'ok' | 'error' | 'loading'>>({});

  const providersQuery = useQuery({ queryKey: ['providers'], queryFn: listProviders });

  const saveMutation = useMutation({
    mutationFn: (data: FormState) =>
      editingId
        ? updateProvider(editingId, data)
        : createProvider(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['providers'] });
      setForm(emptyForm());
      setEditingId(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteProvider,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }),
  });

  const handleTest = async (id: number) => {
    setTestResults(prev => ({ ...prev, [id]: 'loading' }));
    try {
      await testProvider(id);
      setTestResults(prev => ({ ...prev, [id]: 'ok' }));
    } catch {
      setTestResults(prev => ({ ...prev, [id]: 'error' }));
    }
  };

  const handleEdit = (profile: ProviderProfile) => {
    setEditingId(profile.id);
    setForm({
      name: profile.name,
      provider_kind: profile.provider_kind,
      model: profile.model,
      base_url: profile.base_url ?? '',
      api_key: '',  // never pre-fill API keys
      temperature: profile.temperature,
      max_tokens: profile.max_tokens,
      timeout_seconds: profile.timeout_seconds,
      concurrency_cap: profile.concurrency_cap,
    });
  };

  const handleKindChange = (kind: string) => {
    setForm(f => ({ ...f, provider_kind: kind, model: DEFAULT_MODELS[kind] ?? '' }));
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Settings</h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Add/edit form */}
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <h3 className="font-semibold text-gray-800 mb-4">
            {editingId ? 'Edit Provider' : 'Add LLM Provider'}
          </h3>

          <form
            onSubmit={e => { e.preventDefault(); saveMutation.mutate(form); }}
            className="space-y-3"
          >
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Profile name</label>
              <input
                required
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g. GPT-4o mini (rewrites)"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
              <select
                value={form.provider_kind}
                onChange={e => handleKindChange(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {PROVIDER_KINDS.map(k => (
                  <option key={k.value} value={k.value}>{k.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
              <input
                required
                value={form.model}
                onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {(form.provider_kind === 'openai_compatible') && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Base URL
                </label>
                <input
                  value={form.base_url}
                  onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))}
                  placeholder="http://localhost:11434/v1"
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                API Key {editingId && <span className="text-gray-400">(leave blank to keep existing)</span>}
              </label>
              <input
                type="password"
                value={form.api_key}
                onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="sk-..."
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Temperature: {form.temperature}
                </label>
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.1}
                  value={form.temperature}
                  onChange={e => setForm(f => ({ ...f, temperature: Number(e.target.value) }))}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Max tokens</label>
                <input
                  type="number"
                  min={100}
                  max={32000}
                  value={form.max_tokens}
                  onChange={e => setForm(f => ({ ...f, max_tokens: Number(e.target.value) }))}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (s)</label>
                <input
                  type="number"
                  min={5}
                  max={300}
                  value={form.timeout_seconds}
                  onChange={e => setForm(f => ({ ...f, timeout_seconds: Number(e.target.value) }))}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Concurrency</label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={form.concurrency_cap}
                  onChange={e => setForm(f => ({ ...f, concurrency_cap: Number(e.target.value) }))}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="flex gap-2 pt-1">
              <button
                type="submit"
                disabled={saveMutation.isPending}
                className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {saveMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                {editingId ? 'Update' : 'Add Provider'}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={() => { setEditingId(null); setForm(emptyForm()); }}
                  className="px-4 py-2 text-sm border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50"
                >
                  Cancel
                </button>
              )}
            </div>

            {saveMutation.isError && (
              <p className="text-sm text-red-600">
                {String((saveMutation.error as any)?.response?.data?.detail ?? 'Save failed')}
              </p>
            )}
          </form>
        </div>

        {/* Provider list */}
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-200">
            <h3 className="font-semibold text-gray-800">Configured Providers</h3>
          </div>
          {providersQuery.isLoading && (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            </div>
          )}
          {providersQuery.data?.length === 0 && (
            <div className="p-6 text-center text-sm text-gray-400">
              <Plus className="h-8 w-8 mx-auto mb-2 opacity-30" />
              No providers yet. Add one to start generating rewrites.
            </div>
          )}
          <div className="divide-y divide-gray-100">
            {providersQuery.data?.map(profile => (
              <div key={profile.id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-800">{profile.name}</div>
                    <div className="text-xs text-gray-500">
                      {PROVIDER_KINDS.find(k => k.value === profile.provider_kind)?.label ?? profile.provider_kind}
                      {' · '}{profile.model}
                      {profile.base_url && ` · ${profile.base_url}`}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      T={profile.temperature} · {profile.max_tokens} tok · {profile.concurrency_cap} concurrent
                      {profile.has_api_key && ' · 🔑'}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {testResults[profile.id] === 'loading' && (
                      <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
                    )}
                    {testResults[profile.id] === 'ok' && (
                      <CheckCircle className="h-4 w-4 text-green-500" />
                    )}
                    {testResults[profile.id] === 'error' && (
                      <XCircle className="h-4 w-4 text-red-500" />
                    )}
                    <button
                      onClick={() => handleTest(profile.id)}
                      title="Test connection"
                      className="p-1 text-gray-400 hover:text-gray-600"
                    >
                      <TestTube2 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => handleEdit(profile)}
                      className="p-1 text-gray-400 hover:text-gray-600"
                    >
                      <Edit className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(profile.id)}
                      disabled={deleteMutation.isPending}
                      className="p-1 text-gray-400 hover:text-red-500"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
