import { FileText, Loader2, Save, Upload, X } from 'lucide-react';
import { useRef, useState } from 'react';
import type { Profile, ProfileCreate, ProfileUpdate } from '../../types/profile';

interface ProfileFormProps {
  profile: Profile | null;
  saving: boolean;
  uploading: boolean;
  saveError: string | null;
  uploadError: string | null;
  onSave: (data: ProfileCreate | ProfileUpdate) => Promise<unknown>;
  onUploadCV: (file: File) => Promise<unknown>;
}

const ACCEPTED_CV_TYPES = '.pdf,.docx';

export function ProfileForm({
  profile,
  saving,
  uploading,
  saveError,
  uploadError,
  onSave,
  onUploadCV,
}: ProfileFormProps) {
  const [name, setName] = useState(profile?.name ?? '');
  const [location, setLocation] = useState(profile?.location ?? '');
  const [experienceYears, setExperienceYears] = useState(
    profile?.experience_years ?? 0,
  );
  const [skillsInput, setSkillsInput] = useState(
    (profile?.skills ?? []).join(', '),
  );
  const [remoteOnly, setRemoteOnly] = useState(
    (profile?.preferences as Record<string, unknown> | null)?.remote === true,
  );
  const [jobTypes, setJobTypes] = useState<string[]>(
    ((profile?.preferences as Record<string, unknown> | null)
      ?.job_types as string[]) ?? [],
  );
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const JOB_TYPE_OPTIONS = ['Full-time', 'Part-time', 'Contract', 'Internship'];

  const toggleJobType = (type: string) => {
    setJobTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveSuccess(false);
    const skills = skillsInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const data: ProfileCreate = {
      name,
      location,
      experience_years: experienceYears,
      skills,
      preferences: { remote: remoteOnly, job_types: jobTypes },
    };
    await onSave(data);
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 3000);
  };

  const handleFile = async (file: File) => {
    setUploadedFileName(file.name);
    await onUploadCV(file);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const inputClass =
    'w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 ' +
    'text-slate-200 placeholder-slate-500 focus:outline-none ' +
    'focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 ' +
    'transition-all';

  const labelClass = 'block text-sm font-medium text-slate-400 mb-2';

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Personal info */}
      <div className="glass-card p-6 space-y-4">
        <h2 className="text-lg font-semibold text-slate-200">
          Personal Information
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Full Name</label>
            <input
              className={inputClass}
              placeholder="Jane Smith"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className={labelClass}>Location</label>
            <input
              className={inputClass}
              placeholder="Brisbane, QLD"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              required
            />
          </div>
        </div>

        <div>
          <label className={labelClass}>Years of Experience</label>
          <input
            type="number"
            min={0}
            className={inputClass}
            value={experienceYears}
            onChange={(e) => setExperienceYears(Number(e.target.value))}
            required
          />
        </div>

        <div>
          <label className={labelClass}>
            Skills{' '}
            <span className="text-slate-500 font-normal">
              (comma-separated)
            </span>
          </label>
          <input
            className={inputClass}
            placeholder="Python, FastAPI, PostgreSQL"
            value={skillsInput}
            onChange={(e) => setSkillsInput(e.target.value)}
          />
          {skillsInput && (
            <div className="flex flex-wrap gap-2 mt-2">
              {skillsInput
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean)
                .map((skill) => (
                  <span
                    key={skill}
                    className="px-2 py-1 text-xs rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                  >
                    {skill}
                  </span>
                ))}
            </div>
          )}
        </div>
      </div>

      {/* Preferences */}
      <div className="glass-card p-6 space-y-4">
        <h2 className="text-lg font-semibold text-slate-200">Preferences</h2>

        <div>
          <label className={labelClass}>Job Types</label>
          <div className="flex flex-wrap gap-2">
            {JOB_TYPE_OPTIONS.map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => toggleJobType(type)}
                className={
                  'px-3 py-1.5 rounded-full text-sm border transition-all ' +
                  (jobTypes.includes(type)
                    ? 'bg-indigo-500/30 border-indigo-500/60 text-indigo-200'
                    : 'bg-white/5 border-white/10 text-slate-400 hover:border-white/20')
                }
              >
                {type}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setRemoteOnly((v) => !v)}
            className={
              'relative w-10 h-6 rounded-full transition-all ' +
              (remoteOnly ? 'bg-indigo-500' : 'bg-white/10')
            }
          >
            <span
              className={
                'absolute top-1 w-4 h-4 bg-white rounded-full transition-all ' +
                (remoteOnly ? 'left-5' : 'left-1')
              }
            />
          </button>
          <span className="text-sm text-slate-300">Remote only</span>
        </div>
      </div>

      {/* CV Upload */}
      <div className="glass-card p-6 space-y-4">
        <h2 className="text-lg font-semibold text-slate-200">Resume / CV</h2>

        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={
            'relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ' +
            (dragOver
              ? 'border-indigo-400 bg-indigo-500/10'
              : 'border-white/10 hover:border-white/20 hover:bg-white/5')
          }
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_CV_TYPES}
            className="hidden"
            onChange={handleFileInput}
          />
          {uploading ? (
            <div className="flex flex-col items-center gap-2 text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
              <span className="text-sm">Parsing CV with AI…</span>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <Upload className="w-8 h-8 text-slate-500" />
              <p className="text-sm text-slate-400">
                Drag & drop or{' '}
                <span className="text-indigo-400">browse</span>
              </p>
              <p className="text-xs text-slate-600">PDF or DOCX, max 10 MB</p>
            </div>
          )}
        </div>

        {uploadError && (
          <p className="text-sm text-red-400 flex items-center gap-1">
            <X className="w-4 h-4" /> {uploadError}
          </p>
        )}

        {uploadedFileName && !uploading && !uploadError && (
          <p className="text-sm text-emerald-400 flex items-center gap-1">
            <FileText className="w-4 h-4" /> {uploadedFileName} uploaded
          </p>
        )}

        {profile?.resume_text && (
          <div className="mt-2">
            <label className={labelClass}>Parsed CV Summary</label>
            <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-sm text-slate-400 max-h-40 overflow-y-auto whitespace-pre-wrap">
              {profile.resume_text}
            </div>
          </div>
        )}
      </div>

      {/* Save */}
      {saveError && (
        <p className="text-sm text-red-400 flex items-center gap-1">
          <X className="w-4 h-4" /> {saveError}
        </p>
      )}
      {saveSuccess && (
        <p className="text-sm text-emerald-400">Profile saved successfully.</p>
      )}

      <button
        type="submit"
        disabled={saving}
        className="flex items-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium transition-all"
      >
        {saving ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Save className="w-4 h-4" />
        )}
        {saving ? 'Saving…' : 'Save Profile'}
      </button>
    </form>
  );
}
