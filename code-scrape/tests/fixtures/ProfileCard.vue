<template>
  <div class="card">
    <!-- 卡片标题 -->
    <span>{{ title }}</span>
  </div>
</template>

<script>
// 组件逻辑
export default {
  props: ["title"],
  data() {
    return { count: 0 }; // 计数
  },
};
</script>

<style scoped>
.card {
  color: red; /* 主色 */
}
</style>
