<template>
  <a-layout>
    <a-layout-sider v-model:collapsed="collapsed" :trigger="null" collapsible>
      <div class="logo" />
      <a-menu v-model:selectedKeys="selectedKeys" theme="dark" mode="inline" @click="menuClickEvent">
        <a-menu-item v-for="item in menuItems" :key="item.path">
<!--          <a-icon> {{ item.icon }} </a-icon>-->
          {{ item.title }}
        </a-menu-item>
      </a-menu>
    </a-layout-sider>
    <a-layout>
      <a-layout-header style="background: #fff;">
        <menu-unfold-outlined
          v-if="collapsed"
          class="trigger"
          @click="() => (collapsed = !collapsed)"
        />
        <menu-fold-outlined v-else class="trigger" @click="() => (collapsed = !collapsed)" />
      </a-layout-header>
      <a-layout-content
        :style="{ margin: '24px 16px', padding: '24px', background: '#fff', minHeight: '280px' }"
      >
        <router-view/>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>
<script lang="ts" setup>
import { ref } from 'vue';
import {
  UserOutlined,
  VideoCameraOutlined,
  UploadOutlined,
  MenuUnfoldOutlined,
  MenuFoldOutlined,
} from '@ant-design/icons-vue';
const collapsed = ref<boolean>(false);
import {useRouter} from "vue-router"

const router = useRouter()


const menuItems = ref([
  {
    key: "Home",
    title: "Home",
    path: "/admin",
    icon: UserOutlined,
  },
  {
    key: "MeetingRoom",
    title: "Meeting Room",
    path: "/admin/userMgt"
  },
  {
    key: "AccessibilityTest",
    title: "App Accessibility Testing",
    path: "/admin/accessibilityTest"
  }
])
const selectedKeys = ref<string[]>([router.currentRoute.value.path]);
const menuClickEvent = function (item: any) {
  if (router.currentRoute.value.path !== item.key){
    router.push(item.key)
    console.log(selectedKeys.value)
  }
}

</script>
<style>
#components-layout-demo-custom-trigger .trigger {
  font-size: 18px;
  line-height: 64px;
  padding: 0 24px;
  cursor: pointer;
  transition: color 0.3s;
}

#components-layout-demo-custom-trigger .trigger:hover {
  color: #1890ff;
}

#components-layout-demo-custom-trigger .logo {
  height: 32px;
  background: rgba(255, 255, 255, 0.3);
  margin: 16px;
}

.site-layout .site-layout-background {
  background: #fff;
}

.logo {
  height: 32px;
  margin: 16px;
  background: rgba(255, 255, 255, 0.3);
}

</style>
