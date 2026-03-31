import axios from 'axios';
import { useCallback, useState } from 'react';
import {
  createProfile,
  getProfile,
  updateProfile,
  uploadCV,
} from '../api/profile';
import type { Profile, ProfileCreate, ProfileUpdate } from '../types/profile';

interface ApiErrorPayload {
  detail?: string;
}

const getErrorDetail = (error: unknown): string | null => {
  if (!axios.isAxiosError(error)) return null;
  const data = error.response?.data as ApiErrorPayload | undefined;
  return typeof data?.detail === 'string' ? data.detail : null;
};

export const useProfile = () => {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const fetchProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getProfile();
      setProfile(data);
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        setProfile(null);
      } else {
        setError(getErrorDetail(err) || 'Failed to load profile');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const saveProfile = useCallback(
    async (data: ProfileCreate | ProfileUpdate) => {
      setSaving(true);
      setSaveError(null);
      try {
        const saved = profile
          ? await updateProfile(data as ProfileUpdate)
          : await createProfile(data as ProfileCreate);
        setProfile(saved);
        return saved;
      } catch (err) {
        const msg = getErrorDetail(err) || 'Failed to save profile';
        setSaveError(msg);
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [profile],
  );

  const uploadCVFile = useCallback(async (file: File) => {
    setUploading(true);
    setUploadError(null);
    try {
      const updated = await uploadCV(file);
      setProfile(updated);
      return updated;
    } catch (err) {
      const msg = getErrorDetail(err) || 'Failed to upload CV';
      setUploadError(msg);
      throw err;
    } finally {
      setUploading(false);
    }
  }, []);

  return {
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
  };
};
