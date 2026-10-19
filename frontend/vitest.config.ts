import { defineConfig } from 'vitest/config'
import { resolve } from 'path'

// 与 vite.config.ts 分开：测试不需要 vue 插件（三个 composable 都是纯 TS），
// 但需要 happy-dom 提供 document/location，以及 @ 别名。
export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/__tests__/**/*.spec.ts']
  }
})
