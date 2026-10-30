# CT Testhub 二次开发说明

> 基线：开源项目 **TestHub**（Django 4.2 + DRF + Vue 3，GPL-3.0），原项目地址 <https://github.com/chenjigang4167/testhub_platform>。
> 本仓库在其基础上做二次开发，品牌改为 **CT Testhub**，新增「源码分析 → 用例生成」模块。

## 一、新增模块：源码分析 → 用例生成

### 后端 `apps/source_analysis/`

| 文件 | 作用 |
|---|---|
| `analyzer.py` | 静态解析：遍历目录、识别 Spring Boot、抽取 `@RequestMapping` / `@GetMapping` / `@PostMapping`、`@RequestBody` DTO 字段与校验注解、`schema.sql` 表结构、JWT 鉴权标记 |
| `generator.py` | 用例生成：优先调用平台「统一配置中心」的 writer 模型配置，失败时回退规则模板 |
| `models.py` | `AnalysisJob`（分析任务）、`GeneratedCase`（生成用例）两张表 |
| `views.py` | 4 个 REST 接口：分析、任务列表、任务详情、导入项目 |
| `urls.py` | 挂载到 `/api/source-analysis/` |

### 接线
- `backend/settings.py`：`LOCAL_APPS` 注册 `apps.source_analysis`
- `backend/urls.py`：新增 `path('api/source-analysis/', ...)`

### 前端
- 新增 `src/views/source-analysis/SourceAnalysis.vue`
- `src/router/index.js`：新增 `/ai-generation/source-analysis`
- `src/layout/index.vue`：侧边栏「AI 用例生成」组内新增入口（置顶）

## 二、界面与品牌改造（CT Testhub）

| 文件 | 改动 |
|---|---|
| `src/assets/css/global.scss` | 深蓝主题变量、卡片 / 按钮 / 表格样式 |
| `src/layout/index.vue` | 侧边栏改为深蓝渐变、选中态高亮、新 logo 与品牌字、菜单顺序调整 |
| `src/views/Home.vue` | 首页新增品牌区与「源码分析」入口卡片、主按钮，背景调整 |
| `src/views/auth/Login.vue` | 登录页品牌名改为 CT Testhub |
| `index.html` | 标题改为 `CT Testhub - 智能测试平台`，favicon 指向新图标 |
| `src/assets/images/logo-mark.svg` | 新增矢量 logo |
| `public/favicon.svg` | 新增浏览器地址栏图标 |

## 三、清理

- 删除 README 中的代理广告段落、交流群 / 官网二维码、作者公众号署名
- 删除 `static_files/` 下 3 张广告与二维码图片（约 4.2 MB）
- 删除 `.idea/`、53 个 `__pycache__/`、运行日志、`.env.bak`、`requirements_full.txt`、废弃示例脚本 `docs/demo_pyzbar.py`

## 四、接口说明

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/source-analysis/analyze/` | 入参 `{"path": "本地项目路径"}`，同步执行分析并生成用例 |
| GET | `/api/source-analysis/jobs/` | 最近 20 条分析任务 |
| GET | `/api/source-analysis/jobs/<id>/` | 任务详情（含接口清单与用例） |
| POST | `/api/source-analysis/jobs/<id>/import/` | 把用例导入项目；不传 `project_id` 时自动创建项目 |

## 五、数据表

| 表名 | 说明 |
|---|---|
| `sa_analysis_job` | 分析任务：路径、框架、状态、接口清单 JSON、统计信息、生成方式 |
| `sa_generated_case` | 生成用例：模块、方法、路径、标题、场景、优先级、步骤、预期、是否已导入 |

## 六、使用方式

0. 首次运行：`python manage.py makemigrations && python manage.py migrate`（本仓库按上游惯例不提交 migrations，克隆后需先生成）
1. 启动后端（`python manage.py runserver`）与前端（`npm run dev`）
2. 登录后进入「AI 用例生成 → 源码分析生成用例」
3. 输入本地项目路径，例如 `C:\Users\HP\Desktop\pingjian-ai-assistant-lc`
4. 点击「开始分析」，等待解析与生成完成
5. 查看接口清单与生成用例，点击「导入到项目」

## 七、验证记录

对 `pingjian-ai-assistant-lc`（Spring Boot 3.5）实测：

- 扫描文件：88 个
- 识别接口：21 个（含请求体 DTO、query/path 参数、鉴权标记）
- 生成用例：59 条（约 21.8 秒，走 DeepSeek）
- 导入结果：59 条用例写入项目「源码分析 · pingjian-ai-assistant-lc」

## 八、已知边界

- 当前只解析 **Spring Boot（Java 注解）** 项目，Django / Express 需另加解析器
- 分析为同步执行，接口较多时约 20–30 秒
- 大模型不可用时自动回退规则模板，界面会标注「规则兜底生成」
- 尚未向上游 TestHub 提交 PR，本仓库为独立二次开发版本

## 九、配置说明

- 模型配置在平台「统一配置中心」中维护（角色 `writer`），不写入仓库
- `.env` 已被 `.gitignore` 忽略，请勿提交真实密钥
- 保留上游 `LICENSE`（GPL-3.0）
