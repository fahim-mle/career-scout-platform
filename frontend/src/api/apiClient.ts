import axios, { AxiosError, AxiosResponse } from 'axios'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    if (import.meta.env.DEV) {
      console.error('API Error:', error.response?.data || error.message)
    } else {
      console.error('API Error:', error.message)
    }
    return Promise.reject(error)
  }
)

export default apiClient
