import { Job } from '../../types/job';
import JobCard from './JobCard';
import JobTable from './JobTable';

interface JobListProps {
  jobs: Job[];
  viewMode: 'grid' | 'table';
}

const JobList = ({ jobs, viewMode }: JobListProps) => {
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
