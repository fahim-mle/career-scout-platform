export interface Profile {
  id: number
  name: string
  location: string
  experience_years: number
  skills: string[]
  preferences: Record<string, unknown> | null
  resume_text: string | null
  created_at: string
  updated_at: string
}

export interface ProfileCreate {
  name: string
  location: string
  experience_years: number
  skills: string[]
  preferences?: Record<string, unknown>
  resume_text?: string
}

export type ProfileUpdate = Partial<ProfileCreate>
