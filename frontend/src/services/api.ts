import axios from 'axios'
import type { TripFormData, TripPlanResponse } from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 2分钟超时
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 生成旅行计划
 */
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

/**
 * 获取景点配图
 *
 * 统一走 apiClient 而不是在组件里 fetch 绝对地址：
 * 组件里写死 http://localhost:8000 在本地开发时看不出问题，
 * 一部署到服务器就会全部失败（而且只报 CORS/连接错误，很难定位）。
 *
 * 配图属于"锦上添花"，失败不该影响主流程，所以这里吞掉异常返回 null，
 * 由调用方走占位图。超时也单独收窄到 15s，避免拖住页面。
 */
export async function getAttractionPhoto(name: string): Promise<string | null> {
  try {
    const response = await apiClient.get('/api/poi/photo', {
      params: { name },
      timeout: 15000
    })
    const payload = response.data
    if (payload?.success && payload?.data?.photo_url) {
      return payload.data.photo_url as string
    }
    return null
  } catch (error) {
    console.warn(`获取「${name}」配图失败，使用占位图`, error)
    return null
  }
}

export default apiClient

