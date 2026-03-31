## 1. 目标

将 `Qwen/Qwen3-VL-8B-Instruct` 从通用多模态生成模型改造成六分类图片分类器，用于以下场景：

*   `study`
*   `office`
*   `product_drug`
*   `menu`
*   `landmark_relic`
*   `other`

目标不是生成长文本或 JSON 解释，而是直接从图片输出类别，以获得更低时延和更稳定的分类结果。

## 2. 方案概述

### 2.1 模型结构

实现位于 [train\_qwen3\_vl\_classifier.py](/ssd13/other/lys05/glmocr/src/vlm_rl/train_qwen3_vl_classifier.py)。

核心做法：

*   基座模型：`Qwen/Qwen3-VL-8B-Instruct`
*   权重量化：`4-bit QLoRA`
*   训练参数：只训练 LoRA + 新增分类头
*   分类方式：取最后一个有效 token 的 hidden state，做 pooling 后接 `Linear(hidden_size -> 6)` 分类头
*   输出：`6` 维 logits，经 `softmax + argmax` 得到最终类别

这和端到端生成式 VLM 的主要区别是：

*   不做自回归解码
*   不生成 JSON
*   不输出解释文本
*   直接输出类别概率

### 2.2 输入输出

评测脚本位于 [evaluate\_qwen3\_vl\_classifier\_human\_set.py](/ssd13/other/lys05/glmocr/src/vlm_rl/evaluate_qwen3_vl_classifier_human_set.py)。

输入：

*   一张图片
*   一句固定短 prompt：

```text
Choose one label for the image: study, office, product_drug, menu, landmark_relic, other. Use the whole image.
```

输出：

*   `pred_label`
*   `confidence_score`
*   `6` 类概率分布

本方案本质是“视觉 backbone + 分类头”，不是“图片问答”。

## 3. 数据与训练

数据摘要来自 [dataset\_summary.json](/ssd13/other/lys05/glmocr/exp/qwen-vl-sft/dataset_summary.json)：

*   训练集：`23460`
*   dev：`120`
*   test：`120`
*   训练集构成：
    *   人工标注：`960`
    *   弱标注：`22500`

训练分布：

| 类别              | train |
| :-------------- | ----: |
| landmark\_relic |   251 |
| menu            |  1010 |
| office          |  5509 |
| other           |  7301 |
| product\_drug   |  4591 |
| study           |  4798 |

训练配置：

*   epoch：`1`
*   batch size：`1`
*   gradient accumulation：`8`
*   learning rate：`2e-4`
*   max pixels：`122880`
*   LoRA：`r=8, alpha=16, dropout=0.05`
*   仅保留最后 `8` 层 LoRA 可训练
*   分类头 dropout：`0.1`
*   精度：`bf16`
*   推理/训练卡：单卡 `4090D`

这里需要区分两类 prompt：

1.  标注 prompt

*   用于生成训练集中的 `teacher_secondary_category`
*   这批数据的标签边界来自更完整的标准标注 prompt
*   标准 prompt 会显式定义各类别边界，例如 `study / office / product_drug / menu / landmark_relic / other` 的语义范围

1.  分类头训练 prompt

*   用于把“图片分类任务”喂给 Qwen3-VL backbone
*   当前已完成的分类头版本实际使用的是短 prompt：

```text
Choose one label for the image: study, office, product_drug, menu, landmark_relic, other. Use the whole image.
```

也就是说：

*   数据标签本身来自标准 prompt 语义体系
*   但分类头训练和推理阶段，并没有直接使用那套完整标准 prompt，而是用了一个更短的分类 prompt

## 4. 训练过程说明

这条线最初尝试过生成式 SFT 和多卡 DDP，但稳定性较差，主要问题是：

*   生成式训练显存压力大
*   DDP 与 LoRA + checkpointing 组合下不稳定
*   存在 OOM 和 reduction/NCCL 问题

最终收敛到的可用方案是：

*   单卡训练
*   4-bit QLoRA
*   分类头训练
*   OOM batch 跳过
*   checkpoint/resume

最终训练跑到 `global_step=2908`，并产出最终模型。训练期间有 `230` 个 train batch 因 OOM 被跳过，因此 global step 略低于理论值。这不影响训练正常收尾，但意味着不是所有样本都参与了有效反向。

## 5. 人工评测集 165 结果

评测目录：

*   [qwen3\_vl\_8b\_classifier\_round1\_final](/ssd13/other/lys05/glmocr/exp/photo_case_eval_20260325/qwen3_vl_8b_classifier_round1_final)

关键文件：

*   [summary.json](/ssd13/other/lys05/glmocr/exp/photo_case_eval_20260325/qwen3_vl_8b_classifier_round1_final/summary.json)
*   [predictions.csv](/ssd13/other/lys05/glmocr/exp/photo_case_eval_20260325/qwen3_vl_8b_classifier_round1_final/predictions.csv)

测试集：

*   数据集：`photo_case_20260325`
*   样本数：`165`
*   推理设备：单卡 `4090D`

### 5.1 准确率指标

| 指标                |     数值 |
| :---------------- | -----: |
| accuracy          | 79.39% |
| macro\_f1         | 81.17% |
| weighted\_f1      | 78.29% |
| primary\_accuracy | 84.24% |

### 5.2 时延指标

这里有两套口径：

*   `avg_classification_ms`：纯前向时延，只统计 `model(**batch)` 到 logits 输出
*   `avg_total_ms`：本地端到端时延，包含读图、processor 预处理、前向和后处理

| 指标                      |    数值 |
| :---------------------- | ----: |
| avg\_embedding\_ms      |  36.7 |
| avg\_classification\_ms | 181.0 |
| avg\_total\_ms          | 217.8 |
| p50\_total\_ms          | 199.1 |
| p90\_total\_ms          | 214.7 |
| p95\_total\_ms          | 224.5 |
| p99\_total\_ms          | 657.1 |

说明：

*   大多数样本本地端到端时延集中在 `190-220ms`
*   `p99` 被个别预处理长尾样本拉高
*   因此更能代表稳定时延的是 `p50/p90/p95`

### 5.3 分类别表现

| 类别              | precision | recall |     f1 |
| :-------------- | --------: | -----: | -----: |
| study           |    0.7021 | 1.0000 | 0.8250 |
| office          |    0.7576 | 0.7813 | 0.7692 |
| product\_drug   |    0.7500 | 0.9130 | 0.8235 |
| menu            |    0.9375 | 1.0000 | 0.9677 |
| landmark\_relic |    0.8947 | 0.8095 | 0.8500 |
| other           |    0.9091 | 0.4878 | 0.6349 |

主要观察：

*   `study/menu/product_drug/landmark_relic` 表现较强
*   `office` 中等
*   `other recall` 仍偏低，是当前主要短板

## 6. 与生成式端到端方案对比

与同底座的生成式 `qwen3-vl-8b` 相比：

| 方案                         | accuracy | macro\_f1 | avg\_total\_ms |
| :------------------------- | -------: | --------: | -------------: |
| qwen3-vl-8b 生成式端到端         |   73.94% |    75.04% |         1343.1 |
| qwen3-vl-8b classifier 分类头 |   79.39% |    81.17% |          217.8 |

结论：

*   分类头方案比生成式端到端更准
*   分类头方案时延显著更低
*   在单卡本地部署场景下，分类头路线更适合作为生产候选

与 `qwen3.5-9b` 端到端相比：

| 方案                     | accuracy | macro\_f1 | avg\_total\_ms |
| :--------------------- | -------: | --------: | -------------: |
| qwen3.5-9b 端到端         |   79.39% |    80.82% |         2304.9 |
| qwen3-vl-8b classifier |   79.39% |    81.17% |          217.8 |

结论：

*   两者 accuracy 持平
*   分类头方案 macro\_f1 更高
*   分类头方案时延约低一个数量级

## 7. 当前优缺点

优点：

*   单卡本地即可部署
*   不需要生成 JSON，输出更稳定
*   时延远低于通用生成式 VLM
*   165 人工集上效果已经达到较强水平

缺点：

*   `other` 类召回仍不够高
*   训练中存在 OOM skip，说明当前训练配置仍接近显存边界
*   分类头方案泛化上仍受训练数据分布影响较大
*   当前仍是单轮训练结果，尚未做更系统的数据清洗和 hard case 回流

## 8. 建议

短期建议：

*   保留该方案作为“本地单卡低时延方案”
*   后续优化重点放在 `other` 和 `office/other` 边界 case
*   人工集评估时继续同时保留：
    *   `forward_ms`
    *   `local_end2end_ms`

中期建议：

*   对 `other` 做更有针对性的增样
*   单独回流误判最重的 `office -> study`、`other -> office/study/product_drug`
*   进一步约束预处理长尾，降低 `p99`

## 9. 结论

`qwen3-vl-8b classifier` 是当前这批方案里非常有价值的一条线：

*   本地单卡可跑
*   精度达到 `79.39%`
*   `macro_f1` 达到 `81.17%`
*   本地端到端平均时延仅 `217.8ms`

