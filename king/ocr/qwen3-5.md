## 1. 目标

将 `Qwen/Qwen3.5-9B` 改造成六分类图片分类器，用于以下场景：

*   `study`
*   `office`
*   `product_drug`
*   `menu`
*   `landmark_relic`
*   `other`

目标不是做多模态长文本生成，而是直接从图片输出类别，以获得更高准确率和更稳定的线上行为。

## 2. 方案概述

### 2.1 模型结构

核心实现位于：

*   [train\_qwen3\_vl\_classifier.py](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/code/qwen3_5_classifier/train_qwen3_vl_classifier.py)
*   [common.py](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/code/qwen3_5_classifier/common.py)
*   [run\_round1\_classifier.sh](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/run_round1_classifier.sh)

核心做法：

*   基座模型：`Qwen/Qwen3.5-9B`
*   权重量化：`4-bit QLoRA`
*   训练参数：只训练 LoRA + 新增分类头
*   分类方式：取最后一个有效 token 的 hidden state，pooling 后接 `Linear(hidden_size -> 6)` 分类头
*   输出：`6` 维 logits，经 `softmax + argmax` 得到最终类别

这条路线和生成式端到端 VLM 的区别是：

*   不做自回归解码
*   不生成 JSON
*   不输出解释文本
*   直接输出分类结果

### 2.2 输入输出

输入：

*   一张图片
*   一句固定短 prompt

```text
Choose one label for the image: study, office, product_drug, menu, landmark_relic, other. Use the whole image.
```

输出：

*   `pred_label`
*   `confidence_score`
*   `6` 类概率分布

本方案本质是“视觉 backbone + 分类头”，不是“图片问答”。

## 3. 数据与训练

数据摘要来自：

*   [dataset\_summary.json](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/dataset_summary.json)

数据规模：

*   训练集：`23460`
*   dev：`120`
*   test：`120`
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

本轮训练配置来自：

*   [run\_config.json](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/runs/qwen35_classifier_gpu1_full_20260330_161021/run_config.json)

关键参数：

*   epoch：`1`
*   batch size：`1`
*   gradient accumulation：`8`
*   learning rate：`2e-4`
*   max pixels：`122880`
*   LoRA：`r=8, alpha=16, dropout=0.05`
*   仅保留最后 `8` 层 LoRA 可训练
*   分类头 dropout：`0.1`
*   prompt style：`short`
*   精度：`bf16`
*   训练卡：单卡 `4090D`

## 4. 工程实现说明

### 4.1 兼容性处理

由于 `Qwen/Qwen3.5-9B` 依赖的 `transformers / peft` 版本较新，这条线没有直接复用旧环境，而是在实验目录中单独放了一套 vendor 依赖：

*   `/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/vendor`

训练脚本通过 `PYTHONPATH` 优先使用这套依赖，避免影响现有其他实验。

### 4.2 OOM 跳过机制

训练代码保留了和 `qwen3-vl-classifier` 相同的 OOM 保护：

*   forward OOM 跳过
*   backward OOM 跳过
*   `gc.collect()`
*   `torch.cuda.empty_cache()`
*   训练和评测分别统计 `oom_skipped_train_batches` / `oom_skipped_eval_batches`

本轮正式训练结果：

*   `oom_skipped_train_batches = 0`
*   `oom_skipped_eval_batches = 0`

### 4.3 Qwen3.5 适配点

Qwen3.5 的 processor 相比旧版 Qwen3-VL 会返回更多 tensor 字段，因此训练侧做了兼容：

*   对 `kwargs` 中所有 tensor 统一搬到目标 device

否则会在首个训练 step 上出现 device mismatch。

## 5. 训练结果

正式训练目录：

*   [qwen35\_classifier\_gpu1\_full\_20260330\_161021](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/runs/qwen35_classifier_gpu1_full_20260330_161021)

最佳 checkpoint 指标来自：

*   [best\_metrics.json](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/runs/qwen35_classifier_gpu1_full_20260330_161021/best_metrics.json)

训练过程最佳点：

*   `global_step = 1700`
*   `accuracy = 72.50%`
*   `macro_recall = 80.66%`

各类 recall：

| label           |   recall |
| :-------------- | -------: |
| study           | 0.888889 |
| office          | 0.857143 |
| product\_drug   | 0.818182 |
| menu            | 1.000000 |
| landmark\_relic | 0.666667 |
| other           | 0.608696 |

说明：

*   上述是训练过程中的 `dev` 指标
*   不等于业务 165 张人工评测集结果

## 6. 165 人工评测集结果

评测目录：

*   [eval\_photo\_case\_best\_20260331](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/eval_photo_case_best_20260331)

关键文件：

*   [summary.json](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/eval_photo_case_best_20260331/summary.json)
*   [predictions.csv](/ssd13/other/lys05/glmocr/exp/qwen3.5-classifier/eval_photo_case_best_20260331/predictions.csv)

测试设置：

*   数据集：`photo_case_20260325`
*   样本数：`165`
*   推理设备：单卡 `4090D`
*   prompt：`short`

整体结果：

| 指标                      |     数值 |
| :---------------------- | -----: |
| accuracy                | 84.24% |
| macro\_f1               | 85.87% |
| weighted\_f1            | 83.88% |
| primary\_accuracy       | 87.88% |
| avg\_total\_ms          |  262.0 |
| avg\_embedding\_ms      |   27.8 |
| avg\_classification\_ms |  234.1 |
| p50\_total\_ms          |  257.2 |
| p90\_total\_ms          |  277.3 |
| p95\_total\_ms          |  288.9 |
| p99\_total\_ms          |  392.8 |

各类 F1 / Recall：

| label           |       f1 |   recall |
| :-------------- | -------: | -------: |
| study           | 0.868421 | 1.000000 |
| office          | 0.806452 | 0.781250 |
| product\_drug   | 0.897959 | 0.956522 |
| menu            | 0.967742 | 1.000000 |
| landmark\_relic | 0.864865 | 0.761905 |
| other           | 0.746667 | 0.682927 |

## 7. 与现有方案对比

结合当前总报告：

*   [report.md](/ssd13/other/lys05/glmocr/exp/report/report.md)

可以得到：

*   `qwen3.5-9b-classifier` 是当前 165 集上准确率最高的方案
*   它同时超过 `doubao-seed-2.0-lite` 和 `qwen3-vl-8b-classifier`
*   平均时延高于 `qwen3-vl-8b-classifier`，但远低于生成式 `qwen3.5-9b` 和 Doubao 端到端

简表：

| 系统                     | accuracy | macro\_f1 | avg\_total\_ms |
| :--------------------- | -------: | --------: | -------------: |
| qwen3.5-9b-classifier  |   84.24% |    85.87% |          262.0 |
| doubao-seed-2.0-lite   |   81.82% |    84.24% |         3077.5 |
| qwen3-vl-8b-classifier |   79.39% |    81.17% |          214.6 |
| qwen3.5-9b 端到端         |   79.39% |    80.82% |         2304.9 |

## 8. 结论

结论：

*   这条 `Qwen3.5-9B + 分类头` 路线已经跑通，训练和评测链路完整可复现
*   在当前 `165` 张人工评测集上，它是准确率最高的方案
*   如果目标是“本地单卡部署 + 高准确率”，当前优先推荐这条线
*   如果目标是“更低时延”，则 `qwen3-vl-8b-classifier` 仍更有优势

当前推荐：

*   追求效果优先：`qwen3.5-9b-classifier`
*   追求速度优先：`qwen3-vl-8b-classifier`

