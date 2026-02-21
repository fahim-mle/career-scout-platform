import { LayoutGrid, List as ListIcon, Search, SlidersHorizontal } from 'lucide-react';
import { useEffect, useState } from 'react';
import JobList from '../components/jobs/JobList';
import { useJobs } from '../hooks/useJobs';
import { Job } from '../types/job';

const JobsPage = () => {
  const { jobs, loading, error, fetchJobs } = useJobs();
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const filteredJobs = jobs.filter((job: Job) => {
    const query = searchQuery.toLowerCase();
    return (
      job.title.toLowerCase().includes(query) ||
      job.company.toLowerCase().includes(query) ||
      job.location.toLowerCase().includes(query)
    );
  });

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h1 className="text-4xl font-extrabold text-white tracking-tight">
            Job Board
          </h1>
          <p className="text-slate-400 mt-2 font-medium">
            Explore {jobs.length} enriched opportunities tailored for you.
          </p>
        </div>

        <div className="flex items-center gap-3 bg-white/5 p-1 rounded-xl border border-white/10">
          <button
            onClick={() => setViewMode('grid')}
            className={`p-2 rounded-lg transition-all ${viewMode === 'grid' ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/20' : 'text-slate-400 hover:text-white'}`}
            title="Grid View"
          >
            <LayoutGrid className="w-5 h-5" />
          </button>
          <button
            onClick={() => setViewMode('table')}
            className={`p-2 rounded-lg transition-all ${viewMode === 'table' ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/20' : 'text-slate-400 hover:text-white'}`}
            title="Table View"
          >
            <ListIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative flex-1 group">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500 group-focus-within:text-indigo-400 transition-colors" />
          <input
            type="text"
            placeholder="Search by title, company, or location..."
            className="w-full bg-white/5 border border-white/10 rounded-xl py-4 pl-12 pr-4 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all font-medium"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <button className="flex items-center gap-2 px-6 py-4 bg-white/5 border border-white/10 rounded-xl text-slate-300 hover:text-white hover:bg-white/10 transition-all font-bold">
          <SlidersHorizontal className="w-5 h-5" />
          Filters
        </button>
      </div>

      {loading && jobs.length === 0 ? (
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
      ) : error ? (
        <div className="glass-card p-12 text-center space-y-4">
          <p className="text-red-400 font-medium">{error}</p>
          <button
            onClick={() => fetchJobs()}
            className="text-indigo-400 hover:text-indigo-300 font-medium underline underline-offset-4"
          >
            Try reloading
          </button>
        </div>
      ) : filteredJobs.length === 0 ? (
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
        <JobList jobs={filteredJobs} viewMode={viewMode} />
      )}
    </div>
  );
};

export default JobsPage;
