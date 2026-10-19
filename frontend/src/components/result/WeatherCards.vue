<template>
  <a-card id="weather" title="天气信息" style="margin-top: 20px" :bordered="false">
    <a-list :data-source="weatherInfo" :grid="{ gutter: 16, column: 3 }">
      <template #renderItem="{ item }">
        <a-list-item>
          <a-card size="small" class="weather-card">
            <div class="weather-date">{{ item.date }}</div>
            <div class="weather-info-row">
              <span class="weather-icon">☀️</span>
              <div>
                <div class="weather-label">白天</div>
                <div class="weather-value">{{ item.day_weather }} {{ item.day_temp }}°C</div>
              </div>
            </div>
            <div class="weather-info-row">
              <span class="weather-icon">🌙</span>
              <div>
                <div class="weather-label">夜间</div>
                <div class="weather-value">{{ item.night_weather }} {{ item.night_temp }}°C</div>
              </div>
            </div>
            <div class="weather-wind">
              💨 {{ item.wind_direction }} {{ item.wind_power }}
            </div>
          </a-card>
        </a-list-item>
      </template>
    </a-list>
  </a-card>
</template>

<script setup lang="ts">
import type { WeatherInfo } from '@/types'

// 纯展示组件。id="weather" 供侧边导航滚动定位用，必须保留在根卡片上。
defineProps<{ weatherInfo: WeatherInfo[] }>()
</script>

<style scoped>
.weather-card {
  background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 100%);
  border: none !important;
  transition: all 0.3s ease;
}

.weather-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
}

.weather-date {
  font-size: 16px;
  font-weight: bold;
  color: #00796b;
  margin-bottom: 12px;
  text-align: center;
}

.weather-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.weather-icon {
  font-size: 24px;
}

.weather-label {
  font-size: 12px;
  color: #666;
}

.weather-value {
  font-size: 16px;
  font-weight: 600;
  color: #00796b;
}

.weather-wind {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(0, 121, 107, 0.2);
  text-align: center;
  color: #00796b;
  font-size: 14px;
}
</style>
