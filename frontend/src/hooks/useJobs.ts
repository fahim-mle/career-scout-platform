import axios from 'axios';
import { useCallback, useState } from 'react';
import { getJob, getJobs, GetJobsParams } from '../api/jobs';
import { Job } from '../types/job';

export const useJobs = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchJobs = useCallback(async (params: GetJobsParams = {}) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJobs(params);
      setJobs(data);
    } catch (err) {
      let errorMessage = 'Failed to fetch jobs';
      if (axios.isAxiosError(err)) {
        errorMessage = err.response?.data?.detail || errorMessage;
      }
      setError(errorMessage);
      console.error('fetchJobs error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchJob = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJob(id);
      setJob(data);
    } catch (err) {
      let errorMessage = 'Failed to fetch job details';
      if (axios.isAxiosError(err)) {
        errorMessage = err.response?.data?.detail || errorMessage;
      }
      setError(errorMessage);
      console.error('fetchJob error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    jobs,
    job,
    loading,
    error,
    fetchJobs,
    fetchJob,
  };
};
