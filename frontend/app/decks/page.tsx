'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listDecks, inspectDeck } from '@/lib/api';
import { cn, supportLevelColor } from '@/lib/utils';
import { Loader2, ChevronRight, Info } from 'lucide-react';
import Link from 'next/link';

export default function DecksPage() {
  const [selectedDeck, setSelectedDeck] = useState<string | null>(null);

  const decksQuery = useQuery({
    queryKey: ['decks'],
    queryFn: listDecks,
  });

  const inspectQuery = useQuery({
    queryKey: ['deck-inspect', selectedDeck],
    queryFn: () => inspectDeck(selectedDeck!),
    enabled: !!selectedDeck,
  });

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Deck Browser</h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Deck list */}
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-5 py-4 border-b border-gray-200">
            <h3 className="font-semibold text-gray-800">Your Decks</h3>
          </div>
          {decksQuery.isLoading && (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="h-6 w-6 text-gray-400 animate-spin" />
            </div>
          )}
          {decksQuery.isError && (
            <div className="p-5 text-sm text-red-600">
              Cannot load decks. Is AnkiConnect running?
            </div>
          )}
          {decksQuery.data && (
            <div className="divide-y divide-gray-100 max-h-[calc(100vh-220px)] overflow-auto">
              {decksQuery.data.map(deck => (
                <button
                  key={deck.name}
                  onClick={() => setSelectedDeck(deck.name)}
                  className={cn(
                    'w-full text-left px-5 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors',
                    selectedDeck === deck.name && 'bg-blue-50'
                  )}
                >
                  <div>
                    <div className="text-sm font-medium text-gray-800">{deck.name}</div>
                    <div className="text-xs text-gray-500">{deck.note_count} notes</div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-gray-400" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Deck details */}
        <div className="bg-white border border-gray-200 rounded-lg">
          {!selectedDeck && (
            <div className="flex flex-col items-center justify-center h-64 text-gray-400">
              <Info className="h-8 w-8 mb-2" />
              <p className="text-sm">Select a deck to inspect it</p>
            </div>
          )}
          {selectedDeck && inspectQuery.isLoading && (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="h-6 w-6 text-gray-400 animate-spin" />
            </div>
          )}
          {inspectQuery.data && (
            <>
              <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-gray-800">{inspectQuery.data.deck_name}</h3>
                  <p className="text-xs text-gray-500">{inspectQuery.data.note_count} notes</p>
                </div>
                <Link
                  href={`/rewrite?deck=${encodeURIComponent(selectedDeck)}`}
                  className="text-sm bg-blue-600 text-white px-3 py-1.5 rounded-md hover:bg-blue-700"
                >
                  Rewrite Deck
                </Link>
              </div>
              <div className="px-5 py-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-3">Note Types</h4>
                <div className="space-y-3">
                  {inspectQuery.data.note_types.map(nt => (
                    <div
                      key={nt.model_name}
                      className="border border-gray-100 rounded-lg p-3"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-sm font-medium text-gray-800">{nt.model_name}</div>
                        <span
                          className={cn(
                            'text-xs px-2 py-0.5 rounded-full font-medium shrink-0',
                            supportLevelColor(nt.support_level)
                          )}
                        >
                          {nt.support_level.replace('_', ' ')}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {nt.field_names.join(' · ')}
                      </div>
                      {nt.notes.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {nt.notes.map((note, i) => (
                            <p key={i} className="text-xs text-amber-600">⚠ {note}</p>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
