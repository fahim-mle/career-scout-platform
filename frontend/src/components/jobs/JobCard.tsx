import { Calendar, ExternalLink, MapPin } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Job } from '../../types/job';

interface JobCardProps {
  job: Job;
}

const JobCard = ({ job }: JobCardProps) => {
  return (
    <div className="glass-card p-6 hover:border-indigo-500/50 transition-all group flex flex-col h-full">
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1">
          <Link to={`/jobs/${job.id}`}>
            <h3 className="text-xl font-bold text-white group-hover:text-indigo-400 transition-colors line-clamp-2">
              {job.title}
            </h3>
          </Link>
          <p className="text-slate-300 font-medium mt-1">{job.company}</p>
        </div>
        {job.relevanceScore !== null && (
          <div className="flex items-center justify-center w-12 h-12 rounded-full border-2 border-indigo-500/30 bg-indigo-500/10 shrink-0">
            <span className="text-sm font-bold text-indigo-400">{job.relevanceScore}%</span>
          </div>
        )}
      </div>

      <div className="space-y-2 mb-6 flex-1">
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <MapPin className="w-4 h-4" />
          <span>{job.location}</span>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Calendar className="w-4 h-4" />
          <span>{job.postedDate ? new Date(job.postedDate).toLocaleDateString() : 'Date missing'}</span>
        </div>
      </div>

      <div className="flex items-center justify-between mt-auto pt-4 border-t border-white/5">
        <span className="px-2 py-1 rounded-md bg-white/5 text-xs text-slate-400 border border-white/10 uppercase tracking-wider font-semibold">
          {job.platform}
        </span>
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-slate-400 hover:text-white transition-colors"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>
    </div>
  );
};

export default JobCard;
