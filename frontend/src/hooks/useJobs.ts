import axios from 'axios';
import { useCallback, useRef, useState } from 'react';
import { getJob, getJobs } from '../api/jobs';
import type { GetJobsParams } from '../api/jobs';
import type { Job } from '../types/job';

interface ApiErrorPayload {
  detail?: string;
}

const getErrorDetail = (error: unknown): string | null => {
  if (!axios.isAxiosError(error)) {
    return null;
  }

  const data = error.response?.data as ApiErrorPayload | undefined;
  return typeof data?.detail === 'string' ? data.detail : null;
};

export const useJobs = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobLoading, setJobLoading] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const latestJobsRequestId = useRef(0);

  const fetchJobs = useCallback(async (params: GetJobsParams = {}) => {
    const requestId = ++latestJobsRequestId.current;
    setJobsLoading(true);
    setJobsError(null);
    try {
      const data = await getJobs(params);
      if (requestId !== latestJobsRequestId.current) {
        return;
      }
      setJobs(data);
    } catch (err) {
      if (requestId !== latestJobsRequestId.current) {
        return;
      }
      let errorMessage = 'Failed to fetch jobs';
      const detail = getErrorDetail(err);
      if (detail) {
        errorMessage = detail;
      }
      setJobsError(errorMessage);
      console.error('fetchJobs error:', err);
    } finally {
      if (requestId === latestJobsRequestId.current) {
        setJobsLoading(false);
      }
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
      const detail = getErrorDetail(err);
      if (detail) {
        errorMessage = detail;
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
