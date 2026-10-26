<template>
  <n-config-provider :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { zhCN, dateZhCN } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'

const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#3370ff',
    primaryColorHover: '#4a82ff',
    primaryColorPressed: '#2a5ee6',
    primaryColorSuppl: '#3370ff',
    infoColor: '#3370ff',
    infoColorHover: '#4a82ff',
    borderRadius: '8px',
    fontSize: '14px'
  }
}
</script>
