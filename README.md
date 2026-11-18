# Agentic Job Search Copilot

> 当前版本：`0.3.0`。V1 负责邮件自动化，V2 增加求职 CRM 与匹配分析，V3 增加带人工审批边界的目标驱动 Agent。

> 隐私提示：仓库只应提交源码和虚构示例。不要提交 `.env`、真实简历、邮件、日志、数据库、求职记录或飞书数据。详见 [SECURITY.md](SECURITY.md)。

提交前可运行 `powershell -ExecutionPolicy Bypass -File scripts\privacy_check.ps1`，检查 Git 已跟踪文件中是否混入运行数据或常见密钥格式。

这是一个可本地运行的 Windows/Python V1 求职自动化工作流：

```text
网易 163/126 邮箱（IMAP SSL）
        ↓
按关键词做低成本初筛
        ↓
OpenAI-compatible AI 把邮件解析为固定 JSON
        ↓
Pydantic schema 严格校验
        ↓
按 Application ID 新增或更新飞书多维表格
        ↓
若为面试且时间明确，创建或更新飞书日历事件
        ↓
SQLite 记录 Message-ID、record_id、event_id，防止重复
```

V1 遵循一个关键边界：**AI 只负责理解邮件并输出数据，Python 程序负责校验和执行。** AI 不会直接拿到邮箱授权码、飞书 App Secret，也不能任意调用飞书操作。

## 1. 当前实现的能力

- IMAP SSL 连接网易 163 或 126 邮箱，可配置主机、端口、邮箱目录、回看天数和是否只读未读邮件。
- MIME 邮件解析：主题编码、纯文本、HTML 降级、发件人、收件人、发送时间和 `Message-ID`。
- 网易兼容：登录后发送 RFC 2971 IMAP `ID`，避免 163/126 返回 `Unsafe Login`。
- 规则初筛求职邮件，减少无关邮件进入 AI，降低费用与误操作概率。
- 确定性排除验证码、面试满意度问卷和面试体验反馈，避免被 AI 误判成面试事件。
- 可替换的 AI Provider 接口；默认实现调用 OpenAI-compatible `/chat/completions`。
- AI JSON 经过 Pydantic 严格校验：非法类型、多余字段、错误日期或超出 0~1 的置信度会失败，不会写飞书。
- 飞书自建应用 `tenant_access_token` 自动获取并在进程内缓存。
- 飞书多维表格记录列表查询、新增和更新。
- 面试日程创建和更新；创建时使用稳定的 idempotency key，并保存 `event_id`。
- 本地 SQLite 幂等状态、轮转日志、单封失败不阻断整批、失败邮件下次可重试。
- `dry-run`：读取和解析，但不写飞书、不写“已处理”状态。
- 本地 `.eml` 样例、Mock AI 和 pytest；测试不需要真实邮箱、AI 或飞书 API。

当前暂不包含：自动投递、自动联系招聘者、招聘网站登录、验证码绕过、附件 OCR、图形界面和长期常驻服务。

## 2. 项目目录与每个文件的用途

```text
D:\AgenticJobSearchCopilot
├─ .env.example                   配置模板，不含真实凭据
├─ .gitignore                     防止 .env、日志、数据库、虚拟环境入库
├─ requirements.txt               运行、测试和静态检查依赖
├─ pyproject.toml                 包元数据、命令入口、pytest/ruff 配置
├─ README.md                      本说明
├─ data\
│  ├─ candidate_profile_input.example.md  虚构简历模板
│  ├─ search_goal_input.example.json      搜索目标模板
│  ├─ state.db                    首次运行后生成且不会提交的 SQLite 状态库
│  └─ logs\workflow.log           首次运行后生成且不会提交的轮转日志
├─ scripts\
│  ├─ setup.ps1                   创建 venv、安装依赖、复制 .env、自检
│  ├─ run_once.ps1                供手动运行或任务计划程序调用
│  └─ run_mock.py                 完全离线的演示脚本
├─ src\job_workflow\
│  ├─ cli.py                      命令行入口、模式校验、组件组装
│  ├─ config.py                   从 .env 读取配置
│  ├─ logging_config.py           控制台与滚动文件日志
│  ├─ models\                     邮件对象、AI schema、枚举、Application ID
│  ├─ email_client\               IMAP 客户端、MIME 解析、规则过滤
│  ├─ ai\                         Provider 协议、提示词、兼容 API、Mock
│  ├─ feishu\                     Token、多维表格、Calendar API
│  ├─ state\                      SQLite 幂等状态
│  └─ workflow\                   主流程和异常隔离
└─ tests\
   ├─ fixtures\                   面试邮件和非求职邮件样例
   ├─ test_email.py               MIME 与规则测试
   ├─ test_models.py              schema 与稳定 ID 测试
   └─ test_workflow.py            写表/建日程/重复邮件的假客户端测试
```

## 3. 外部工具分别做什么

### Python

负责整个流程编排。建议 Python 3.9 以上。项目当前机器检测到的是 Python 3.9.13，因此代码与依赖范围按这个版本设计。

### IMAP

IMAP 是读取邮箱的标准协议。本项目使用 Python 标准库 `imaplib.IMAP4_SSL`，端口默认 993。SSL 表示登录和邮件内容在网络传输时加密。程序以 `readonly=True` 打开邮箱，不会把邮件标为已读，也不会删除或移动邮件。

### OpenAI-compatible API

它不是限定某一家模型厂商，而是要求服务提供与 `POST /v1/chat/completions` 相近的 HTTP 格式。Provider 接口位于 `ai/base.py`；以后接本地模型或其他厂商时，新建一个实现 `parse_email()` 的类即可，不必改工作流。

默认实现会发送邮件主题、发件人、发送时间和最多 20,000 字符正文，不会发送 `.env`、授权码或飞书 Secret。

### Pydantic

Pydantic 是数据校验工具。AI 即使返回了“看起来像 JSON”的内容，也必须满足固定字段、类型、日期格式和置信度范围。`extra="forbid"` 会拒绝多余字段。

### 飞书开放平台

项目通过飞书服务端 OpenAPI 操作多维表格和日历。这里使用企业自建应用的 `tenant_access_token`，适合无人值守任务；token 由 App ID 和 App Secret 换取，短期有效，程序自动重新获取，不写入磁盘。

### SQLite

SQLite 是 Python 自带的单文件数据库。`data/state.db` 只保存邮件 ID、Application ID、飞书 record ID、Calendar event ID、状态和错误，不保存邮箱正文和任何密钥。

### Windows 任务计划程序

项目本身是“运行一次后退出”的程序。周期性运行交给 Windows 任务计划程序，比自己写无限循环更容易管理、重启和查看失败记录。

## 4. 首次安装

打开 PowerShell：

```powershell
Set-Location -LiteralPath 'D:\AgenticJobSearchCopilot'
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

`setup.ps1` 的每一步：

1. `python -m venv .venv`：在项目内创建隔离环境，不污染全局 Python。
2. 升级 venv 内的 pip。
3. 从 `requirements.txt` 安装依赖。
4. 在 venv 内安装构建工具，把构建临时目录设为项目内较短的 `.tmp`，再用 `pip install --no-build-isolation -e .` 以 editable 模式安装本项目，让 `python -m job_workflow` 可用。关闭 build isolation 是为了避开部分 Windows 商店应用沙箱临时路径过长的问题，不会跳过依赖安装。
5. 若 `.env` 不存在，则复制 `.env.example`。已有 `.env` 永不覆盖。
6. 执行 `self-check`，只检查本地导入、日志目录和 SQLite，不联网。

如果公司网络不能访问 PyPI，需要给 pip 配置可用镜像；不要从来路不明的网站下载单独的 `.whl`。

## 5. `.env` 每个参数的完整解释

先编辑：

```powershell
notepad D:\AgenticJobSearchCopilot\.env
```

`.env` 已被 `.gitignore` 排除。不要把它发到聊天、提交到 Git 或截图公开。

### 运行参数

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `APP_ENV` | `development` | 环境标签，当前只用于辨识环境，预留给 V2。 |
| `DRY_RUN` | `true` | `true` 时禁止飞书写操作，也不把邮件记为处理成功。第一次必须保持 `true`。 |
| `LOG_LEVEL` | `INFO` | 日志级别：`DEBUG/INFO/WARNING/ERROR`。排错可临时改 `DEBUG`。 |
| `TIMEZONE` | `Asia/Shanghai` | 飞书日程时区。AI 的时间仍必须带 UTC offset。 |
| `STATE_DB_PATH` | `data/state.db` | SQLite 路径，相对路径以启动时工作目录为准。 |
| `LOG_DIR` | `data/logs` | 日志目录。单个日志 5 MB，最多保留 5 个备份。 |

### 网易 IMAP 参数

| 参数 | 163 邮箱 | 126 邮箱 | 含义 |
|---|---|---|---|
| `EMAIL_IMAP_HOST` | `imap.163.com` | `imap.126.com` | IMAP SSL 服务器。 |
| `EMAIL_IMAP_PORT` | `993` | `993` | SSL IMAP 标准端口。 |
| `EMAIL_USERNAME` | 完整 163 地址 | 完整 126 地址 | 例如 `name@163.com`，不能只写用户名。 |
| `EMAIL_AUTH_CODE` | 客户端授权码 | 客户端授权码 | 不是网易网页登录密码。 |
| `EMAIL_MAILBOX` | `INBOX` | `INBOX` | 要扫描的目录。若投递回执在自定义目录，改为实际 IMAP 目录名。 |
| `EMAIL_LOOKBACK_DAYS` | `7` | `7` | 每次从当前时间往前查多少天。重复窗口由 Message-ID 去重。 |
| `EMAIL_ONLY_UNSEEN` | `false` | `false` | 是否只搜索未读邮件。建议 `false`，因为其他客户端可能已自动标记已读。 |

### AI 参数

| 参数 | 示例/默认 | 含义 |
|---|---|---|
| `AI_BASE_URL` | `https://api.openai.com/v1` | 兼容服务根 URL，代码会追加 `/chat/completions`，末尾有无 `/` 都可。 |
| `AI_API_KEY` | 无 | 服务商密钥，只放 `.env`，代码不提供默认值。 |
| `AI_MODEL` | 无 | 服务商实际支持的模型名称；项目不会猜测或伪造。 |
| `AI_TIMEOUT_SECONDS` | `60` | 单次 HTTP 请求超时。网络慢可增加。 |
| `AI_TEMPERATURE` | `0` | 解析任务建议 0，让输出更稳定。 |

默认 Provider 要求接口支持 `messages`、`temperature` 和 `response_format={"type":"json_object"}`。若某兼容服务不支持 `response_format`，请在 Provider 中按该服务文档调整；不要误以为“兼容”代表所有可选参数都相同。

### 飞书参数

| 参数 | 含义 |
|---|---|
| `FEISHU_BASE_URL` | 中国版飞书默认 `https://open.feishu.cn/open-apis`；Lark 海外版不能直接沿用。 |
| `FEISHU_APP_ID` | 自建应用“凭证与基础信息”中的 App ID，通常以 `cli_` 开头。 |
| `FEISHU_APP_SECRET` | 同页的 App Secret。它等同服务器密码，只放 `.env`。 |
| `FEISHU_BITABLE_APP_TOKEN` | 指定多维表格 Base 的标识，不是 App ID。 |
| `FEISHU_BITABLE_TABLE_ID` | Base 内具体数据表的标识。一个 Base 可有多张表。 |
| `FEISHU_CALENDAR_ID` | 要创建面试事件的日历 ID，不是用户 open_id。 |
| `FEISHU_DEFAULT_EVENT_DURATION_MINUTES` | 邮件只有开始时间时的默认面试时长，默认 60 分钟。 |

## 6. 网易邮箱授权码配置

网易的 UI 可能调整，核心动作不变：

1. 登录 163 或 126 网页邮箱。
2. 进入“设置”中与 `POP3/SMTP/IMAP` 或“客户端授权密码”相关的页面。
3. 开启 IMAP/SMTP 服务。网易可能要求短信或安全验证。
4. 创建/重置客户端授权码。
5. 把授权码写入 `.env` 的 `EMAIL_AUTH_CODE`，不要填网页登录密码。
6. 163 使用 `imap.163.com:993`；126 使用 `imap.126.com:993`。

常见错误：

- `AUTHENTICATIONFAILED`：用户名不完整、填了网页登录密码、授权码有空格、IMAP 未开启或网易风控。
- 能登录但读不到：检查 `EMAIL_MAILBOX`、回看天数，以及邮件是否被规则移动到其他文件夹。
- 中文文件夹名失败：先用 `INBOX` 验证；自定义 IMAP 文件夹可能需要 modified UTF-7 编码，V1 未自动转换。

## 7. 飞书开放平台从零配置

### 7.1 创建企业自建应用

1. 打开[飞书开放平台](https://open.feishu.cn/)，进入开发者后台。
2. 创建“企业自建应用”，例如 `Job Search Workflow`。
3. 在“凭证与基础信息”复制 App ID 和 App Secret 到 `.env`。
4. 开启应用需要的能力并创建版本；按企业策略提交审核、发布，并由管理员启用/安装。

代码使用应用身份 `tenant_access_token`，不需要每次人工网页登录。飞书官方说明：token 只代表应用已获授权的能力和资源范围，并不拥有租户管理员特权。

### 7.2 申请 API 权限

在“权限管理”中按 API 搜索并申请应用身份权限，至少覆盖：

- 多维表格：读取记录、创建记录、更新记录。控制台常见的聚合显示名称类似“查看、评论、编辑和管理多维表格”。
- 日历：读取日历/日程信息，以及“更新日历和日程信息”（创建和修改事件）。

最稳妥的方法不是只照抄 scope 字符串，而是在飞书 API 文档或 API Explorer 中打开本项目实际使用的 API，让控制台显示该 API 当前要求的权限：

- `GET /bitable/v1/apps/:app_token/tables/:table_id/records`
- `POST /bitable/v1/apps/:app_token/tables/:table_id/records`
- `PUT /bitable/v1/apps/:app_token/tables/:table_id/records/:record_id`
- `GET /calendar/v4/calendars`
- `POST /calendar/v4/calendars/:calendar_id/events`
- `PATCH /calendar/v4/calendars/:calendar_id/events/:event_id`

权限展示名和 scope 可能随飞书控制台版本调整，应以 API 页面“权限要求”为准。增加权限后通常需要重新发布应用版本。

### 7.3 创建多维表格及字段

在飞书中新建一个多维表格 Base，并新建数据表 `Job Applications`。字段名必须与下表逐字一致；字段类型不一致会导致飞书返回参数错误。

| 字段名 | 推荐类型 | 用途 |
|---|---|---|
| `Application ID` | 单行文本 | 公司+岗位生成的稳定主键。必须保留。 |
| `Company` | 单行文本 | 公司名称。 |
| `Position` | 单行文本 | 岗位名称。 |
| `Current Stage` | 单行文本或单选 | 已投递/笔试/一面/Offer/拒绝等。若用单选，请预先允许对应选项。 |
| `Mail Type` | 单行文本或单选 | `application/interview/written_test/rejection/offer`。 |
| `Application Date` | 日期 | 投递日期。 |
| `Interview Time` | 日期（含时间） | 面试开始时间。 |
| `Location` | 单行文本 | 线上或地址。 |
| `Meeting Link` | URL 或单行文本 | 会议链接。若 URL 字段写入报错，先改成单行文本。 |
| `Contact Name` | 单行文本 | HR/面试联系人。 |
| `Contact Email` | 单行文本 | 联系邮箱。 |
| `Email Subject` | 单行文本 | 最近一次相关邮件主题。 |
| `Email Message ID` | 单行文本 | 最近一次邮件的 RFC Message-ID。 |
| `Source Email Sender` | 单行文本 | 来源发件人。 |
| `AI Confidence` | 数字 | 0~1。 |
| `Calendar Event ID` | 单行文本 | 已创建的飞书日程 ID，用于改期更新。 |
| `Last Updated` | 日期（含时间） | 最近同步时间。 |

如果 `Current Stage` 或 `Mail Type` 使用单选，飞书可能要求选项已存在；V1 为减少配置摩擦，推荐先用单行文本，稳定后再升级为单选。

### 7.4 获取 app_token 和 table_id

打开目标多维表格，常见 URL 类似：

```text
https://your-domain.feishu.cn/base/bascnXXXXXXXXXXXX?table=tblXXXXXXXXXXXX&view=vewXXXX
```

- `/base/` 后、`?` 前的 `bascn...` 是 `FEISHU_BITABLE_APP_TOKEN`。
- 查询参数 `table=` 后的 `tbl...` 是 `FEISHU_BITABLE_TABLE_ID`。
- `view=` 是视图 ID，本项目不需要。

不同入口的 URL 可能是 wiki 链接。若 URL 没直接显示 token，可在飞书开放平台 API Explorer 选择该 Base，或通过知识库节点解析接口获得真实 Base token。不要把 wiki node token 当 app_token。

### 7.5 给应用授予目标 Base 的资源权限

API 权限与文档资源权限是两层：

1. 开放平台“权限管理”决定应用有没有调用某类 API 的能力。
2. 目标 Base 自身的分享/高级权限决定应用能不能访问这一份具体数据。

在目标多维表格右上角的分享/更多菜单中，把自建应用添加为可编辑成员或管理员。若启用了高级权限，给应用对应数据表的读取和编辑权限。若出现 `app unauthorized`、无权访问文档或记录列表为空，优先检查这一层。

### 7.6 获取 calendar_id 并授权

推荐为 V1 建一个专用共享日历，例如“求职面试”，而不是直接操作个人主日历：

1. 在飞书日历创建专用日历。
2. 通过日历共享/ACL 让应用身份拥有 `writer` 或 `owner` 权限。企业界面若不能直接选择应用，可使用飞书 Calendar ACL API 或管理员支持的授权方式。
3. 在 API Explorer 中使用该应用的 `tenant_access_token` 调用 `GET /calendar/v4/calendars`。
4. 从返回列表找到目标日历，复制 `calendar_id` 到 `.env`。

`calendar_id` 常呈邮箱样式，但不能凭名字自行拼接。应用能看到事件不等于有编辑权；创建/更新要求当前身份对目标日历至少是 writer。

重要边界：`tenant_access_token` 代表应用身份。若你的真实目标是“直接写入某个用户的个人主日历”，更标准的方式往往是实现 OAuth 并使用 `user_access_token`。本 V1 按需求实现 tenant token，因此推荐专用共享日历。日后可增加 User OAuth Provider，而不改邮件和 AI 层。

## 8. AI 输出数据模型

AI 必须返回且只能返回这些键，即使未知也要写 `null`：

```json
{
  "type": "interview",
  "company": "示例科技",
  "position": "AI 产品经理",
  "stage": "一面",
  "application_date": "2026-11-01",
  "interview_time": "2026-11-20T14:00:00+08:00",
  "location": "线上",
  "meeting_link": null,
  "contact_name": null,
  "contact_email": "hr@example.com",
  "confidence": 0.96
}
```

字段语义：

- `type`：邮件事件类型，只能为 `application/interview/written_test/rejection/offer/other`。
- `company`：标准公司名，不确定为 null。
- `position`：岗位名，不确定为 null。
- `stage`：业务阶段，如一面、二面、HR 面。
- `application_date`：投递日期，格式 `YYYY-MM-DD`。
- `interview_time`：面试开始时间，必须是带时区的 ISO 8601。
- `location`：线下地址或“线上”。
- `meeting_link`：会议 URL。
- `contact_name/contact_email`：联系人信息。
- `confidence`：AI 对整体解析的置信度，0~1；它是审计信息，不是安全保证。

未知值使用 null 是刻意设计：系统宁可不建日程，也不根据模糊的“下周三下午”猜错时间。

## 9. Application ID 与状态机

### Application ID

当公司和岗位都明确时，程序对“规范化公司名 + 规范化岗位名”做 SHA-256，并取前 16 位生成：

```text
APP-0123456789ABCDEF
```

因此，同一公司同一岗位的投递、笔试、面试、Offer 邮件会命中同一条记录并更新阶段。若公司或岗位任一项未知，则退化为按 Message-ID 生成，优先避免把多次不同申请错误合并。

历史面试仍会写入表格，但只有未来的明确面试时间才创建日历事件，避免首次扫描历史邮件时补建过期日程。

V1 的限制：同一公司同一岗位多次投递会被视作同一次申请。V2 可把投递批次或年份加入主键。

### 状态机

典型路径：

```text
已投递(application)
   ├─→ 笔试(written_test) ─→ 面试(interview) ─→ Offer(offer)
   │                              └────────────→ 拒绝(rejection)
   └──────────────────────────────────────────→ 拒绝(rejection)
```

邮件并不保证按顺序到达，因此 V1 不强制拒绝“跳跃状态”。每封新邮件会把 `Current Stage` 更新为 AI 识别出的最新事件。更严格的状态回退保护可以在 V2 增加。

## 10. 幂等与异常处理

“幂等”表示同一个输入运行多次，最终结果不会无限重复。

本项目有三层：

1. `processed_emails.message_id`：成功处理的 Message-ID 再次出现时直接跳过。
2. `Application ID`：飞书已有相同申请则更新，不新增第二条。首次没有本地缓存时会分页读取记录并在本地匹配。
3. Calendar `event_id`：第一次创建后同时写入 SQLite 和飞书 `Calendar Event ID`；后续面试改期更新原事件。创建请求也携带稳定 idempotency key。

成功写飞书后才会把邮件标记为成功。若某封邮件失败：

- 日志记录完整堆栈；SQLite 记录 failed 和错误摘要。
- 其他邮件继续处理。
- 下次运行会重试失败邮件。

极端情况下，进程可能在飞书成功响应后、写入本地状态前断电。飞书 Application ID 查询和 Calendar 创建 idempotency key 用于缩小这种“部分成功”窗口，但任何跨系统工作流都无法仅靠本地事务做到数学意义上的原子提交。

## 11. 推荐运行顺序

### 11.1 完全离线测试

```powershell
Set-Location -LiteralPath 'D:\AgenticJobSearchCopilot'
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe .\scripts\run_mock.py
```

### 11.2 用本地样例走 CLI

```powershell
.\.venv\Scripts\python.exe -m job_workflow run `
  --fixture .\tests\fixtures\interview.eml `
  --mock-ai `
  --dry-run
```

这条命令不连接邮箱、不调用 AI、不写飞书。

### 11.3 真实邮箱 + Mock AI + dry-run

先只填写网易邮箱参数，然后：

```powershell
.\.venv\Scripts\python.exe -m job_workflow run --mock-ai --dry-run
```

它验证 IMAP 连接和规则过滤，但 Mock 只用于工程连通性，不代表真实解析质量。

### 11.4 真实邮箱 + 真实 AI + dry-run

填写 AI 参数，保持 `DRY_RUN=true`：

```powershell
.\.venv\Scripts\python.exe -m job_workflow run --dry-run
```

查看控制台和 `data\logs\workflow.log`，确认公司、岗位、阶段和时间。建议至少人工检查 20 封不同类型邮件。

### 11.5 小范围真实写飞书

完成飞书配置后，把 `.env` 中 `DRY_RUN=false`，并把 `EMAIL_LOOKBACK_DAYS` 临时设为 1：

```powershell
.\.venv\Scripts\python.exe -m job_workflow run
```

核对表记录和日历后，再把回看天数调回 7。不要在未验证字段类型时直接扫描几千封历史邮件。

## 12. Windows 任务计划程序

验证手动运行成功后：

1. 打开“任务计划程序”→“创建任务”。
2. 触发器设为每 15 或 30 分钟一次。
3. 操作选择“启动程序”。
4. 程序/脚本填：`powershell.exe`。
5. 参数填：

```text
-NoProfile -ExecutionPolicy Bypass -File "D:\AgenticJobSearchCopilot\scripts\run_once.ps1"
```

6. “起始于”填：`D:\AgenticJobSearchCopilot`。
7. 建议勾选“如果任务运行时间超过 10 分钟则停止”，并设为已有实例运行时不启动新实例。

为什么要填写“起始于”：`.env`、`data/state.db` 和 `data/logs` 默认是相对路径。起始目录错误会导致程序找不到 `.env` 或在意外目录生成数据库。

## 13. 日志和隐私

日志位置：`data\logs\workflow.log`。日志包含 Message-ID、邮件主题、识别出的公司/岗位/类型和错误堆栈；不会主动打印 API key、邮箱授权码、App Secret 或 tenant token。

为了隐私：

- 不要上传 `.env`、`state.db` 或真实日志。
- 本地日志仍可能含求职公司和邮件主题，备份时按个人敏感数据处理。
- 邮件正文会发送给选定的 AI 服务商。若不接受这一点，应改用可信本地模型 Provider。
- 定期轮换邮箱授权码、AI key 和飞书 App Secret。

## 14. 常见排错

### `No module named job_workflow`

没有安装 editable 包，或没用 venv：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

### AI 返回 400

检查 `AI_BASE_URL` 是否重复 `/v1`、模型名是否存在、服务是否支持 `response_format`。查看服务商官方 API 文档，不要随意改成网页聊天地址。

### AI 输出校验失败

日志会显示缺失字段或错误类型。不要删除 schema 校验来“解决”；应该调整提示词或 Provider，让输出真正符合格式。

### 飞书 token 获取失败

检查 App ID/Secret、应用是否已发布并启用，以及使用的是中国飞书还是 Lark。Secret 更新后旧值立即失效。

### 飞书 403、`app unauthorized` 或文档无权访问

同时检查：开放平台 API 权限、应用版本是否重新发布、目标 Base 是否把应用加为成员、Base 高级权限，以及 calendar ACL 是否给应用 writer。

### 飞书提示字段不存在或字段类型错误

字段名区分空格和大小写，必须与第 7.3 节一致。日期字段接收毫秒时间戳；Calendar API 则接收秒级时间戳，这两个单位代码已分别处理。

### 面试被识别但没有日程

日志若显示“没有明确时间”，这是安全设计。检查邮件是否只有“下周三”或时间藏在附件/图片中；V1 不解析附件，也不猜模糊日期。

### 修改 `.env` 没生效

`python-dotenv` 默认不覆盖已经存在的系统环境变量。PowerShell 当前会话若已设置同名变量，系统环境变量优先；关闭终端重开，或清理该变量。

## 15. 开发与扩展点

- 新 AI 服务：实现 `AIProvider.parse_email(message) -> ApplicationData`。
- 新输入：把 Boss/LinkedIn 导出转换成 `ParsedEmail` 或抽象成通用事件。
- 面试准备大纲：在日程成功后增加 `PreparationDocumentService`，不要塞进 AI Provider。
- 用户个人日历：增加 OAuth 流程和 `user_access_token` Provider。
- 人工确认队列：低置信度或缺时间时写入“待确认”表，不自动执行。
- 更严格状态机：为阶段定义优先级和允许转移，防止旧邮件覆盖新状态。

## 16. 官方参考

- [飞书：获取访问凭证](https://open.feishu.cn/document/server-docs/api-call-guide/calling-process/get-access-token)
- [飞书：日历 API 概述](https://open.feishu.cn/document/server-docs/calendar-v4/overview)
- [飞书：日历快速开发教程](https://open.feishu.cn/document/home/quickly-build-a-feishu-calendar-schedule/introduction)
- [飞书：API 权限申请](https://open.feishu.cn/document/ukTMukTMukTM/uQjN3QjL0YzN04CN2cDN)
- [飞书：应用数据权限](https://open.feishu.cn/document/api-call-guide/calling-process/configure-app-data-permissions)

这些页面应作为权限和参数的最终依据；控制台界面和权限显示名可能更新。

## 17. V2：AI-enhanced CRM / Copilot

V2 的边界是确定性的：AI 负责解析和生成，Python Workflow 决定什么时候调用哪个能力。系统没有 Planner，也不会自行决定投递、跟进、回复或改变阶段。

```text
Application
   ├─ JD Raw 有内容且 Hash 变化 → JD Schema
   ├─ JD + Candidate Profile 变化 → Matching
   ├─ Stage 明确为 Interview → Interview Prep
   ├─ 用户显式提交复盘 → Interview Review
   └─ 每次计划运行 → Analytics
```

核心逻辑是：

```text
邮件告诉系统“发生了什么”
JD 告诉系统“岗位需要什么”
Resume 告诉系统“我有什么”
AI 分析“哪里匹配、哪里不足”
Workflow 根据预设 IF/THEN 生成固定输出
```

### 17.1 V2 飞书结构

现有 `Job Applications` 表增加：

| 字段 | 用途 |
|---|---|
| `JD Raw` | 用户粘贴的原始 JD；这是 JD 流程的唯一触发输入。 |
| `JD Structured JSON` / `JD Hash` | Schema 校验后的 JD 和输入指纹。 |
| `Match Analysis JSON` / `Match Hash` | 匹配完整结果与上下文指纹。 |
| `Match Score` | 0~100 匹配度，不代表录用概率。 |
| `Strengths` / `Gaps` | 有证据的优势与缺口。 |
| `Interview Focus` | 面试中应该重点验证或表达的内容。 |
| `Interview Prep` | Markdown 格式面试准备文档。 |
| `Prep Status` / `Prep Hash` | 固定触发状态与幂等指纹。 |
| `Interview Review Raw/JSON` | 用户原始复盘与结构化复盘。 |
| `Review Hash` | 复盘输入指纹。 |
| `V2 Last Processed` | 最近一次 V2 处理时间。 |

另有两张辅助表：

- `Candidate Profile`：保存结构化 Profile 的当前版本和 Hash。
- `Analytics`：Dashboard 数据源，包含阶段、公司、岗位类型和漏斗指标。

### 17.2 V2.1 — JD Schema

在飞书某条 Application 的 `JD Raw` 粘贴 JD，然后运行：

```powershell
.\.venv\Scripts\python.exe -m job_workflow v2-enrich
```

只有 JD Raw 非空且内容 Hash 变化时才调用 DeepSeek。输出严格通过 `JDProfile` schema 校验。

### 17.3 V2.2 — Candidate Profile

把简历纯文本复制到：

```text
data\candidate_profile_input.example.md  → 复制为 candidate_profile_input.md 后填写
```

不要包含身份证号、银行卡或家庭住址。然后运行：

```powershell
.\.venv\Scripts\python.exe -m job_workflow profile
```

结果会写入本地 `data\candidate_profile.json`，并同步到飞书 `Candidate Profile` 表。JSON 文件被 `.gitignore` 排除。

### 17.4 V2.3 — Matching Engine

当 JD 与 Candidate Profile 都存在时，`v2-enrich` 自动生成：

- Strength / Gap
- 0~100 Match Score
- Requirement ↔ Resume Evidence
- Missing Keywords
- Interview Focus
- Recommended Stories

每项 Strength 必须引用 Candidate Profile 中已有证据。系统不会因为高分自动投递，也不会因为低分自动放弃。

### 17.5 V2.4 — Interview Prep

唯一自动触发条件：

```text
IF Current Stage 是 interview/面试/一面/二面/三面/HR面/终面
AND JD 已结构化
AND Candidate Profile 已存在
AND Match Analysis 已存在
THEN 生成 Interview Prep
```

输出包括岗位重点、预计问题、回答框架、简历映射、STAR 提示、专业复习、Case、反问和 Checklist。当前以 Markdown 文档写入飞书 `Interview Prep` 字段，不会自行联网编造公司信息。

### 17.6 V2.5 — Interview Review

把复盘写入任意 UTF-8 文本文件，然后显式运行：

```powershell
.\.venv\Scripts\python.exe -m job_workflow v2-review `
  --application-id APP-XXXXXXXXXXXXXXX `
  --input .\data\my_interview_review.md
```

只有用户执行该命令才会整理复盘，不会监听或猜测面试是否已经结束。

### 17.7 V2.6 — Analytics

运行：

```powershell
.\.venv\Scripts\python.exe -m job_workflow v2-analytics
```

会生成 `data\analytics.json`，并更新飞书 `Analytics` 表。指标包括：

- 总申请数与活跃申请数
- 当前阶段分布
- 公司分布
- AI/算法、产品、数据、工程、运营/商业化等岗位类型
- Application → Interview、Interview → Offer、Application → Offer 漏斗

漏斗基于当前表中可见状态和面试时间，是 CRM 统计，不是录用概率预测。

### 17.8 一次运行完整 V1 + V2

`scripts\run_once.ps1` 已更新为：

```text
V1 邮件同步
→ V2 JD/Matching/Prep
→ V2 Analytics
```

因此 Windows 任务计划程序继续调用同一个脚本即可，不需要第二个定时任务。

### 17.9 V2 幂等逻辑

V2 不按“运行次数”判断，而按内容 Hash：

- JD Hash = 原始 JD
- Match Hash = JD JSON + Candidate Profile JSON
- Prep Hash = Application + Stage + JD + Profile + Match
- Review Hash = 原始复盘

输入没有变化时不会再次调用 DeepSeek。修改 JD、简历或阶段后，只重算受影响的下游产物。


# V3：Agentic Job Search Copilot（0.3.0）

V3 在 V1 邮件自动化与 V2 JD/简历匹配之上新增“目标驱动”的岗位发现。系统可以根据你明确保存的 Search Goal，自主规划并执行公开网页搜索、岗位正文读取、去重、JD 解析、匹配、排序和决策记录。

最重要的边界：V3 **不会自动投递、登录招聘网站、绕过验证码、给招聘者发消息或改变你的求职目标**。自动规划器的白名单仅含 `search_jobs`、`read_job_page`、`deduplicate_leads`、`analyze_leads`、`rank_leads`、`create_approval_proposals` 和 `refresh_analytics`。高匹配岗位只会进入 Approval Queue。你批准后，系统也只生成申请材料草案，不会替你提交。

## V3 的飞书数据表

- `Search Goals`：你明确配置的岗位、城市、时效、关键词和运行频率。
- `Job Leads`：搜索到的岗位、原始 URL、JD、匹配分数和风险标记。
- `Approval Queue`：需要你决定的动作提案。
- `Agent Runs`：每轮规划、状态和统计。
- `Decision Logs`：每条推荐/跳过决策的理由与证据 URL。
- `Generated Artifacts`：批准后生成的申请材料草案。

首次创建表格：

```powershell
cd D:\AgenticJobSearchCopilot
.\.venv\Scripts\python.exe .\scripts\provision_v3.py
```

脚本是幂等的：重复运行只会补缺失表或字段，并把 6 个 table_id 自动写入 `.env`。

## 配置并运行 Search Goal

先复制 `data\search_goal_input.example.json` 为 `data\search_goal_input.json`，再编辑新文件。`role_keywords` 是岗位关键词，`locations` 是城市，`published_within_days` 默认 7 天；`required_keywords`/`excluded_keywords` 用于收窄搜索；确认后把 `active` 改为 `true`。系统不会从历史申请中擅自推断这些偏好。

```powershell
# 导入或更新目标
.\.venv\Scripts\python.exe -m job_workflow --env-file .env v3-goal --input data\search_goal_input.json

# 安全预演：只生成计划，不联网、不写表
.\.venv\Scripts\python.exe -m job_workflow --env-file .env v3-run --goal-id 你的goal_id --dry-run

# 真实执行：DeepSeek Search/Fetch 会按成功请求计费
.\.venv\Scripts\python.exe -m job_workflow --env-file .env v3-run --goal-id 你的goal_id

# 人工批准/拒绝提案
.\.venv\Scripts\python.exe -m job_workflow --env-file .env v3-approve --approval-id approval_xxx --decision approved

# 仅在批准后生成申请材料草案
.\.venv\Scripts\python.exe -m job_workflow --env-file .env v3-package --lead-id lead_xxx
```

V3 默认使用现有 `AI_API_KEY` 调用 DeepSeek 官方 `POST /v1/tools/search` 和 `POST /v1/tools/fetch`。Search 返回来源 URL、标题、摘要、发布时间、权威度和相关性；Fetch 读取公开网页 Markdown。系统拒绝 localhost、内网和保留地址。`--dry-run` 不发起这些可能计费的请求。

Candidate Profile 仍来自 `V2_CANDIDATE_PROFILE_PATH`。如果它不存在，V3 会保存岗位并标记“Candidate Profile 缺失”，但不会给出真正的简历匹配推荐，也不会创建高匹配审批。

---

