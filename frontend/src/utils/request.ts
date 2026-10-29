import axios from "axios";
import qs from "qs";
import {inject} from "vue";

/**
 * 请求 设置
 */
const serverConfig = {
    baseURL: "", // 同源相对路径，/api 由 vite dev proxy 转发到后端
    useTokenAuthorization: false, // 是否开启 token 认证
    AuthorizationField: "Authorization" // Token 字段
};

// 创建 axios 请求实例
const request = axios.create({
  baseURL: serverConfig.baseURL, // 基础请求地址
  timeout: 10000, // 请求超时设置
  withCredentials: false, // 跨域请求是否需要携带 cookie
});


// 创建请求拦截
request.interceptors.request.use(
  (config) => {
    // 如果开启 token 认证
    if (serverConfig.useTokenAuthorization) {
      config.headers[serverConfig.AuthorizationField] = localStorage.getItem("token"); // 请求头携带 token
    }
    // 设置请求头
    if(!config.headers["content-type"]) { // 如果没有设置请求头
      if(config.method === 'post' && !(config.data instanceof FormData)) {
        config.headers["content-type"] = "application/x-www-form-urlencoded"; // post 请求
        config.data = qs.stringify(config.data); // 序列化,比如表单数据
      } else if (!(config.data instanceof FormData)) {
        config.headers["content-type"] = "application/json"; // 默认类型
      }
    }
    console.log("请求配置", config);
    return config;
  },
  (error) => {
    Promise.reject(error);
  }
);


// 创建响应拦截
request.interceptors.response.use(
  (res) => {
    let data = res;
    // 处理自己的业务逻辑，比如判断 token 是否过期等等
    // 代码块
    return data;
  },
  (error) => {
    const message = (window as any).message;
    let msg = "";
    if (error && error.response) {
      switch (error.response.status) {
        case 302:
          msg = "接口重定向了！";
          break;
        case 400:
          msg = "参数不正确！";
          break;
        case 401:
          msg = "您未登录，或者登录已经超时，请先登录！";
          break;
        case 403:
          msg = "您没有权限操作！";
          break;
        case 404:
          msg = `请求地址出错: ${error.response.config.url}`;
          break;
        case 408:
          msg = "请求超时！";
          break;
        case 409:
          msg = "系统已存在相同数据！";
          break;
        case 500:
          msg = "服务器内部错误！";
          break;
        case 501:
          msg = "服务未实现！";
          break;
        case 502:
          msg = "网关错误！";
          break;
        case 503:
          msg = "服务不可用！";
          break;
        case 504:
          msg = "服务暂时无法访问，请稍后再试！";
          break;
        case 505:
          msg = "HTTP 版本不受支持！";
          break;
        default:
          msg = "异常问题，请联系管理员！";
          break;
      }
    }
    message.error(error.message);
    return Promise.reject(msg);
  }
);

export default request