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

/** SSE 事件结构（与后端 trip.py 的 emit 一一对应） */
export interface PlanStreamEvent {
  stage: string
  percent: number
  status: string
  /** 仅在 stage === 'done' 时存在，结构与 /plan 的响应体一致 */
  data?: TripPlanResponse
}

/**
 * 流式生成旅行计划（SSE 真实进度）
 *
 * 为什么不用 EventSource：
 *   EventSource 只支持 GET，且无法携带请求体。旅行需求是一个 JSON 对象，
 *   塞进 query string 既难读又会超长，所以改用 fetch + ReadableStream
 *   手动解析 SSE 协议（服务端仍然是标准的 text/event-stream）。
 *
 * 参数 onEvent：
 *   每收到一条进度事件回调一次。注意三路并行搜索的完成顺序不固定，
 *   percent 可能出现 48 早于 38 到达的情况，调用方应取最大值渲染。
 */
export async function generateTripPlanStream(
  formData: TripFormData,
  onEvent: (event: PlanStreamEvent) => void,
  signal?: AbortSignal
): Promise<TripPlanResponse> {
  const response = await fetch(`${API_BASE_URL}/api/trip/plan-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(formData),
    signal
  })

  if (!response.ok) {
    throw new Error(`生成旅行计划失败 (HTTP ${response.status})`)
  }
  if (!response.body) {
    // 老浏览器 / 被 polyfill 拦截的情况，让调用方降级到普通接口
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalResult: TripPlanResponse | null = null

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以空行分隔事件；最后一段可能不完整，留在 buffer 里等下一轮
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() ?? ''

      for (const chunk of chunks) {
        // 心跳是 ": keep-alive" 注释行，没有 data: 前缀，直接跳过
        const dataLines = chunk
          .split('\n')
          .filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trim())
        if (dataLines.length === 0) continue

        let event: PlanStreamEvent
        try {
          event = JSON.parse(dataLines.join('\n'))
        } catch {
          // 单条事件解析失败不应中断整个流
          continue
        }

        if (event.stage === 'error') {
          throw new Error(event.status || '生成旅行计划失败')
        }
        if (event.stage === 'done' && event.data) {
          finalResult = event.data
        }
        onEvent(event)
      }
    }
  } finally {
    // 正常读完或抛错都要释放 reader，否则连接可能一直挂着
    reader.releaseLock()
  }

  if (!finalResult) {
    throw new Error('未收到完整的行程数据')
  }
  return finalResult
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
    const response = await apiClient.get('/api/map/photo', {
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

