# 训练 Aria 自己的模型：按量化研究的标准来做

一次微调就像一个交易策略：回测里漂亮的数字，很可能只是看过答案、样本太少或运气好。
所以这里先定规则，再碰数据。规则写进了代码（`aria_code/training/`），不靠自觉。

## 1. 对应关系

| 量化研究 | 训练 Aria |
|---|---|
| 不用未来数据（无前视偏差） | 锁定的测试集（`hard` 套件）永远不进训练；轨迹只要碰过评分文件就丢弃 |
| 样本外检验，最终测试集只用一次 | 调参只看验证集；锁定测试集只在最后决定是否上线时跑一次，并记录在案 |
| 多重检验 | 每看一次锁定测试集都记一笔；看得越多，结论越不可信 |
| 超额收益要有置信区间 | 和「基座模型 + Aria 提示词」成对比较，每题重复多次，用 bootstrap 区间和符号检验，区间不跨 0 才算提升 |
| 幸存者偏差 | 只有评分通过、且自身验收没有失败的轨迹才是样本；碰巧通过的不算 |
| 交易成本 | 同时报告每题耗时（和 token），分数涨了但成本翻倍要说出来 |
| 行业暴露 | 编程、金融、物流的样本数量单独统计，避免训出偏科的模型 |
| 样本内 vs 样本外 | 私有仓库 `artheras/aria-evals-holdout` 里放公开题的「孪生题」（同一能力，换数据、数字和措辞）。公开分数明显高于孪生题分数，说明公开题被模型见过或被调参调过头 |
| 情景生成 | 用题目模板换数据、换数字批量生成变体扩充训练集；但测试集必须是没见过的模板，才检验得到泛化 |

## 2. 现在能做什么、不能做什么

- **能微调的模型**：Vertex AI 的监督微调支持 `gemini-3.5-flash`（也是 Aria 的默认模型）和 `gemini-3.1-flash-lite`；2.5 系列随模型一起退役。Gemma 走开源模型微调路径。见 [Tune Gemini models with supervised fine-tuning](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-use-supervised-tuning)。
- **数据还不够**：50 道题、每题几次，只有几十条轨迹；监督微调一般需要几百到几千条高质量样本。在数据够之前训练，得到的只会是过拟合。

## 3. 步骤

1. **测基线（不训练）。** 用 `gemini-3.5-flash` 跑 Evals，`--repeat 3`，保存报告和轨迹。这是之后所有比较的基准。
2. **扩充训练数据。** 为 core 和 operations 的题目写参数化的变体生成器（换数据、换数字、换货主），每个模板几十个变体；`hard` 套件不生成变体，保持锁定。
3. **收集轨迹。** 在变体上跑 Evals（可以用更强的模型做「老师」，例如 `gemini-3.8-flash`），只保留验证通过的轨迹。
4. **构建数据集。**

   ```bash
   python -m aria_code.training.sft_dataset trajectories/ --suites evals/suites --out sft/
   ```

   输出 `train.jsonl`、`validation.jsonl`（Vertex Gemini 微调格式）和 `manifest.json`（每个输入文件的 sha256、规则、各领域样本数、被排除的原因、锁定的题目）。

5. **在 Vertex 上微调** `gemini-3.5-flash`，训练集用 `train.jsonl`，验证集用 `validation.jsonl`。
6. **在验证集上比较。** 用微调后的模型跑 Evals（同样 `--repeat 3`），然后：

   ```bash
   python -m aria_code.training.compare baseline/*.json --candidate tuned/*.json
   ```

   输出成对比较的平均提升、95% 区间、变好/变差的题数、符号检验 p 值和耗时。

7. **上线的门槛**（全部满足才进行下一步）：
   - 验证集上 `ci95` 的下限大于 0；
   - 没有任何一个领域（编程、金融、物流）的平均通过率下降超过 5 个百分点；
   - 平均耗时增加不超过 25%。
8. **锁定测试集，只跑一次。** 用 `hard` 套件比较基线和候选模型，结论记录在发布说明里。不通过就回到第 2 步，并且这次查看也要记录下来。

## 4. 私有保留集（孪生题）

- **放在哪里**：`artheras/aria-evals-holdout`，结构与 `evals/` 相同（`suites/*.yaml`、`fixtures/`），每道题用 `twin_of` 写明对应的公开题。公开仓库里不出现保留集的任何内容。
- **怎么跑**：仓库设置了 `HOLDOUT_DEPLOY_KEY`（保留集仓库的只读 deploy key）时，Evals 工作流会拉取并运行保留集；没设置就跳过。
- **不公开什么**：保留集的报告和轨迹不上传为 artifact，日志不打印题目，成绩表只显示通过数、均值 ± 标准误，以及「公开 − 孪生」的差距和 95% 区间：

  ```bash
  python -m aria_code.evals.gap --public evals-*.json --holdout holdout.json --suites holdout/suites/*.yaml
  ```

  区间下限大于 0，就说明公开分数高估了真实能力。
- **不进训练**：保留集的题目、轨迹和答案永远不进训练集，也不按它生成变体。

## 5. 不做的事

- 不在锁定测试集上调参、挑检查点或改提示词。
- 不把评分文件、标准答案或 `eval.outcome` 放进任何训练样本。
- 不只报单次运行的分数；每个套件都带标准误。
