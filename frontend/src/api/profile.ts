import apiClient from './apiClient';
import { Profile, ProfileCreate, ProfileUpdate } from '../types/profile';

export async function getProfile(): Promise<Profile> {
  const response = await apiClient.get<Profile>('/profile');
  return response.data;
}

export async function createProfile(data: ProfileCreate): Promise<Profile> {
  const response = await apiClient.post<Profile>('/profile', data);
  return response.data;
}

export async function updateProfile(data: ProfileUpdate): Promise<Profile> {
  const response = await apiClient.patch<Profile>('/profile', data);
  return response.data;
}

export async function uploadCV(file: File): Promise<Profile> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<Profile>('/profile/cv', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}
