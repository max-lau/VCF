import axios from 'axios'
import { useToast } from '@/composables/useToast'

const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Attach JWT on every request
client.interceptors.request.use(config => {
  const token = localStorage.getItem('paraiq_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Human-readable messages for common HTTP errors
function errorMessage(err) {
  const status = err.response?.status
  const detail = err.response?.data?.detail || err.response?.data?.message

  if (!status) return 'Network error — check your connection.'

  const MAP = {
    400: detail || 'Bad request — check your input.',
    403: 'You don\'t have permission to do that.',
    404: 'Resource not found.',
    408: 'Request timed out.',
    422: detail || 'Validation error — check your input.',
    429: 'Too many requests — slow down.',
    500: 'Server error — try again shortly.',
    502: 'Server unavailable — try again shortly.',
    503: 'Service temporarily unavailable.',
  }
  return MAP[status] || `Unexpected error (${status}).`
}

// On error: 401 clears session; everything else fires a toast
client.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('paraiq_token')
      localStorage.removeItem('paraiq_user')
      window.location.href = '/login'
      return Promise.reject(err)
    }

    // Don't toast on intentional silent calls
    if (err.config?._silent) return Promise.reject(err)

    const { toast } = useToast()
    const status = err.response?.status
    const type = status >= 500 ? 'error' : status === 403 ? 'warning' : 'error'
    toast[type](errorMessage(err))

    return Promise.reject(err)
  }
)

export default client
