// 类型定义
//
// ⚠️ 本文件是「手工镜像」：与 backend/app/models/schemas.py 一一对应。
// 改后端模型后，运行下面两条命令重新生成机器校验版，再对照 diff 修这里：
//   npm run gen:openapi   # 后端导出 openapi.json
//   npm run gen:types     # 生成 src/types/api.d.ts（勿手改，机器生成）
// api.d.ts 是 openapi-typescript 生成的「唯一真相」，本文件若与它冲突，以它为准。

export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  /** 经纬度。后端可能返回 null（数据缺失时宁可留空也不编造），渲染前需判空 */
  location?: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  ticket_price?: number
}

export interface Meal {
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  name: string
  address?: string
  location?: Location
  description?: string
  estimated_cost?: number
}

export interface Hotel {
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost?: number
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
}

export interface WeatherInfo {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number
  night_temp: number
  wind_direction: string
  wind_power: string
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
  /** true 表示后端生成失败、这是占位数据，页面必须显示醒目警告 */
  is_fallback?: boolean
  fallback_reason?: string
}

export interface TripFormData {
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
}

