'use client';

import './globals.css';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  Layers,
  RefreshCw,
  ShieldCheck,
  Wrench,
  Settings,
} from 'lucide-react';

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/decks', label: 'Decks', icon: Layers },
  { href: '/rewrite', label: 'Rewrite', icon: RefreshCw },
  { href: '/audit', label: 'Audit', icon: ShieldCheck },
  { href: '/templates', label: 'Templates', icon: Wrench },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        staleTime: 10_000,
      },
    },
  }));

  const pathname = usePathname();

  return (
    <html lang="en">
      <body>
        <QueryClientProvider client={queryClient}>
          <div className="flex h-screen bg-gray-50">
            {/* Sidebar */}
            <aside className="w-56 bg-white border-r border-gray-200 flex flex-col">
              <div className="px-4 py-5 border-b border-gray-200">
                <h1 className="text-lg font-bold text-gray-900">Anki Diversify</h1>
                <p className="text-xs text-gray-500 mt-0.5">AI-powered card variants</p>
              </div>
              <nav className="flex-1 px-2 py-4 space-y-1">
                {navItems.map(({ href, label, icon: Icon }) => {
                  const active = href === '/'
                    ? pathname === '/'
                    : pathname.startsWith(href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      className={cn(
                        'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                        active
                          ? 'bg-blue-50 text-blue-700'
                          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      {label}
                    </Link>
                  );
                })}
              </nav>
              <div className="px-4 py-3 border-t border-gray-200">
                <p className="text-xs text-gray-400">v0.1.0</p>
              </div>
            </aside>

            {/* Main content */}
            <main className="flex-1 overflow-auto">
              {children}
            </main>
          </div>
        </QueryClientProvider>
      </body>
    </html>
  );
}
