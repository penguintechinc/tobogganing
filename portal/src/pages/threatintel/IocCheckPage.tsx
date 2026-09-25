import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Search, ShieldAlert, ShieldCheck } from 'lucide-react';
import { checkIoc, IOC_TYPES, type IocVerdict } from '../../api/threatintel';

/**
 * IocCheckPage — ad-hoc lookup of a single indicator (IP/domain/URL/hash)
 * against the SASE blocklist, rendering a verdict card with severity/source.
 */
export function IocCheckPage() {
  const [iocType, setIocType] = useState<string>('domain');
  const [value, setValue] = useState('');
  const [verdict, setVerdict] = useState<IocVerdict | null | undefined>(undefined);

  const {
    mutate: runCheck,
    isPending,
    error,
  } = useMutation({
    mutationFn: () => checkIoc(iocType, value.trim()),
    onSuccess: (result) => {
      console.log('[IocCheckPage] CheckIoc success { found }', { found: result !== null });
      setVerdict(result);
    },
    onError: (err) => {
      console.error('[IocCheckPage] CheckIoc error', { error: String(err) });
      setVerdict(undefined);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) {
      return;
    }
    console.log('[IocCheckPage] Submit { iocType }', { iocType });
    runCheck();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-amber-400">IOC Check</h1>

      <form
        onSubmit={handleSubmit}
        className="bg-slate-800 rounded-lg p-4 flex flex-col sm:flex-row gap-3 items-stretch sm:items-end"
      >
        <div className="w-full sm:w-40">
          <label htmlFor="ioc-type" className="block text-sm text-slate-300 mb-1">
            Type
          </label>
          <select
            id="ioc-type"
            value={iocType}
            onChange={(e) => setIocType(e.target.value)}
            className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            {IOC_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1">
          <label htmlFor="ioc-value" className="block text-sm text-slate-300 mb-1">
            Indicator value
          </label>
          <input
            id="ioc-value"
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="e.g. malicious.example.com"
            className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-sky-500"
          />
        </div>

        <button
          type="submit"
          disabled={isPending || !value.trim()}
          aria-label="Check indicator against blocklist"
          className="flex items-center justify-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded disabled:opacity-50 transition-colors focus:ring-2 focus:ring-sky-500 focus:outline-none"
        >
          <Search size={16} />
          {isPending ? 'Checking...' : 'Check'}
        </button>
      </form>

      {error && (
        <div className="bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded">
          <p className="font-semibold">Lookup failed</p>
          <p className="text-sm">{error.message}</p>
        </div>
      )}

      {verdict === null && (
        <div
          data-testid="ioc-verdict-clean"
          className="bg-green-900 border border-green-700 text-green-100 px-4 py-4 rounded-lg flex items-center gap-3"
        >
          <ShieldCheck size={24} />
          <div>
            <p className="font-semibold">Not blocked</p>
            <p className="text-sm text-green-200">No matching indicator found in the blocklist.</p>
          </div>
        </div>
      )}

      {verdict && (
        <div
          data-testid="ioc-verdict-blocked"
          className="bg-red-900 border border-red-700 text-red-100 px-4 py-4 rounded-lg space-y-2"
        >
          <div className="flex items-center gap-3">
            <ShieldAlert size={24} />
            <p className="font-semibold text-lg">Blocked</p>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-red-300">Type</dt>
            <dd>{verdict.ioc_type}</dd>
            <dt className="text-red-300">Value</dt>
            <dd className="font-mono">{verdict.value}</dd>
            <dt className="text-red-300">Severity</dt>
            <dd>{verdict.severity}</dd>
            <dt className="text-red-300">Source</dt>
            <dd>{verdict.source}</dd>
            <dt className="text-red-300">STIX ID</dt>
            <dd className="font-mono text-xs">{verdict.stix_id}</dd>
            <dt className="text-red-300">First seen</dt>
            <dd>{new Date(verdict.first_seen * 1000).toLocaleString()}</dd>
            <dt className="text-red-300">Expiry</dt>
            <dd>{verdict.expiry ? new Date(verdict.expiry * 1000).toLocaleString() : 'never'}</dd>
          </dl>
        </div>
      )}
    </div>
  );
}
