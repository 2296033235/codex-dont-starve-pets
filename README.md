# 饥荒 Codex 桌宠（官方帧版）

给 Codex 做的《饥荒》桌宠，全是拿游戏官方贴图和动画一帧一帧抠出来渲染的，没有一张图是 AI 画的。每个角色一个独立目录，之后还会加新角色。

## 收录角色

| 目录 | 角色 | 称号 | 台词 |
| --- | --- | --- | --- |
| [`pets/wilson/`](pets/wilson/README.md) | 威尔逊 | 绅士科学家 | "我会用我的头脑征服一切！" |
| [`pets/webber/`](pets/webber/README.md) | 韦伯 | 蜘蛛男孩 | "我们可以克服万难！" |

## 安装（一步）

先把仓库拉下来（或者直接 Download ZIP 解压）：

```powershell
git clone https://github.com/2296033235/codex-dont-starve-pets.git
cd codex-dont-starve-pets
```

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Pet wilson   # 或 -Pet webber
```

它会把对应角色的 `final\spritesheet-extended.webp` 与 `pet\pet.json` 复制到
`%USERPROFILE%\.codex\pets\<角色id>\`。

## 使用

装完**重启一下 Codex 客户端**，在桌宠列表里就能选到角色了。每个角色自带 9 种状态：待机、拖动跟手（分左右朝向）、
招手、悬停反应、出错（精神崩溃）、等审批、干活（制作）、查看成果，外加 16 个注视方向——盯着它看，它的眼睛会跟着你的鼠标转。

## 仓库结构

```
codex-dont-starve-pets/
├── README.md            # 本文件（总览）
├── LICENSE
├── install.ps1          # 参数化安装：-Pet <角色id>
├── pets/
│   ├── wilson/          # 威尔逊：final/ 图集 + pet/ 清单 + README
│   └── webber/          # 韦伯：同上
└── scripts/
    ├── wilson/          # 威尔逊的提取 / 渲染 / 装配 / QA 脚本
    └── webber/          # 韦伯的同套脚本
```

名称、称号与台词均取自《饥荒》游戏自带官方中文语言文件 `data/scripts/languages/chinese_s.po`。

## 免责声明

本仓库只包含渲染流程与最终图集，不包含《饥荒》游戏本体及其版权资源。若要复现，请自备正版游戏，
用 `scripts/<角色>/` 里的脚本从自己的安装目录提取。
