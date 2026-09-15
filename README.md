# MoviePilot Plugins

本仓库是 [MoviePilot](https://github.com/jxxghp/MoviePilot) V3 的第三方插件仓库（布局：`package.v3.json` + `plugins.v3/<插件ID小写>/`）。

## 插件列表

| 插件 | 版本 | 说明 |
|---|---|---|
| **Cd2StrmSync**（CD2 API Strm 同步、媒体整理与镜像移动） | 1.18.0 | 接收 CloudDrive2 变更通知，按多组「源目录 → 目的目录」规则生成 strm / 软链接并同步元数据；可另按独立的整理规则把文件交给 MoviePilot 整理链入库；还可按镜像规则把镜像目录中对应的对象移动到回收站。三者互不影响，共用同一路 CD2 通知。 |

## 安装

1. 打开 MoviePilot → **插件市场** → **添加仓库**（或在「设置 → 插件市场的第三方仓库」处填入本仓库地址）：

   ```
   https://github.com/mtno1/MoviePilot-Plugins
   ```

2. 刷新市场，找到 **CD2 API Strm 同步、媒体整理与镜像移动**，点击安装。
3. 安装后插件默认**停用**，请到插件配置页按你的环境填写 CloudDrive2 地址与令牌、目录组规则，再手动启用。
4. 更新：在同一市场页点「更新」，或在本地插件目录执行 `plugin.install` + `plugin.reload`。

## 目录结构

```
MoviePilot-Plugins/
├── package.v3.json                 # 插件索引（MoviePilot V3 读取此文件）
├── README.md
└── plugins.v3/
    └── cd2strmsync/                # 插件源码（__init__.py / engine.py / rules.py / ui.py / cd2web.py）
```

## Cd2StrmSync 使用要点

- **通知来源**：只使用 CloudDrive2 的 `PushMessage` 推送订阅与 `GetMountPoints` 只读自检；令牌需在 CD2 侧手动勾选「推送消息」「获取挂载点」。
- **路径口径**：所有目录按「源目录 → 目的目录」配置，填容器内路径；通知里的路径会先归一化（去 CD2 根目录前缀、反斜杠转斜杠）再匹配。
- **三块功能互相独立**：
  1. **STRM 同步**：按目录组规则生成 strm / 软链接，并按需同步同名元数据；
  2. **媒体整理**：把源目录里的文件交给 MoviePilot 整理链入库，整理行为（刮削 / 类型目录 / 分类目录 / 命名 / 同名覆盖）统一由命中目录的 MoviePilot「目录配置」决定(必须在mp设置中设置相同的整理目录,自动整理选择不整理或手动整理)；
  3. **镜像移动**：监听目录里删除什么，就把镜像目录里对应的对象移动到回收站，保护白名单命中的对象不移动。
- **定时扫描**：网盘侧新增的文件 CloudDrive2 不会推送，建议给需要的目录组开启定时扫描兜底。

## 免责声明

本仓库仅提供插件源码，使用前请自行评估风险并做好备份。插件按「原样」提供，作者不对数据丢失或其它损失负责。
