# CT Testhub

基于开源测试管理平台 **TestHub** 的二次开发版本，用于自动化自测练习。

- 原项目：TestHub（GPL-3.0）— <https://github.com/chenjigang4167/testhub_platform>
- 本仓库：CT Testhub，在上游代码基础上做了以下改动

## 本仓库做了什么

1. **新增「源码分析 → 用例生成」模块**：输入本地 Spring Boot 项目路径，静态解析接口与 DTO 字段，调用平台模型配置生成测试用例，一键导入用例库。
2. **界面改版**：深蓝主题，首页入口调整。

详细改动见 [CHANGELOG-CT.md](./CHANGELOG-CT.md)。

## 技术栈

- 后端：Django 4.2 + Django REST Framework，MySQL 8，Redis / Celery
- 前端：Vue 3 + Vite + Element Plus
- 自动化：Selenium、Playwright、Airtest、Allure、Locust

## 快速开始

```bash
# 后端
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations && python manage.py migrate
python manage.py runserver

# 前端
cd frontend
npm install
npm run dev
```

页面地址：<http://localhost:3000>；接口文档：<http://localhost:8000/api/docs/>。

## 许可

本项目基于 GPL-3.0 许可，保留上游版权声明，详见 [LICENSE](./LICENSE)。
