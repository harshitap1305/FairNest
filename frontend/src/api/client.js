import axios from 'axios'

// ─── Token store (in-memory only) ───────────────────────────────────────────
let _accessToken = null

export function setToken(token) {
  _accessToken = token
}

export function getToken() {
  return _accessToken
}

export function generateIdempotencyKey() {
  return crypto.randomUUID()
}

// ─── Axios instance ──────────────────────────────────────────────────────────
const client = axios.create({
  baseURL: '/api/v1',
  withCredentials: true, // send httpOnly refresh cookie
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
})

// Request interceptor: attach access token & handle FormData multipart headers
client.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Track whether a refresh is in-flight to avoid multiple concurrent refreshes
let _refreshPromise = null

// Response interceptor: silent refresh on 401
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (
      error.response?.status === 401 &&
      !originalRequest?._retried &&
      !originalRequest?.url?.includes('/auth/refresh') &&
      !originalRequest?.url?.includes('/auth/login')
    ) {
      originalRequest._retried = true

      try {
        if (!_refreshPromise) {
          _refreshPromise = client
            .post('/auth/refresh')
            .then((res) => {
              const newToken = res.data?.access_token
              if (newToken) setToken(newToken)
              return newToken
            })
            .finally(() => {
              _refreshPromise = null
            })
        }

        const newToken = await _refreshPromise
        if (newToken) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return client(originalRequest)
        }
      } catch (_refreshError) {
        setToken(null)
        window.dispatchEvent(new CustomEvent('auth:logout'))
        return Promise.reject(_refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default client
