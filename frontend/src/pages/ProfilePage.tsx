import { Loader2 } from 'lucide-react';
import { useEffect } from 'react';
import { ProfileForm } from '../components/profile/ProfileForm';
import { useProfile } from '../hooks/useProfile';

const ProfilePage = () => {
  const {
    profile,
    loading,
    saving,
    uploading,
    error,
    saveError,
    uploadError,
    fetchProfile,
    saveProfile,
    uploadCVFile,
  } = useProfile();

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const completedFields = profile
    ? [
        profile.name,
        profile.location,
        profile.experience_years != null,
        profile.skills?.length,
        profile.resume_text,
      ].filter(Boolean).length
    : 0;
  const totalFields = 5;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-3xl font-bold text-white">My Profile</h2>
          <p className="text-slate-400 mt-1">
            Manage your professional information and preferences.
          </p>
        </div>
        {profile && (
          <div className="text-right">
            <p className="text-xs text-slate-500 mb-1">Profile completion</p>
            <div className="flex items-center gap-2">
              <div className="w-32 h-1.5 bg-white/10 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-500 rounded-full transition-all"
                  style={{
                    width: `${(completedFields / totalFields) * 100}%`,
                  }}
                />
              </div>
              <span className="text-xs text-slate-400">
                {Math.round((completedFields / totalFields) * 100)}%
              </span>
            </div>
          </div>
        )}
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
        </div>
      )}

      {error && (
        <div className="glass-card p-4 border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {!loading && !error && (
        <ProfileForm
          profile={profile}
          saving={saving}
          uploading={uploading}
          saveError={saveError}
          uploadError={uploadError}
          onSave={saveProfile}
          onUploadCV={uploadCVFile}
        />
      )}
    </div>
  );
};

export default ProfilePage;
