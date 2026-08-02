# 云湖QSpace Rebased

本仓库是云湖QSpace Rebased（Misskey）的云湖机器人模块源代码。其他模块源代码请见：<https://ars.lilingyi-awa.top/@7261230/pages/1767788116562>。

## 技术架构

- `services`：核心模块
  - `commons.py`：公共模块
  - `eapis.py`：外部API调用模块
  - `basics.py`：云湖登录基础逻辑
  - `utils.py`：辅助API
  - `robotapis.py`：云湖机器人Router
  - `clientlogin.py`：客户端API
  - `oauth.py`：OAuth2.0
  - `contents.py`：内容管理操作
- `main.py`：系统初始化逻辑

## 版权声明

版权所有 © 2026-至今 「Vsinger小冰」企划组。以 GNU AGPL 3.0 开源协议发布。
