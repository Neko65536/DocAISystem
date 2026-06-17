import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

client.interceptors.request.use((config) => {
  const token = window.localStorage.getItem('access_token')
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      console.warn('收到 401 响应，保留 token 由登出操作清除')
    }
    const message = error.response?.data?.error?.message || error.message
    return Promise.reject(new Error(message))
  }
)

export default client
