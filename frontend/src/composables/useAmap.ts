/**
 * 高德地图 composable
 *
 * 把 Result.vue 里 initMap / addAttractionMarkers / drawRoutes 这些地图逻辑从
 * 千行单文件中抽出来，组件只保留「什么时候初始化 / 什么时候重建标记」的调用。
 *
 * 关键点：地图初始中心不再写死北京（手册第 16 节 P2-9），而是取第一个有坐标的
 * 景点；只有当全部景点都没有坐标时，才回退到北京默认点（避免请求上海时地图先
 * 闪一下北京）。
 */
import AMapLoader from '@amap/amap-jsapi-loader'
import type { TripPlan } from '@/types'

interface MappedAttraction {
  name: string
  address: string
  visit_duration: number
  description: string
  location: { longitude: number; latitude: number }
  dayIndex: number
  attrIndex: number
}

const BEIJING_FALLBACK: [number, number] = [116.397128, 39.916527]

export function useAmap() {
  let map: any = null
  let AMapRef: any = null
  let markers: any[] = []
  const destroyed = { value: false }

  /** 收集所有「有坐标」的景点，附带它在行程里的 day/attr 下标 */
  function collectAttractions(plan: TripPlan): MappedAttraction[] {
    const list: MappedAttraction[] = []
    plan.days.forEach((day, dayIndex) => {
      day.attractions.forEach((attr, attrIndex) => {
        const lon = attr.location?.longitude
        const lat = attr.location?.latitude
        // 注意：用 != null 而非真值判断，经度/纬度为 0（本初子午线/赤道）是合法坐标
        if (lon != null && lat != null) {
          list.push({ ...attr, location: { longitude: lon, latitude: lat }, dayIndex, attrIndex })
        }
      })
    })
    return list
  }

  function drawRoutes(AMap: any, attractions: MappedAttraction[]) {
    if (attractions.length < 2) return
    const dayGroups: Record<number, MappedAttraction[]> = {}
    attractions.forEach((a) => {
      ;(dayGroups[a.dayIndex] ||= []).push(a)
    })
    Object.values(dayGroups).forEach((dayAttrs) => {
      if (dayAttrs.length < 2) return
      const path = dayAttrs.map((a) => [a.location.longitude, a.location.latitude])
      const polyline = new AMap.Polyline({
        path,
        strokeColor: '#1890ff',
        strokeWeight: 4,
        strokeOpacity: 0.8,
        strokeStyle: 'solid',
        showDir: true
      })
      map.add(polyline)
    })
  }

  function addAttractionMarkers(AMap: any, plan: TripPlan) {
    // 重建前先清掉旧标记，避免编辑后叠加（clearMap 会清空路线，所以下面重画）
    if (markers.length > 0) {
      map.remove(markers)
      markers = []
    }
    const all = collectAttractions(plan)
    if (all.length === 0) return

    // InfoWindow 是浮层，同一时刻只显示一个，全局建一个复用即可
    const infoWindow = new AMap.InfoWindow({ offset: new AMap.Pixel(0, -30) })

    markers = all.map((attr, index) => {
      const marker = new AMap.Marker({
        position: [attr.location.longitude, attr.location.latitude],
        title: attr.name,
        label: {
          content: `<div style="background: #4CAF50; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">${index + 1}</div>`,
          offset: new AMap.Pixel(0, -30)
        }
      })
      marker.on('click', () => {
        infoWindow.setContent(`
          <div style="padding: 10px;">
            <h4 style="margin: 0 0 8px 0;">${attr.name}</h4>
            <p style="margin: 4px 0;"><strong>地址:</strong> ${attr.address}</p>
            <p style="margin: 4px 0;"><strong>游览时长:</strong> ${attr.visit_duration}分钟</p>
            <p style="margin: 4px 0;"><strong>描述:</strong> ${attr.description}</p>
            <p style="margin: 4px 0; color: #1890ff;"><strong>第${attr.dayIndex + 1}天 景点${attr.attrIndex + 1}</strong></p>
          </div>
        `)
        infoWindow.open(map, marker.getPosition())
      })
      return marker
    })

    map.add(markers)
    map.setFitView(markers) // 自动调整视野，包含所有标记
    drawRoutes(AMap, all)
  }

  /** 初始化地图。返回是否成功（失败时不抛异常，由调用方提示） */
  async function initMap(plan: TripPlan): Promise<boolean> {
    try {
      const AMap = await AMapLoader.load({
        key: import.meta.env.VITE_AMAP_WEB_JS_KEY,
        version: '2.0',
        plugins: ['AMap.Marker', 'AMap.Polyline', 'AMap.InfoWindow']
      })
      AMapRef = AMap

      const all = collectAttractions(plan)
      const center = all.length > 0 ? [all[0].location.longitude, all[0].location.latitude] : BEIJING_FALLBACK

      map = new AMap.Map('amap-container', {
        zoom: 12,
        center,
        viewMode: '3D'
      })

      addAttractionMarkers(AMap, plan)
      return true
    } catch (error) {
      console.error('地图加载失败:', error)
      return false
    }
  }

  /** 编辑保存后只重建覆盖物，不销毁地图（保留缩放/拖动位置） */
  function refreshMarkers(plan: TripPlan) {
    if (!map || !AMapRef) return
    map.clearMap()
    markers = []
    addAttractionMarkers(AMapRef, plan)
  }

  /** 组件卸载时调用：销毁地图实例与事件监听 */
  function destroy() {
    destroyed.value = true
    if (map) {
      map.destroy()
      map = null
    }
    markers = []
  }

  return { initMap, refreshMarkers, destroy }
}
