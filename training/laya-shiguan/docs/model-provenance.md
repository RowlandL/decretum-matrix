# 模型来源与引用条款 · laya-multilingual

> 适用能力：`shiguan-recall`（史馆对照决策检索）。
> 本文件是**来源记录与引用指引**；许可全文见仓库根 `THIRD_PARTY_NOTICES.md`，组件清单见 `SBOM.spdx.json`。

## 一、来源（固定 revision）

| 组件 | 仓库 | 固定 revision | 许可 | 角色 |
| --- | --- | --- | --- | --- |
| `laya-multilingual` | https://huggingface.co/convaiinnovations/laya-multilingual | `e4e9ddf21a7b1903b7acffd8814ad4307bf63a67` | **Apache-2.0** | 判定模型本体（322M，mmBERT-base 主干 + 决策头）|
| `mmBERT-base` | https://huggingface.co/jhu-clsp/mmBERT-base | `c5955035435e2bf121cde7f3c8863ef52ff35d82` | **MIT** | 主干编码器（`rl_agent_config.json` → `encoder`）|

本机实际落盘文件（安装态同构）：

| 文件 | 体积 |
| --- | --- |
| `model.safetensors` | 614.0 MB |
| `tokenizer/tokenizer.json` | 32.8 MB |
| `tokenizer/tokenizer_config.json` | — |
| `encoder/config.json` | — |
| `rl_agent_config.json` | — |

## 二、本包是否再分发模型

**不再分发。** 本仓库与发布包**不含**模型权重：

- 权重在**安装时**按上表固定 revision 获取，并逐文件校验 SHA-256；
- 下载副本仍归 Apache-2.0 / MIT 管辖，自带上游许可文件；
- 任何再分发这些权重的人，须保留上游版权与许可声明。

因此本仓库的义务是**署名与来源可追溯**，而非随包附许可全文；`THIRD_PARTY_NOTICES.md` 已按此记录。

## 三、引用条款

### 3.1 引用上游模型（必做）

使用或发布基于本能力的成果时，请按上游仓库的引用方式标注 Laya：

```bibtex
@misc{laya2026,
  title        = {Laya: a multilingual non-autoregressive System 1 decision model},
  author       = {Convai Innovations},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/convaiinnovations/laya-multilingual}},
  note         = {Apache-2.0; revision e4e9ddf21a7b1903b7acffd8814ad4307bf63a67}
}
```

主干编码器按上游仓库标注：

```bibtex
@misc{mmbert2025,
  title        = {mmBERT: A Massively Multilingual Encoder},
  author       = {Johns Hopkins University, Center for Language and Speech Processing},
  year         = {2025},
  howpublished = {\url{https://huggingface.co/jhu-clsp/mmBERT-base}},
  note         = {MIT; revision c5955035435e2bf121cde7f3c8863ef52ff35d82}
}
```

### 3.2 标注本仓的二次开发（必做）

本仓**未修改模型权重**，只在其上构建检索用途的推理服务与语料管线。因此在文档中应说明：

> 史馆对照决策检索基于 Convai Innovations 的 Laya（Apache-2.0）与 JHU CLSP 的
> mmBERT-base（MIT）构建，仅用于本地只读召回；模型权重未修改，本仓以 AGPL-3.0-only 发布。

**不得**声称本仓拥有模型权重，**不得**把上游模型标注为本仓原创，**不得**暗示上游对本仓背书（上游与本仓无附属关系）。

### 3.3 许可边界

- Apache-2.0 与 MIT 均为宽松许可，**允许商用与再分发**；
- 二者**不改变**本仓 `AGPL-3.0-only` 的范围，本仓的 AGPL 也**不覆盖**下载得到的权重；
- 商业授权咨询见仓库根 `COMMERCIAL-LICENSE.md`。

## 四、能力的权威边界（与许可无关，但须与引用一同说明）

`shiguan-recall` 是 **advisory / read_only** 组件：

- `authority = advisory`、`execution_authority = false`；
- 输出为**对照参考**，不写史馆、不改 `CONTENT_TAXONOMY`、不替代门下裁定；
- ⚠️ 相似度绝对值**不可作阈值**（mmBERT 句向量各向异性），只能使用 Top-k 相对排序；
- 实测质量（参照集 901 / 查询集 126）：同谱系命中 @1 0.444、@3 0.706、@5 0.810。

引用本能力时应同时转述这一边界，避免被读作判定权威。
