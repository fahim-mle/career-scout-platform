import {
  DescriptionSection,
  EnrichmentStatus,
  Job,
  Platform,
} from '../types/job';
import apiClient from './apiClient';

export interface BackendJob {
  id: number;
  title: string;
  company: string;
  location: string;
  platform: string;
  url: string;
  external_id: string;
  description_short: string | null;
  description_full: string | null;
  posted_date: string | null;
  scraped_at: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
  skills: string[] | null;
  job_type: string | null;
  salary_range: {
    min: number;
    max: number;
    currency: string;
    period: string | null;
    raw: string | null;
  } | null;
  enrichment_status: EnrichmentStatus | null;
  enrichment_version: string | null;
  enrichment_updated_at: string | null;
  description_sections: DescriptionSection[] | null;
  relevance_score: number | null;
}

const ALLOWED_PLATFORMS = ['linkedin', 'seek', 'indeed'] as const;

const normalizePlatform = (platform: string): Platform => {
  if (ALLOWED_PLATFORMS.includes(platform as Platform)) {
    return platform as Platform;
  }

  console.warn(`Unknown platform received from API: ${platform}`);
  return 'linkedin';
};

export interface GetJobsParams {
  skip?: number;
  limit?: number;
  platform?: string;
  is_active?: boolean;
  sort?: 'date' | 'relevance';
  job_type?: string;
  search?: string;
}

const sanitizeJobsParams = (params: GetJobsParams): GetJobsParams => {
  const normalizeValue = (value?: string): string | undefined => {
    if (typeof value !== 'string') {
      return undefined;
    }

    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : undefined;
  };

  return {
    ...params,
    platform: normalizeValue(params.platform),
    job_type: normalizeValue(params.job_type),
    search: normalizeValue(params.search),
  };
};

/**
 * Normalizes snake_case backend response to camelCase frontend model.
 */
const normalizeJob = (data: BackendJob): Job => ({
  id: data.id,
  title: data.title,
  company: data.company,
  location: data.location,
  platform: normalizePlatform(data.platform),
  url: data.url,
  externalId: data.external_id,
  descriptionShort: data.description_short,
  descriptionFull: data.description_full,
  postedDate: data.posted_date,
  scrapedAt: data.scraped_at,
  createdAt: data.created_at,
  updatedAt: data.updated_at,
  isActive: data.is_active,
  skills: data.skills,
  jobType: data.job_type,
  salaryRange: data.salary_range ? {
    min: data.salary_range.min,
    max: data.salary_range.max,
    currency: data.salary_range.currency,
    period: data.salary_range.period,
    raw: data.salary_range.raw,
  } : null,
  enrichmentStatus: data.enrichment_status,
  enrichmentVersion: data.enrichment_version,
  enrichmentUpdatedAt: data.enrichment_updated_at,
  descriptionSections: data.description_sections ?? null,
  relevanceScore: data.relevance_score,
});

export const getJobs = async (params: GetJobsParams = {}): Promise<Job[]> => {
  const response = await apiClient.get('/jobs', { params: sanitizeJobsParams(params) });
  return (response.data || []).map(normalizeJob);
};

export const getJob = async (id: number): Promise<Job> => {
  const response = await apiClient.get(`/jobs/${id}`);
  return normalizeJob(response.data);
};
