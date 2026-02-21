import {
  ArrowLeft,
  Briefcase,
  Calendar,
  Clock,
  DollarSign,
  ExternalLink,
  Globe,
  MapPin,
  ShieldCheck
} from 'lucide-react';
import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useJobs } from '../../hooks/useJobs';
import { formatDisplayDate, formatDisplayDateTime } from '../../lib/date';

const JobDetails = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { job, loading, error, fetchJob } = useJobs();
  const parsedJobId = id ? Number.parseInt(id, 10) : Number.NaN;
  const hasValidJobId = Number.isInteger(parsedJobId) && parsedJobId > 0;

  useEffect(() => {
    if (hasValidJobId) {
      fetchJob(parsedJobId);
    }
  }, [parsedJobId, hasValidJobId, fetchJob]);

  if (id && !hasValidJobId) {
    return (
      <div className="glass-card p-12 text-center space-y-4">
        <p className="text-red-400 font-medium">Invalid job id.</p>
        <button
          onClick={() => navigate('/jobs')}
          className="text-indigo-400 hover:text-indigo-300 font-medium flex items-center justify-center gap-2 mx-auto"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Job Board
        </button>
      </div>
    );
  }

  if (loading || (!job && !error && hasValidJobId)) {
    return (
      <div className="flex flex-col items-center justify-center h-64 space-y-4">
        <div className="w-12 h-12 border-4 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin" />
        <p className="text-slate-400 animate-pulse">Loading job details...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card p-12 text-center space-y-4">
        <p className="text-red-400 font-medium">{error}</p>
        <button
          onClick={() => navigate('/jobs')}
          className="text-indigo-400 hover:text-indigo-300 font-medium flex items-center justify-center gap-2 mx-auto"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Job Board
        </button>
      </div>
    );
  }

  if (!job) return null;

  const fullDescription = (job.descriptionFull || '').trim();
  const shortDescription = (job.descriptionShort || '').trim();
  const displayDescription =
    fullDescription.length >= shortDescription.length
      ? fullDescription || shortDescription
      : shortDescription;
  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Navigation */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors group"
      >
        <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
        <span className="font-medium">Back</span>
      </button>

      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
             <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 text-xs font-bold border border-indigo-500/20 uppercase">
              {job.platform}
            </span>
            {job.relevanceScore !== null && (
               <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-bold border border-emerald-500/20">
                {job.relevanceScore}% Match
              </span>
            )}
          </div>
          <h1 className="text-4xl md:text-5xl font-extrabold text-white tracking-tight leading-tight">
            {job.title}
          </h1>
          <div className="flex items-center gap-3 text-xl text-slate-300">
            <span className="font-semibold">{job.company}</span>
            <span className="text-slate-600">•</span>
            <span className="flex items-center gap-1.5 font-medium">
              <MapPin className="w-5 h-5 text-indigo-400" />
              {job.location}
            </span>
          </div>
        </div>

        <div className="flex gap-4">
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-8 py-4 rounded-xl font-bold transition-all shadow-[0_0_20px_rgba(79,70,229,0.3)] hover:shadow-[0_0_25px_rgba(79,70,229,0.5)]"
          >
            Apply Now
            <ExternalLink className="w-5 h-5" />
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-8">
           {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="glass-card p-4 flex flex-col items-center justify-center text-center space-y-1">
              <Clock className="w-4 h-4 text-indigo-400 mb-1" />
              <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Posted</span>
              <span className="text-sm font-semibold text-white">
                {formatDisplayDate(job.postedDate, 'Unknown')}
              </span>
            </div>
            <div className="glass-card p-4 flex flex-col items-center justify-center text-center space-y-1">
              <Briefcase className="w-4 h-4 text-indigo-400 mb-1" />
              <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Type</span>
              <span className="text-sm font-semibold text-white">{job.jobType || 'Not specified'}</span>
            </div>
            <div className="glass-card p-4 flex flex-col items-center justify-center text-center space-y-1">
              <DollarSign className="w-4 h-4 text-indigo-400 mb-1" />
              <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Salary</span>
              <span className="text-sm font-semibold text-white">
                {job.salaryRange?.raw || 'Not listed'}
              </span>
            </div>
             <div className="glass-card p-4 flex flex-col items-center justify-center text-center space-y-1">
              <ShieldCheck className="w-4 h-4 text-indigo-400 mb-1" />
              <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Enrichment</span>
              <span className="text-sm font-semibold text-white capitalize">{job.enrichmentStatus ? job.enrichmentStatus.replace(/_/g, ' ') : 'Pending'}</span>
            </div>
          </div>

          {/* Description */}
          <section className="glass-card p-8 space-y-6">
            <h3 className="text-2xl font-bold text-white flex items-center gap-2">
              Job Description
            </h3>
            <div className="prose prose-invert max-w-none text-slate-300 leading-relaxed whitespace-pre-wrap">
              {displayDescription || 'No description available for this position.'}
            </div>
          </section>
        </div>

        {/* Sidebar Info */}
        <div className="space-y-8">
          {/* Skills */}
          {job.skills && job.skills.length > 0 && (
            <section className="glass-card p-6 space-y-4">
              <h4 className="text-lg font-bold text-white">Required Skills</h4>
              <div className="flex flex-wrap gap-2">
                {job.skills.map((skill) => (
                  <span
                    key={skill}
                    className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-sm text-slate-300 font-medium"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Additional Metadata */}
          <section className="glass-card p-6 space-y-4">
            <h4 className="text-lg font-bold text-white">Additional Info</h4>
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <Globe className="w-4 h-4 text-indigo-400 mt-1" />
                <div>
                  <p className="text-xs font-bold text-slate-500 mb-0.5 uppercase">External ID</p>
                  <p className="text-sm text-slate-300 break-all">{job.externalId}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Calendar className="w-4 h-4 text-indigo-400 mt-1" />
                <div>
                  <p className="text-xs font-bold text-slate-500 mb-0.5 uppercase">Scraped At</p>
                  <p className="text-sm text-slate-300">
                    {formatDisplayDateTime(job.scrapedAt)}
                  </p>
                </div>
              </div>
              {job.enrichmentVersion && (
                <div className="flex items-start gap-3">
                  <ShieldCheck className="w-4 h-4 text-indigo-400 mt-1" />
                  <div>
                    <p className="text-xs font-bold text-slate-500 mb-0.5 uppercase">Extractor Version</p>
                    <p className="text-sm text-slate-300">{job.enrichmentVersion}</p>
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default JobDetails;
