import { ChevronRight, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { formatDisplayDate } from '../../lib/date';
import { getSafeExternalUrl } from '../../lib/url';
import type { Job } from '../../types/job';

interface JobTableProps {
  jobs: Job[];
}

const JobTable = ({ jobs }: JobTableProps) => {
  if (jobs.length === 0) {
    return (
      <div className="glass-card p-10 text-center">
        <p className="text-slate-300 font-medium">No jobs found.</p>
      </div>
    );
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="bg-white/5 border-b border-white/10">
            <tr>
              <th scope="col" className="px-6 py-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Job Title</th>
              <th scope="col" className="px-6 py-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Company</th>
              <th scope="col" className="px-6 py-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Location</th>
              <th scope="col" className="px-6 py-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Match</th>
              <th scope="col" className="px-6 py-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Posted</th>
              <th scope="col" className="px-6 py-4 text-xs font-semibold text-slate-400 uppercase tracking-wider text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {jobs.map((job) => {
              const applyUrl = getSafeExternalUrl(job.url);

              return (
                <tr key={job.id} className="hover:bg-white/5 transition-colors group">
                  <td className="px-6 py-4">
                    <Link to={`/jobs/${job.id}`} className="font-medium text-white hover:text-indigo-400 transition-colors">
                      {job.title}
                    </Link>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[10px] text-slate-500 uppercase font-bold tracking-tighter">{job.platform}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-slate-300">{job.company}</td>
                  <td className="px-6 py-4 text-slate-400 text-sm">{job.location}</td>
                  <td className="px-6 py-4">
                    {job.relevanceScore !== null ? (
                      <div className="flex items-center gap-2">
                        <div className="w-12 bg-white/5 rounded-full h-1.5 flex-1 max-w-[60px]">
                          <div
                            className="bg-indigo-500 h-1.5 rounded-full"
                            style={{ width: `${job.relevanceScore}%` }}
                          />
                        </div>
                        <span className="text-xs font-bold text-indigo-400">{job.relevanceScore}%</span>
                      </div>
                    ) : (
                      <span className="text-slate-600 text-xs">-</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-slate-400 text-sm">
                    {formatDisplayDate(job.postedDate)}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-3 text-slate-500">
                      {applyUrl ? (
                        <a
                          href={applyUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`Open ${job.title} on ${job.platform}`}
                          className="hover:text-white transition-colors"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>
                      ) : (
                        <span
                          className="text-slate-600 cursor-not-allowed"
                          aria-label="External job link unavailable"
                          title="External job link unavailable"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </span>
                      )}
                      <Link
                        to={`/jobs/${job.id}`}
                        aria-label={`View details for ${job.title}`}
                        className="hover:text-indigo-400 transition-colors"
                      >
                        <ChevronRight className="w-5 h-5" />
                      </Link>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default JobTable;
