/**
 * API client for the Anki Diversify backend.
 * All requests go through Next.js rewrites to http://localhost:8000/api.
 */

import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DeckSummary {
  name: string;
  id?: number;
  note_count: number;
}

export interface NoteTypeSummary {
  model_name: string;
  support_level: 'full' | 'caution' | 'audit_only' | 'unsupported';
  kind: string;
  notes: string[];
  is_app_managed: boolean;
  field_names: string[];
  template_names: string[];
}

export interface DeckInspection {
  deck_name: string;
  note_count: number;
  note_types: NoteTypeSummary[];
}

export interface NotePreview {
  note_id: number;
  model_name: string;
  fields: Record<string, string>;
  tags: string[];
  cards: number[];
}

export interface RewriteVariant {
  id: string;
  style: string;
  text: string;
  text_plain: string;
  warnings: string[];
  error?: string;
  validation?: {
    rating: string;
    rationale: string;
    accept: boolean;
    risk_level: string;
  };
}

export interface NoteRewrite {
  id: number;
  job_id: string;
  note_id: number;
  model_name: string;
  template_name: string;
  prompt_field: string;
  answer_field: string;
  original_prompt: string;
  original_answer: string;
  variants: RewriteVariant[];
  status: string;
  content_hash: string;
  created_at: string;
}

export interface RewriteJob {
  id: string;
  deck_name?: string;
  query?: string;
  status: string;
  variant_count: number;
  total_notes: number;
  processed_notes: number;
  validation_enabled: boolean;
  approval_required: boolean;
  created_at: string;
  error_message?: string;
}

export interface ProviderProfile {
  id: number;
  name: string;
  provider_kind: string;
  model: string;
  base_url?: string;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  concurrency_cap: number;
  use_structured_output: boolean;
  has_api_key: boolean;
  created_at: string;
}

export interface AuditResult {
  id: number;
  job_id?: string;
  note_id: number;
  model_name?: string;
  overall_score: string;
  rationale?: string;
  category_tags: string[];
  created_at: string;
}

export interface AuditSummary {
  job_id: string;
  total: number;
  accurate: number;
  probably_accurate: number;
  possibly_inaccurate: number;
  likely_inaccurate: number;
  wrong: number;
}

export interface PatchPlan {
  original_model_name: string;
  patched_model_name: string;
  fields_to_add: string[];
  template_diffs: Array<{
    template_name: string;
    original_front: string;
    patched_front: string;
    original_back: string;
    patched_back: string;
  }>;
  is_clone: boolean;
  already_patched: boolean;
  warnings: string[];
}

export interface AuditJobResponse {
  id: string;
  deck_name?: string;
  query?: string;
  status: string;
  total_notes: number;
  processed_notes: number;
  created_at: string;
}

export interface AuditJobDetail extends AuditJobResponse {
  error_message?: string;
  provider_profile_id?: number;
  results: AuditResult[];
}

// ---------------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------------

// --- Decks ---

export const pingAnki = () =>
  api.get('/decks/ping').then(r => r.data);

export const listDecks = () =>
  api.get<DeckSummary[]>('/decks/').then(r => r.data);

export const listNoteTypes = () =>
  api.get<NoteTypeSummary[]>('/decks/note-types').then(r => r.data);

export const inspectDeck = (deckName: string) =>
  api.get<DeckInspection>(`/decks/${encodeURIComponent(deckName)}/inspect`).then(r => r.data);

export const listNotes = (deckName: string, limit = 50, offset = 0) =>
  api
    .get<NotePreview[]>(`/decks/${encodeURIComponent(deckName)}/notes`, {
      params: { limit, offset },
    })
    .then(r => r.data);

export const getNoteDetail = (noteId: number) =>
  api.get<NotePreview>(`/decks/notes/${noteId}`).then(r => r.data);

// --- Rewrite Jobs ---

export const createRewriteJob = (payload: {
  deck_name?: string;
  query?: string;
  variant_count?: number;
  distribution?: Record<string, number>;
  provider_profile_id?: number;
  validation_enabled?: boolean;
  approval_required?: boolean;
}) => api.post<RewriteJob>('/rewrites/jobs', payload).then(r => r.data);

export const listJobs = (status?: string) =>
  api.get<RewriteJob[]>('/rewrites/jobs', { params: { status } }).then(r => r.data);

export const getJob = (jobId: string) =>
  api.get<RewriteJob>(`/rewrites/jobs/${jobId}`).then(r => r.data);

export const cancelJob = (jobId: string) =>
  api.post(`/rewrites/jobs/${jobId}/cancel`).then(r => r.data);

export const listJobNotes = (
  jobId: string,
  params?: { status?: string; risk_level?: string; limit?: number; offset?: number }
) =>
  api
    .get<NoteRewrite[]>(`/rewrites/jobs/${jobId}/notes`, { params })
    .then(r => r.data);

export const approveNoteRewrite = (id: number, variantIds: string[], writeBack = false) =>
  api
    .post(`/rewrites/notes/${id}/approve`, {
      variant_ids: variantIds,
      write_back: writeBack,
    })
    .then(r => r.data);

export const rejectNoteRewrite = (id: number) =>
  api.post(`/rewrites/notes/${id}/reject`, {}).then(r => r.data);

export const writeBackNote = (id: number) =>
  api.post(`/rewrites/notes/${id}/write-back`).then(r => r.data);

export const writeBackAll = (jobId: string) =>
  api.post(`/rewrites/jobs/${jobId}/write-back-all`).then(r => r.data);

// --- Audit ---

export const startAudit = (payload: {
  deck_name?: string;
  query?: string;
  provider_profile_id: number;
}) => api.post('/audit/start', payload).then(r => r.data);

export const listAuditResults = (params?: {
  job_id?: string;
  score?: string;
  tag?: string;
  limit?: number;
  offset?: number;
}) => api.get<AuditResult[]>('/audit/results', { params }).then(r => r.data);

export const getAuditSummary = (jobId: string) =>
  api.get<AuditSummary>(`/audit/summary/${jobId}`).then(r => r.data);

export const listAuditJobs = () =>
  api.get<AuditJobResponse[]>('/audit/jobs').then(r => r.data);

export const getAuditJob = (jobId: string) =>
  api.get<AuditJobDetail>(`/audit/jobs/${jobId}`).then(r => r.data);

export const pauseAuditJob = (jobId: string) =>
  api.post(`/audit/jobs/${jobId}/pause`).then(r => r.data);

export const resumeAuditJob = (jobId: string) =>
  api.post(`/audit/jobs/${jobId}/resume`).then(r => r.data);

export const cancelAuditJob = (jobId: string) =>
  api.post(`/audit/jobs/${jobId}/cancel`).then(r => r.data);

// --- Templates ---

export const getPatchPlan = (modelName: string) =>
  api.get<PatchPlan>(`/templates/plan/${encodeURIComponent(modelName)}`).then(r => r.data);

export const applyPatch = (modelName: string) =>
  api.post('/templates/apply', { model_name: modelName, confirmed: true }).then(r => r.data);

export const listPatches = () =>
  api.get('/templates/').then(r => r.data);

export const rollbackPatch = (patchId: number) =>
  api.post(`/templates/${patchId}/rollback`).then(r => r.data);

// --- Settings ---

export const listProviders = () =>
  api.get<ProviderProfile[]>('/settings/providers').then(r => r.data);

export const createProvider = (payload: {
  name: string;
  provider_kind: string;
  model: string;
  base_url?: string;
  api_key?: string;
  temperature?: number;
  max_tokens?: number;
  timeout_seconds?: number;
  concurrency_cap?: number;
}) => api.post<ProviderProfile>('/settings/providers', payload).then(r => r.data);

export const updateProvider = (id: number, payload: Parameters<typeof createProvider>[0]) =>
  api.put<ProviderProfile>(`/settings/providers/${id}`, payload).then(r => r.data);

export const deleteProvider = (id: number) =>
  api.delete(`/settings/providers/${id}`).then(r => r.data);

export const testProvider = (id: number) =>
  api.post(`/settings/providers/${id}/test`).then(r => r.data);

export default api;
