import axios from 'axios';
import { useCallback, useState } from 'react';
import { getJob, getJobs, GetJobsParams } from '../api/jobs';
import { Job } from '../types/job';

export const useJobs = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobLoading, setJobLoading] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);

  const fetchJobs = useCallback(async (params: GetJobsParams = {}) => {
    setJobsLoading(true);
    setJobsError(null);
    try {
      const data = await getJobs(params);
      setJobs(data);
    } catch (err) {
      let errorMessage = 'Failed to fetch jobs';
      if (axios.isAxiosError(err)) {
        errorMessage = err.response?.data?.detail || errorMessage;
      }
      setJobsError(errorMessage);
      console.error('fetchJobs error:', err);
    } finally {
      setJobsLoading(false);
    }
  }, []);

  const fetchJob = useCallback(async (id: number) => {
    setJobLoading(true);
    setJobError(null);
    try {
      const data = await getJob(id);
      setJob(data);
    } catch (err) {
      let errorMessage = 'Failed to fetch job details';
      if (axios.isAxiosError(err)) {
        errorMessage = err.response?.data?.detail || errorMessage;
      }
      setJobError(errorMessage);
      console.error('fetchJob error:', err);
    } finally {
      setJobLoading(false);
    }
  }, []);

  const loading = jobsLoading || jobLoading;
  const error = jobError || jobsError;

  return {
    jobs,
    job,
    jobsLoading,
    jobLoading,
    jobsError,
    jobError,
    loading,
    error,
    fetchJobs,
    fetchJob,
  };
};
