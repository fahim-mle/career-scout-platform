import './JobsPage.css';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { SlidersHorizontal, X, Search, LayoutGrid, List as ListIcon } from 'lucide-react';
import JobList from '@/components/jobs/JobList';
import FilterPanel, { type JobFilters } from '@/components/jobs/FilterPanel';
import { useJobs } from '@/hooks/useJobs';
import type { GetJobsParams } from '@/api/jobs';

const DEFAULT_FILTERS: JobFilters = {
  sort: 'date',
  search: '',
};

function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

export default function JobsPage() {
  const { jobs, loading: jobsLoading, error: jobsError, fetchJobs } = useJobs();

  // Filter state
  const [filters, setFilters] = useState<JobFilters>(DEFAULT_FILTERS);
  const [panelOpen, setPanelOpen] = useState(false);
  const debouncedSearch = useDebounce(filters.search, 350);

  // View state
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');

  // Count active (non-default) filters for badge
  const activeFilterCount =
    (filters.platform ? 1 : 0) +
    (filters.job_type ? 1 : 0) +
    (filters.sort !== 'date' ? 1 : 0) +
    (debouncedSearch.trim() ? 1 : 0);

  const hasActiveFilters = activeFilterCount > 0;

  const appliedFilters = useMemo(() => {
    const entries: string[] = [];

    if (debouncedSearch.trim()) {
      entries.push(`Search: "${debouncedSearch.trim()}"`);
    }
    if (filters.platform) {
      entries.push(`Platform: ${filters.platform}`);
    }
    if (filters.job_type) {
      entries.push(`Job type: ${filters.job_type}`);
    }
    if (filters.sort !== 'date') {
      entries.push('Sort: relevance');
    }

    return entries;
  }, [debouncedSearch, filters.job_type, filters.platform, filters.sort]);

  // Build API params from filters
  const buildParams = useCallback(
    (f: JobFilters, search: string): GetJobsParams => ({
      is_active: true,
      sort: f.sort,
      platform: f.platform || undefined,
      job_type: f.job_type || undefined,
      search: search.trim() || undefined,
    }),
    [],
  );

  // Refetch when filters or debounced search change
  useEffect(() => {
    fetchJobs(buildParams(filters, debouncedSearch));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.sort, filters.platform, filters.job_type, debouncedSearch]);

  const handleFiltersChange = (updated: JobFilters) => {
    // Keep search text in local state; panel only owns sort/platform/job_type
    setFilters((prev) => ({ ...updated, search: prev.search }));
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilters((prev) => ({ ...prev, search: e.target.value }));
  };

  const handleClearAll = () => {
    setFilters(DEFAULT_FILTERS);
  };

  // Subtitle
  const subtitle = jobsLoading
    ? 'Loading…'
    : `${jobs.length} job${jobs.length !== 1 ? 's' : ''}${debouncedSearch.trim() ? ` for "${debouncedSearch.trim()}"` : ''
    }`;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold text-white tracking-tight">Job Board</h2>
          <p className="text-slate-400 mt-2 font-medium">{subtitle}</p>
        </div>

        <div className="flex bg-white/5 border border-white/10 rounded-xl p-1 w-fit">
          <button
            onClick={() => setViewMode('grid')}
            className={`p-2 rounded-lg transition-all ${viewMode === 'grid'
                ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/20'
                : 'text-slate-400 hover:text-white'
              }`}
            title="Grid View"
            aria-label="Switch to grid view"
            aria-pressed={viewMode === 'grid'}
          >
            <LayoutGrid className="w-5 h-5" />
          </button>
          <button
            onClick={() => setViewMode('table')}
            className={`p-2 rounded-lg transition-all ${viewMode === 'table'
                ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/20'
                : 'text-slate-400 hover:text-white'
              }`}
            title="Table View"
            aria-label="Switch to table view"
            aria-pressed={viewMode === 'table'}
          >
            <ListIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative flex-1 group">
          <label htmlFor="job-search" className="sr-only">
            Search jobs by title, company, or location
          </label>
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500 group-focus-within:text-indigo-400 transition-colors" />
          <input
            id="job-search"
            type="search"
            placeholder="Search by title, company, or location..."
            className="w-full bg-white/5 border border-white/10 rounded-xl py-4 pl-12 pr-4 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all font-medium"
            value={filters.search}
            onChange={handleSearchChange}
          />
        </div>

        {hasActiveFilters && (
          <button
            onClick={handleClearAll}
            className="flex items-center gap-2 px-6 py-4 bg-white/5 border border-white/10 rounded-xl text-slate-300 hover:text-white hover:bg-white/10 transition-all font-bold"
          >
            <X className="w-5 h-5" />
            Clear
          </button>
        )}

        <button
          onClick={() => setPanelOpen((o) => !o)}
          className={`flex items-center gap-2 px-6 py-4 border rounded-xl transition-all font-bold ${panelOpen
              ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-300'
              : 'bg-white/5 border-white/10 text-slate-300 hover:text-white hover:bg-white/10'
            }`}
          aria-expanded={panelOpen}
        >
          <SlidersHorizontal className="w-5 h-5" />
          Filters
          {hasActiveFilters && (
            <span className="flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full bg-indigo-500 text-white text-xs font-bold leading-none">
              {activeFilterCount}
            </span>
          )}
        </button>
      </div>

      {hasActiveFilters && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-white/5 p-3" aria-live="polite">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Active filters</span>
          {appliedFilters.map((label) => (
            <span key={label} className="rounded-full border border-indigo-400/30 bg-indigo-500/15 px-3 py-1 text-xs font-medium text-indigo-200">
              {label}
            </span>
          ))}
        </div>
      )}

      {jobsLoading && jobs.length > 0 && (
        <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200" role="status" aria-live="polite">
          Updating results for current filters...
        </div>
      )}

      {panelOpen && (
        <div role="region" aria-label="Filter options">
          <FilterPanel filters={filters} onChange={handleFiltersChange} />
        </div>
      )}

      {jobsLoading && jobs.length === 0 ? (
        viewMode === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="glass-card p-6 space-y-4 animate-pulse">
                <div className="h-6 bg-white/10 rounded-lg w-3/4" />
                <div className="h-4 bg-white/5 rounded-lg w-1/2" />
                <div className="space-y-2 pt-4">
                  <div className="h-3 bg-white/5 rounded-lg w-full" />
                  <div className="h-3 bg-white/5 rounded-lg w-full" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="glass-card p-6 space-y-4 animate-pulse">
            <div className="h-8 bg-white/10 rounded-lg w-full" />
            <div className="h-12 bg-white/5 rounded-lg w-full" />
            <div className="h-12 bg-white/5 rounded-lg w-full" />
            <div className="h-12 bg-white/5 rounded-lg w-full" />
          </div>
        )
      ) : jobsError ? (
        <div className="glass-card p-12 text-center space-y-4">
          <p className="text-red-400 font-medium">{jobsError}</p>
          <button
            onClick={() => fetchJobs(buildParams(filters, debouncedSearch))}
            className="text-indigo-400 hover:text-indigo-300 font-medium underline underline-offset-4"
          >
            Try reloading
          </button>
        </div>
      ) : jobs.length === 0 ? (
        <div className="glass-card p-12 text-center space-y-3">
          <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-4">
            <Search className="w-8 h-8 text-slate-500" />
          </div>
          <h3 className="text-xl font-bold text-white">No jobs found</h3>
          <p className="text-slate-400 max-w-sm mx-auto">
            Try adjusting your search or filters to find what you're looking for.
          </p>
        </div>
      ) : (
        <JobList jobs={jobs} viewMode={viewMode} />
      )}
    </div>
  );
}
