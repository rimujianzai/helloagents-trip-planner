<template>
  <a-card id="budget" title="💰 预算明细" :bordered="false" class="budget-card">
    <div class="budget-grid">
      <div class="budget-item">
        <div class="budget-label">景点门票</div>
        <div class="budget-value">¥{{ budget.total_attractions }}</div>
      </div>
      <div class="budget-item">
        <div class="budget-label">酒店住宿</div>
        <div class="budget-value">¥{{ budget.total_hotels }}</div>
      </div>
      <div class="budget-item">
        <div class="budget-label">餐饮费用</div>
        <div class="budget-value">¥{{ budget.total_meals }}</div>
      </div>
      <div class="budget-item">
        <div class="budget-label">交通费用</div>
        <div class="budget-value">¥{{ budget.total_transportation }}</div>
      </div>
    </div>
    <div class="budget-total">
      <span class="total-label">预估总费用</span>
      <span class="total-value">¥{{ budget.total }}</span>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import type { Budget } from '@/types'

// 纯展示组件：预算数据由父组件（Result.vue）负责重算，
// 这里只负责排版 —— 删除景点后 total 变了这里自动跟着变。
defineProps<{ budget: Budget }>()
</script>

<style scoped>
.budget-card {
  height: fit-content;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.budget-item {
  text-align: center;
  padding: 12px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.budget-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.budget-value {
  font-size: 20px;
  font-weight: 700;
  color: #1890ff;
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  color: white;
}

.total-label {
  font-size: 16px;
  font-weight: 600;
}

.total-value {
  font-size: 28px;
  font-weight: 700;
}
</style>
