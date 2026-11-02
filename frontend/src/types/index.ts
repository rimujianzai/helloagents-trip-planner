// 类型定义
//
// 数据模型（Attraction / DayPlan / TripPlan 等）不再手写，直接从
// src/types/api.d.ts 派生 —— 那个文件由 openapi-typescript 从后端的
// openapi.json 生成，是「唯一真相」。
//
// 后端改字段后跑一条命令同步：
//   npm run gen:api      # = gen:openapi + gen:types
//
// 以前这里是手写镜像，文件头虽然写着「以 api.d.ts 为准」，但实际上没人
// 真的去对照：Attraction 就漏了 photos / poi_id 两个后端会返回的字段，
// 前端想用时 TS 报「属性不存在」，还得回头翻后端代码才知道有这俩字段。
// 改成派生之后，字段一有出入编译期就报错，不依赖「记得去对」这种自觉。

import type { components } from './api'

type Schemas = components['schemas']

export type Location = Schemas['Location']
export type Attraction = Schemas['Attraction']
export type Meal = Schemas['Meal']
export type Hotel = Schemas['Hotel']
export type Budget = Schemas['Budget']
export type DayPlan = Schemas['DayPlan']
export type WeatherInfo = Schemas['WeatherInfo']
export type TripPlan = Schemas['TripPlan']
export type TripPlanResponse = Schemas['TripPlanResponse']

/**
 * 前端表单模型，刻意不从 TripRequest 派生。
 *
 * 后端 TripRequest 里 free_text_input 是 Optional（默认空串），派生过来会
 * 变成可选字段，表单这边就得处处判空。表单提交时它始终是字符串
 * （空串 = 用户没填），所以这里手写一个更严格的版本。
 */
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
