## 1. 背景

本项目服务于图片翻译业务中的意图识别。

最初业务定义的场景为：

*   重文本类
*   学习类：如习题、阅读等，线上词典拍照日志中占比 60% 以上
*   办公类：如邮件、合同等，线上词典拍照日志中占比 20% 以上
*   物体 / 图片类
*   商品 / 药品
*   菜单
*   景点 / 文物
*   其他：不属于以上所有的通用总结

当前系统将其落地为 6 个二级标签：

*   `study`
*   `office`
*   `product_drug`
*   `menu`
*   `landmark_relic`
*   `other`

以及 3 个一级标签：

*   `text`
*   `object`
*   `other`

映射关系如下：

*   `study / office -> text`
*   `product_drug / menu / landmark_relic -> object`
*   `other -> other`

其中 `landmark_relic` 对应“景点 / 文物 / 展馆说明牌 / 文保碑 / 景区介绍牌 / 地标建筑”等场景。

## 2. 标签体系与设计原则

### 2.1 二级标签定义

*   `study`
    *   题目、教材、阅读材料、词典查询、练习、翻译学习类内容
*   `office`
    *   邮件、合同、表格、工作流、企业页面、行政文档、系统截图
*   `product_drug`
    *   商品包装、药盒、成分说明、使用方法、规格参数
*   `menu`
    *   菜单、价目表、点餐页、饮品单
*   `landmark_relic`
    *   景点介绍牌、文保碑、展签、馆藏说明牌、景区说明页、文物说明
*   `other`
    *   不稳定落入上述任何一类的通用图片

### 2.2 一级标签设计

一级标签不是单独训练的模型，而是由二级标签映射得到：

*   `study / office -> text`
*   `product_drug / menu / landmark_relic -> object`
*   `other -> other`

这么做的好处是：

*   业务上仍然可以用一级标签快速分流
*   模型层面只需维护一个 6 类分类器
*   一级标签不会引入单独的训练噪声

## 3. 技术路线

### 3.1 主链路

当前主链路为：

1.  用 `GLM-OCR` 从图片中提取 OCR 文本
2.  用 `gte-multilingual-base` 将 OCR 文本编码成 token embedding
3.  对 token embedding 做 `mean_over_tokens` pooling，得到 `768` 维句向量
4.  用轻量 `MLP` 分类头输出 6 类概率

对应链路：

*   `GLM-OCR -> GTE -> MLP`

从数据形态上看，整条链路经历的是：

1.  `image`
2.  `ocr_text`
3.  `token embeddings`
4.  `pooled sentence embedding`
5.  `6-class logits`
6.  `6-class probabilities`

### 3.2 为什么采用 GTE + MLP

当前采用的是“表示学习与分类解耦”方案：

*   `GTE` 负责把 OCR 文本转成稳定语义表示
*   `MLP` 负责把语义表示映射到业务标签

选择这条路线的原因是：

*   训练稳定
*   重训成本低
*   embedding 可缓存，便于反复试验
*   分类头很小，适合快速调分布和继续训练

早期尝试过直接端到端微调整个基座，但在当前环境下出现过：

*   `position_ids` 异常
*   `NaN logits`
*   `save_pretrained -> reload` 不稳定
*   训练塌缩成单类

因此当前不采用整模微调作为主路线。

### 3.3 两层 MLP 结构

当前分类头是一个两层全连接网络：

*   输入维度：`768`
*   hidden dim：`256`
*   dropout：`0.1`
*   标签数：`6`
*   pooling：`mean_over_tokens`

结构为：

1.  `Linear(768 -> 256)`
2.  `ReLU`
3.  `Dropout(0.1)`
4.  `Linear(256 -> 6)`
5.  `Softmax`

分类头参数量近似为：

*   第一层：`768 x 256 + 256`
*   第二层：`256 x 6 + 6`

总参数量约：

*   `198,406`

### 3.4 token embedding 与 pooling

`GTE` 不会直接只输出一个“整句向量”，而是会先为每个 token 生成一个向量。

例如 OCR 文本：

```text
测试 OCR 文本 这是识别结果
```

编码后的结果可以理解成：

*   token1 -> 一个 `768` 维向量
*   token2 -> 一个 `768` 维向量
*   ...
*   tokenN -> 一个 `768` 维向量

这时得到的是一个 `N x 768` 的张量。\
但分类头需要固定长度输入，所以需要做 pooling。

当前使用：

*   `mean_over_tokens`

也就是对所有 token 的 `768` 维向量逐维求平均，得到一个固定长度句向量。

### 3.5 为什么使用 mean pooling

当前使用 `mean_over_tokens` 的原因是：

*   实现稳定
*   对多语种 OCR 文本更鲁棒
*   不依赖某个特定 special token 的表现
*   与当前导出的 GTE pooling 服务兼容

相比之下：

*   `CLS pooling` 更依赖预训练模型是否对 `[CLS]` 做了足够监督
*   `max pooling` 对噪声 token 更敏感

## 4. 数据与训练方法

### 4.1 数据来源

teacher 池主要来自：

*   `exp/full/teacher`
*   `exp/round2/teacher`
*   `exp/round3/teacher`
*   `exp/round4/teacher`
*   `exp/round6_10k/teacher`

当前阶段没有大规模人工标注，而是采用：

1.  规则粗筛候选
2.  用 `gpt-5.4` 对 OCR 文本打 teacher 标签
3.  合并多轮 teacher 数据
4.  从 teacher 池中重构最终训练集

当前数据构建的核心思想不是“越多越好”，而是“分布可控、关键类别可学”。

### 4.2 round5a：首个正式过线版本

当前首个正式过线版本为 `round5a`，其最终训练集规模为 `3000`：

*   train：`2400`
*   dev：`300`
*   test：`300`

训练数据分布为：

*   `study = 420`
*   `office = 900`
*   `product_drug = 550`
*   `menu = 311`
*   `landmark_relic = 169`
*   `other = 650`

这一版的意义是：

*   证明 `GLM-OCR -> GTE -> MLP` 这条路线可以过正式验收线
*   为后续继续训练提供稳定 checkpoint

### 4.3 训练方式

训练流程如下：

1.  准备 `train / dev / test`
2.  调用 GTE 服务抽取并缓存全量 embedding
3.  使用 embedding 训练 MLP 分类头
4.  用 `dev macro_f1` 做 early stopping
5.  保存 best checkpoint
6.  用 `test` 做正式验收

训练过程中：

*   `GTE` 固定不训练
*   只训练 MLP 分类头

主要训练配置为：

*   embedding batch size：`16`
*   train batch size：`128`
*   eval batch size：`256`
*   epochs：`20`
*   learning rate：`1e-3`
*   hidden dim：`256`
*   dropout：`0.1`
*   early stopping patience：`3`

### 4.4 缓存 embedding 的原因

训练前会先把 `train / dev / test` 的全量 embedding 抽出来并缓存。\
这么做的原因是：

1.  避免每个 epoch 重复调用编码器
2.  显著降低训练耗时
3.  避免 embedding 服务波动影响训练稳定性
4.  便于在同一套 embedding 上快速试不同采样分布、loss 权重和继续训练方案

因此当前训练实际上分成两步：

*   第一步：离线特征抽取
*   第二步：基于固定特征训练分类头

### 4.5 损失函数与优化目标

当前分类头训练的目标是多类分类。\
模型输出 6 个 logits，经过 softmax 后得到 6 类概率分布。

训练时使用：

*   `weighted cross entropy`

原因是：

*   当前标签分布不均衡
*   如果不加权，头部类别更容易主导损失
*   加权后可以缓解小类被忽略的问题

### 4.6 early stopping 的意义

当前模型不大，但训练集来自 teacher 弱标，存在噪声。\
如果固定把 epoch 跑满，分类头容易在弱标上过拟合。

因此当前使用：

*   `dev macro_f1` 作为 early stopping 指标

目的是：

*   在“类间整体质量最好”时停止训练
*   而不是在训练损失最低时停止

## 5. 验收标准

### 5.1 当前验收线

本项目当前采用三条验收线：

*   `dev macro_f1 >= 0.82`
*   `test macro_f1 >= 0.80`
*   `other f1 >= 0.70`

这三条线不是直接从“学习类 60%+、办公类 20%+”公式推导出来的，而是结合以下因素制定的工程门槛：

*   原始业务标签结构
*   类别不均衡现实
*   `other` 作为收口类的重要性
*   teacher 弱标噪声下可实现的稳定上限

### 5.2 `macro_f1` 相关释义

`macro_f1` 的含义是：

*   先分别计算 6 个类别各自的 F1
*   再把 6 个类别的 F1 做简单平均
*   每个类别权重相同，不按样本量加权

公式如下：

```text
macro_f1 = (F1_study + F1_office + F1_product_drug + F1_menu + F1_landmark_relic + F1_other) / 6
```

其中：

```text
precision = TP / (TP + FP)
recall = TP / (TP + FN)
F1 = 2 * precision * recall / (precision + recall)
```

因此：

*   `dev macro_f1 >= 0.82`

表示：

*   模型在验证集上，6 个类别平均下来，整体分类质量要达到 `0.82` 以上

### 5.3 为什么选 `macro_f1` 而不是只看 accuracy

当前任务类别不均衡明显：

*   `office`、`other` 样本相对更多
*   `landmark_relic` 样本较少
*   `menu`、`product_drug` 更容易
*   `study / office / other` 的边界更难

如果只看：

*   `accuracy`
*   `weighted_f1`

头部类别会掩盖长尾类别问题。\
所以当前采用 `macro_f1`，原因是：

*   每个类别同等权重
*   能反映 6 类整体是否都可用
*   更符合业务上“不能只把常见类做好”的目标

### 5.4 三条线的职责划分

这三条线分别控制三件事：

*   `dev macro_f1 >= 0.82`
    *   控制训练阶段候选版本质量
*   `test macro_f1 >= 0.80`
    *   控制正式交付的整体质量
*   `other f1 >= 0.70`
    *   控制收口能力，避免明显过召回

## 6. round5a 正式验收结果

当前首个正式验收对象为：

*   `round5a`

核心指标为：

*   best dev macro\_f1：`0.831957`
*   test macro\_f1：`0.801067`
*   test weighted\_f1：`0.792098`
*   test accuracy：`0.790000`
*   test primary\_accuracy：`0.836667`
*   other f1：`0.701493`

逐项判断如下：

*   `dev macro_f1 >= 0.82`：通过
*   `test macro_f1 >= 0.80`：通过
*   `other f1 >= 0.70`：通过

结论：

*   `round5a` 已通过当前正式验收线

### 6.1 当前达标版本的结构信息

`round5a` 的元信息如下：

*   classifier\_type：`embedding_mlp`
*   input\_dim：`768`
*   hidden\_dim：`256`
*   dropout：`0.1`
*   num\_labels：`6`
*   embedding\_model：`gte-base-pooling`
*   pooling：`mean_over_tokens`
*   best\_epoch：`19`
*   status：`early_stopped`

## 7. round6 实验补充

### 7.1 round6\_10k：teacher 池扩容实验

`round6_10k` 的目标不是直接拿来部署，而是扩大 teacher 池并重新评估类别分布。

该轮 teacher 数据构建结果为：

*   请求总量：`13121`
*   成功弱标：`13066`
*   失败：`55`

分布如下：

*   `product_drug = 3230`
*   `study = 1171`
*   `office = 2563`
*   `menu = 1618`
*   `other = 4328`
*   `landmark_relic = 156`

这一步得到的关键信息是：

*   总量已经足够大
*   但 `landmark_relic` 仍然严重稀缺
*   round6 的主要瓶颈不是总样本量，而是关键小类供给不足

### 7.2 round6\_1405\_ratio156：按 landmark 上限反推训练分布

由于 `round6_10k` 中 `landmark_relic` 只有 `156` 条，所以构建了一套以该上限为约束的比例缩版训练集：

*   `study = 171`
*   `office = 312`
*   `product_drug = 219`
*   `menu = 141`
*   `landmark_relic = 156`
*   `other = 406`

总量为：

*   `1405`

切分为：

*   train：`1123`
*   dev：`141`
*   test：`141`

这一步的意义不是简单缩小训练集，而是：

*   用 landmark 的真实可用上限，反推其它类的相对采样比例
*   观察“关键小类受限时，整体分布如何设计更合理”

### 7.3 round6\_1405\_ratio156\_ft\_round5a：在 round5a 上继续训练

当前 round6 的核心实验版本不是从头训练，而是：

*   以 `round5a` 的 best checkpoint 为初始化
*   在 `round6_1405_ratio156` 这套比例数据上继续训练

checkpoint 元信息中已记录：

*   `init_checkpoint_dir = exp/round5a/train/checkpoints/best`

这样做的原因是：

*   继承 `round5a` 已经学到的稳定边界
*   降低小样本比例集从头训练带来的波动
*   让新增的 landmark 信息在已有边界上做局部修正

### 7.4 round6 继续训练结果

`round6_1405_ratio156_ft_round5a` 的内部集结果为：

*   train\_size：`1099`
*   dev\_size：`141`
*   test\_size：`141`
*   best\_epoch：`1`
*   status：`early_stopped`
*   best dev macro\_f1：`0.859504`
*   test accuracy：`0.858156`
*   test macro\_f1：`0.860139`
*   test weighted\_f1：`0.856961`

分项指标如下：

| 类别              | precision |   recall |       f1 | support |
| --------------- | --------: | -------: | -------: | ------: |
| study           |  0.928571 | 0.764706 | 0.838710 |      17 |
| office          |  0.848485 | 0.903226 | 0.875000 |      31 |
| product\_drug   |  0.840000 | 0.954545 | 0.893617 |      22 |
| menu            |  0.916667 | 0.785714 | 0.846154 |      14 |
| landmark\_relic |  0.833333 | 0.937500 | 0.882353 |      16 |
| other           |  0.846154 | 0.804878 | 0.825000 |      41 |

对应结论：

*   该版本内部 dev/test 明显高于 round5a
*   `landmark_relic` 在内部集上提升明显
*   `other` 在内部集上也保持稳定

### 7.5 round5a 与 round6 的关系

可以把两者理解为：

*   `round5a`
    *   首个正式过线版本
    *   是整个方案成立的基线
*   `round6_1405_ratio156_ft_round5a`
    *   在 round5a 基础上的继续训练版本
    *   内部 dev/test 指标更好
    *   是当前更新的候选主版本

## 8. 166 人工验收集补充

### 8.1 166 人工集说明

人工验收集为：

*   `翻译官-AI相机评测集`

总样本数：

*   `166`

标签分布为：

*   `office = 32`
*   `product_drug = 25`
*   `study = 30`
*   `landmark_relic = 21`
*   `menu = 20`
*   `other = 38`

这是当前最重要的人工验收集合，用来补充内部 dev/test 之外的真实业务判断。

### 8.2 round5a 在 166 人工集上的表现

`round5a` 在 166 人工集上的结果为：

*   accuracy：`0.692771`
*   macro\_f1：`0.695997`
*   avg\_ocr\_ms：`4175.8`
*   avg\_embedding\_ms：`135.9`
*   avg\_classification\_ms：`0.4`
*   avg\_total\_ms：`4506.8`

分项如下：

| 类别              | precision |   recall |       f1 | support |
| --------------- | --------: | -------: | -------: | ------: |
| study           |  0.622222 | 0.933333 | 0.746667 |      30 |
| office          |  0.733333 | 0.687500 | 0.709677 |      32 |
| product\_drug   |  0.677419 | 0.840000 | 0.750000 |      25 |
| menu            |  1.000000 | 0.700000 | 0.823529 |      20 |
| landmark\_relic |  0.647059 | 0.523810 | 0.578947 |      21 |
| other           |  0.655172 | 0.500000 | 0.567164 |      38 |

### 8.3 round6 继续训练版在 166 人工集上的表现

`round6_1405_ratio156_ft_round5a` 在 166 人工集上的结果为：

*   accuracy：`0.692771`
*   macro\_f1：`0.698888`
*   weighted\_f1：`0.688865`
*   primary\_accuracy：`0.759036`
*   avg\_ocr\_ms：`6008.4`
*   avg\_embedding\_ms：`335.7`
*   avg\_total\_ms：`6344.1`

分项如下：

| 类别              | precision |   recall |       f1 | support |
| --------------- | --------: | -------: | -------: | ------: |
| study           |  0.608696 | 0.933333 | 0.736842 |      30 |
| office          |  0.733333 | 0.687500 | 0.709677 |      32 |
| product\_drug   |  0.689655 | 0.800000 | 0.740741 |      25 |
| menu            |  1.000000 | 0.700000 | 0.823529 |      20 |
| landmark\_relic |  0.733333 | 0.523810 | 0.611111 |      21 |
| other           |  0.625000 | 0.526316 | 0.571429 |      38 |

### 8.4 round5a 与 round6 的人工集对比

| 指标                 |  round5a | round6\_1405\_ratio156\_ft\_round5a |
| ------------------ | -------: | ----------------------------------: |
| accuracy           | 0.692771 |                            0.692771 |
| macro\_f1          | 0.695997 |                            0.698888 |
| landmark\_relic f1 | 0.578947 |                            0.611111 |
| other f1           | 0.567164 |                            0.571429 |

解读如下：

*   round6 在人工集上不是“大幅跃升”，而是“小幅改善”
*   提升最明显的类是 `landmark_relic`
*   `other` 也有轻微改善
*   `study / office / other` 依然是当前最主要的混淆带

这说明：

*   round6 的继续训练是有效的
*   但当前提升上限仍然受 `landmark_relic` 数据供给限制

### 8.5 FastAPI 复用缓存 OCR 的 round6 与 GPT-5.4 对比

为了避免重复跑 `GLM-OCR`，这里复用了：

*   `exp/round6_1405_ratio156_ft_round5a/eval_ai_camera_6scenes_cached_ocr/predictions.jsonl`

然后在同一个 `FastAPI` 服务上，分别走：

*   `round6_1405_ratio156_ft_round5a` 的 `mlp` 路径
*   `gpt-5.4` 的分类路径

本节评测使用的是 `POST /classify_ocr_text`，因此：

*   `ocr_text` 与 `ocr_ms` 复用缓存结果
*   `classification_ms` 为本次实际服务调用耗时
*   `total_ms = cached_ocr_ms + 当前分类链路耗时`

这不是一次重新上传图片的完整端到端 wall clock 测量，但它能在同一份 OCR 输入上，稳定对比两条 FastAPI 分类链路的精度与分类额外耗时。

在 166 人工集上的结果为：

*   round6 accuracy：`0.692771`

*   round6 macro\_f1：`0.698888`

*   round6 weighted\_f1：`0.688865`

*   round6 primary\_accuracy：`0.759036`

*   round6 avg\_total\_ms：`6143.4`

*   round6 avg\_classification\_ms：`0.3`

*   gpt-5.4 accuracy：`0.789157`

*   gpt-5.4 macro\_f1：`0.788430`

*   gpt-5.4 weighted\_f1：`0.785235`

*   gpt-5.4 primary\_accuracy：`0.837349`

*   gpt-5.4 avg\_total\_ms：`11735.8`

*   gpt-5.4 avg\_classification\_ms：`5727.4`

分项对比如下：

| 指标                 | round6\_1405\_ratio156\_ft\_round5a |  gpt-5.4 |
| ------------------ | ----------------------------------: | -------: |
| accuracy           |                            0.692771 | 0.789157 |
| macro\_f1          |                            0.698888 | 0.788430 |
| weighted\_f1       |                            0.688865 | 0.785235 |
| primary\_accuracy  |                            0.759036 | 0.837349 |
| landmark\_relic f1 |                            0.611111 | 0.647059 |
| other f1           |                            0.571429 | 0.720930 |
| avg\_total\_ms     |                              6143.4 |  11735.8 |

进一步看每类 `f1`：

| 类别              | round6 f1 | gpt-5.4 f1 |
| --------------- | --------: | ---------: |
| study           |  0.736842 |   0.875000 |
| office          |  0.709677 |   0.750000 |
| product\_drug   |  0.740741 |   0.872727 |
| menu            |  0.823529 |   0.864865 |
| landmark\_relic |  0.611111 |   0.647059 |
| other           |  0.571429 |   0.720930 |

结论如下：

*   在同一份 OCR 输入上，`gpt-5.4` 的整体精度明显高于 round6
*   提升最明显的类是 `other`、`product_drug` 和 `study`
*   `landmark_relic` 也有提升，但幅度没有 `other` 大
*   round6 的分类头几乎不增加额外耗时，`classification_ms` 只有 `0.3 ms`
*   `gpt-5.4` 的分类阶段平均还要再花 `5727.4 ms`
*   即使复用了同一份 OCR，`gpt-5.4` 的总耗时仍接近 round6 的 `1.9x`

因此：

*   如果目标是更高精度，`gpt-5.4` 明显更强
*   如果目标是线上主链路的响应速度与成本控制，`round6 + GTE + MLP` 依然更适合作为默认方案

## 9. round5a 与 GPT-5.4 对拍结论

### 使用 1000 条随机样本对拍

`round5a` 与 `GPT-5.4` 在 1000 条随机样本上的对拍结果为：

*   agreement\_rate：`0.727`
*   accuracy\_vs\_gpt：`0.727`
*   macro\_f1\_vs\_gpt：`0.597997`
*   weighted\_f1\_vs\_gpt：`0.745017`
*   primary\_accuracy\_vs\_gpt：`0.768`
*   avg classifier latency：`84.9 ms`
*   avg GPT latency：`4310.5 ms`

说明：

*   主模型速度优势极大
*   但真实随机样本上仍存在边界错分
*   主要风险集中在 `study / office / other` 和 `landmark_relic`

## 10. 服务实现细节

### 10.1 当前服务拓扑

当前服务拓扑如下：

*   宿主机：
    *   `GLM-OCR vLLM`
*   容器内：
    *   `FastAPI`
    *   `GTE vLLM pooling`
    *   `MLP` 分类头推理

一次 `model=mlp` 请求的大致流程是：

1.  图片上传到 FastAPI
2.  FastAPI 调用宿主机 `GLM-OCR`
3.  OCR 文本返回
4.  FastAPI 调用容器内 `GTE pooling`
5.  得到 pooled embedding
6.  本地 `MLP` 输出分类结果

### 10.2 当前三个 model 参数的内部路径

`model=mlp`

*   `GLM-OCR -> GTE -> MLP`

`model=gpt-5.4`

*   `GLM-OCR -> GPT-5.4`

`model=xiaomi`

*   `GLM-OCR -> Xiaomi MiMo`

另外，为了支持复用已有 OCR 结果做离线评测，当前还补充了：

*   `POST /classify_ocr_text`

它会跳过 OCR，直接对给定的 `ocr_text` 走 `mlp` 或 `gpt-5.4` 分类链路。

### 10.3 接口返回里的耗时字段

当前接口会返回：

*   `ocr`
*   `embedding`
*   `classification`
*   `total`

含义如下：

*   `ocr`
    *   图片到 OCR 文本的耗时
*   `embedding`
    *   OCR 文本到 GTE 向量的耗时
    *   只在 `mlp` 模式下有值
*   `classification`
    *   最终分类模型本身的耗时
*   `total`
    *   整条请求从进入服务到返回的总耗时

### 10.4 当前服务代码与资产位置

核心实现如下：

*   服务入口：`web/app.py`
*   容器启动：`web/entrypoint.sh`
*   单容器运行脚本：`web/run_onebox.sh`
*   GTE 基座：`exp/full/export/encoder_model_v4`
*   当前部署分类头：`exp/round6_1405_ratio156_ft_round5a/train/checkpoints/best`

### 10.5 当前 FastAPI 结构化日志

当前 `/classfiy` 已补充结构化日志，默认会打印：

*   `filename`
*   `model`
*   `client_ip`
*   `ocr_ms`
*   `embedding_ms`
*   `classification_ms`
*   `total_ms`
*   `ocr_text_len`
*   `primary_category`
*   `secondary_category`

对复用 OCR 的离线评测，`/classify_ocr_text` 也会记录同风格日志，只是 `ocr_ms` 为空。

这使得慢请求可以明确判断卡在：

*   OCR
*   embedding
*   还是分类阶段

## 11. 当前卡点与经验沉淀

已经验证并沉淀出的关键经验包括：

1.  直接端到端微调整个基座模型，在当前环境下稳定性不足
2.  `GTE + MLP` 是当前最稳的训练路线
3.  teacher 池足够大后，训练集分布设计比继续盲目扩大弱标更重要
4.  `other` 必须被单独约束，否则会出现明显过召回
5.  `landmark_relic` 的真实瓶颈不是训练器，而是高质量样本供给不足
6.  第三方多模态模型适合补充，不适合作为当前主链路
7.  FastAPI 的主要耗时通常在 OCR，不在分类头

