import type { FC } from 'react';
import { memo } from 'react';
import './FilterPanel.css';

export type SortOption = 'date' | 'relevance';

export interface JobFilters {
    platform?: string;
    job_type?: string;
    sort: SortOption;
    search: string;
}

interface PillGroupProps<T extends string> {
    label: string;
    options: { value: T | ''; label: string }[];
    active: T | '';
    onChange: (v: T | '') => void;
}

function PillGroup<T extends string>({ label, options, active, onChange }: PillGroupProps<T>) {
    return (
        <div className="filter-panel__group">
            <span className="filter-panel__group-label">{label}</span>
            <div className="filter-panel__pills">
                {options.map(({ value, label: text }) => (
                    <button
                        key={value === '' ? '__all__' : value}
                        type="button"
                        className={`filter-panel__pill${active === value ? ' filter-panel__pill--active' : ''}`}
                        onClick={() => onChange(value)}
                        aria-pressed={active === value}
                    >
                        {text}
                    </button>
                ))}
            </div>
        </div>
    );
}

const JOB_TYPE_OPTIONS: { value: string | ''; label: string }[] = [
    { value: '', label: 'Any' },
    { value: 'Full-time', label: 'Full-time' },
    { value: 'Part-time', label: 'Part-time' },
    { value: 'Contract', label: 'Contract' },
    { value: 'Casual', label: 'Casual' },
    { value: 'Internship', label: 'Internship' },
];

const PLATFORM_OPTIONS: { value: string | ''; label: string }[] = [
    { value: '', label: 'All' },
    { value: 'seek', label: 'Seek' },
    { value: 'linkedin', label: 'LinkedIn' },
    { value: 'indeed', label: 'Indeed' },
];

const SORT_OPTIONS: { value: SortOption | ''; label: string }[] = [
    { value: 'date', label: 'Latest' },
    { value: 'relevance', label: 'Relevance' },
];

interface FilterPanelProps {
    filters: JobFilters;
    onChange: (filters: JobFilters) => void;
}

const FilterPanel: FC<FilterPanelProps> = memo(({ filters, onChange }) => {
    const set = <K extends keyof JobFilters>(key: K, value: JobFilters[K]) =>
        onChange({ ...filters, [key]: value });

    return (
        <aside className="filter-panel" aria-label="Job filters">
            <PillGroup
                label="Job Type"
                options={JOB_TYPE_OPTIONS}
                active={filters.job_type ?? ''}
                onChange={(v) => set('job_type', v || undefined)}
            />
            <PillGroup
                label="Platform"
                options={PLATFORM_OPTIONS}
                active={filters.platform ?? ''}
                onChange={(v) => set('platform', v || undefined)}
            />
            <PillGroup
                label="Sort By"
                options={SORT_OPTIONS}
                active={filters.sort}
                onChange={(v) => set('sort', (v as SortOption) || 'date')}
            />
        </aside>
    );
});

FilterPanel.displayName = 'FilterPanel';

export default FilterPanel;
