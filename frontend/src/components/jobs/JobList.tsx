import { Job } from '../../types/job';
import JobCard from './JobCard';
import JobTable from './JobTable';

interface JobListProps {
  jobs: Job[];
  viewMode: 'grid' | 'table';
}

const JobList = ({ jobs, viewMode }: JobListProps) => {
  if (jobs.length === 0) {
    return (
      <div className="glass-card p-10 text-center">
        <p className="text-slate-300 font-medium">No jobs found.</p>
      </div>
    );
  }

  if (viewMode === 'table') {
    return <JobTable jobs={jobs} />;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {jobs.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
    </div>
  );
};

export default JobList;
