const routes = [
    {
        path: '',
        redirect: "/user"
    },
    {
        path: '/login',
        component: () =>import("../view/Login/index.vue")
    },
    {
        path: '/admin',
        name: 'AdminLayout',
        title: '管理员首页',
        children: [
            {
                path: '',
                component: () => import("../view/AdminHome/index.vue"),
                title: '管理员首页',
                meta:{
                    layout:"admin"
                }
            },
            {
                path: 'userMgt',
                component: () => import("../view/UserMgt/index.vue"),
                title: '管理员首页',
                meta:{
                    layout:"admin"
                }
            },
            {
                path: 'accessibilityTest',
                component: () => import("../view/AccessibilityTest/index.vue"),
                title: 'App Accessibility Testing',
                meta:{
                    layout:"admin"
                }
            },
        ],
    },
    {
        path: '/user',
        name: 'UserHome',
        title: '用户首页',
        children: [
            {
                path: '',
                title: '用户首页',
                component: () => import("../view/Home/index.vue"),
                meta:{
                    layout:"user"
                }
            },
            {
                path: 'product',
                title: '商品页Demo',
                component: () => import("~/components/ProductArea.vue"),
                meta:{
                    layout:"user"
                }
            },
            {
                path: 'accordion',
                title: '嵌套手风琴组件',
                component: () => import("~/components/Accordion.vue"),
                meta:{
                    layout:"user"
                }
            },
            {
                path: 'banner',
                title: 'Banner',
                component: () => import("~/components/Banner.vue"),
                meta:{
                    layout:"user"
                }
            },
            {
                path: 'selectDevice',
                component: () => import("../view/MeetingRoom/index.vue"),
                meta:{
                    layout:"user"
                }
            },
        ],
    }
]
export default routes