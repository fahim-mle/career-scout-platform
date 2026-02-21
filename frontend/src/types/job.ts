export type Platform = 'linkedin' | 'seek' | 'indeed';
export type EnrichmentStatus = 'pending' | 'completed' | 'failed' | 'not_applicable';

export interface SalaryRange {
  min: number;
  max: number;
  currency: string;
  period: string | null;
  raw: string | null;
}

export interface DescriptionSection {
  title: string;
  items: string[];
}

export interface Job {
  id: number;
  title: string;
  company: string;
  location: string;
  platform: Platform;
  url: string;
  externalId: string;
  descriptionShort: string | null;
  descriptionFull: string | null;
  postedDate: string | null;
  scrapedAt: string;
  createdAt: string;
  updatedAt: string;
  isActive: boolean;

  // Enrichment fields
  skills: string[] | null;
  jobType: string | null;
  salaryRange: SalaryRange | null;
  enrichmentStatus: EnrichmentStatus | null;
  enrichmentVersion: string | null;
  enrichmentUpdatedAt: string | null;
  descriptionSections: DescriptionSection[] | null;

  // Scoring
  relevanceScore: number | null;
}
