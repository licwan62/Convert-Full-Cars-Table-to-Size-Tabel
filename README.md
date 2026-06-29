# 尺码表压缩工作流

这个目录用于把全量 TSV 尺码表转换成可交付的压缩表，并按需要生成适配器表、压缩日志、原子事实表和检查表。

当前主入口是 `process_tsv.py`。日常建议优先使用它完成整套流程；`build_adapter.py` 和 `check_atom.py` 主要用于单独补跑某一段结果。

## 环境准备

第一次使用先安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

之后每次进入目录，只需要先启用环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

## 推荐工作流

### 1. 放入输入文件

把待处理的全量 TSV 放到：

```text
data/input/
```

例如：

```text
data/input/full0628.tsv
```

### 2. 只生成压缩表

适合先快速看非皮卡、皮卡压缩结果：

```powershell
python .\process_tsv.py .\data\input\full0628.tsv
```

输出会写到：

```text
data/output/full0628/
```

主要结果在：

```text
data/output/full0628/compress/
```

### 3. 生成完整交付结果

如果需要同时生成适配器表，并检查高度压缩表是否覆盖原子事实，使用：

```powershell
python .\process_tsv.py .\data\input\full0628.tsv --with-adapter --check-atom
```

这通常是最终交付前最常用的命令。

它会生成：

```text
data/output/full0628/compress/full0628_非皮卡无损压缩表.tsv
data/output/full0628/compress/full0628_非皮卡高度压缩表.tsv
data/output/full0628/compress/full0628_皮卡无损压缩.tsv
data/output/full0628/compress/full0628_皮卡高度压缩表.tsv
data/output/full0628/compress/full0628_原子事实表.tsv
data/output/full0628/compress/full0628_压缩log.tsv
data/output/full0628/adapter/full0628_适配器.tsv
data/output/full0628/adapter/full0628_适配器log.tsv
data/output/full0628/adapter/submodels_adapter_fact.tsv
data/output/full0628/adapter/fitments_adapter_fact.tsv
data/output/full0628/check/full0628_非皮卡原子检查.tsv
data/output/full0628/check/full0628_皮卡原子检查.tsv
data/output/full0628/full0628_output.xlsx
```

Excel 文件会把主要结果放进一个工作簿，方便人工查看。

## 常用命令例子

### 换输出目录

```powershell
python .\process_tsv.py .\data\input\full0628.tsv -o .\data\output_test
```

结果会写到：

```text
data/output_test/full0628/
```

### 输入不是 UTF-8 BOM 编码

默认读取编码是 `utf-8-sig`。如果源文件是 GBK：

```powershell
python .\process_tsv.py .\data\input\full0628.tsv --encoding gbk
```

### 使用指定的适配器检查数据源

默认使用：

```text
database/submodels.tsv
database/4Afitment_base.tsv
```

如果要换成其他文件：

```powershell
python .\process_tsv.py .\data\input\full0628.tsv --with-adapter --sub-model .\database\submodels.tsv --fitments .\database\4Afitment_base.tsv
```

### 单独补跑适配器

如果压缩结果已经有了，只想重新生成适配器：

```powershell
python .\build_adapter.py .\data\input\full0628.tsv -o .\data\output
```

输出位置：

```text
data/output/full0628/adapter/
```

### 单独检查原子事实和某张压缩表

例如检查非皮卡高度压缩表：

```powershell
python .\check_atom.py --atom .\data\output\full0628\compress\full0628_原子事实表.tsv --compress .\data\output\full0628\compress\full0628_非皮卡高度压缩表.tsv -o .\data\output\full0628\check
```

会生成：

```text
data/output/full0628/check/full0628_原子事实表_check.tsv
```

## 参数说明

### process_tsv.py

```powershell
python .\process_tsv.py <输入TSV> [参数]
```

常见参数：

```text
-o, --output-dir      输出根目录，默认 data/output
--encoding            输入 TSV 编码，默认 utf-8-sig
--field-profile       字段映射 YAML，用于把输入 TSV 的自定义列名映射成脚本标准字段
--with-adapter        同时生成适配器、适配器日志和适配器事实表
--sub-model           子车系事实源，默认 database/submodels.tsv
--fitments            全量 fitments 事实源，默认 database/4Afitment_base.tsv
--check-atom          生成非皮卡/皮卡高度压缩表的原子检查结果
```

### build_adapter.py

```powershell
python .\build_adapter.py <输入TSV> [参数]
```

常见参数：

```text
-o, --output-dir              输出根目录，默认 data/output
--sub-model                   子车系事实源
--fitments                    全量 fitments 事实源
--sub-model-fact-output       指定子车系事实表输出文件
--fitments-fact-output        指定 fitments 事实表输出文件
--encoding                    输入 TSV 编码，默认 utf-8-sig
--field-profile               字段映射 YAML，用于兼容自定义输入列名
```

### check_atom.py

```powershell
python .\check_atom.py --atom <原子事实表> --compress <压缩表> [参数]
```

常见参数：

```text
--atom              原子事实表 TSV，通常是 *_原子事实表.tsv
--compress          要检查的压缩表 TSV
-o, --output-dir    检查结果输出目录
--encoding          输入 TSV 编码，默认 utf-8-sig
```

## 输入字段

脚本会兼容旧字段名，但推荐全量 TSV 使用当前字段。

非皮卡压缩需要：

```text
品牌
前台车型
结构
版本
年份区间
最终尺码
```

皮卡压缩需要：

```text
品牌
前台车型
版本
年份区间
最终尺码
驾驶室类型
货斗长度_ft
```

适配器需要：

```text
品牌
前台车型
子车系
年份区间
最终尺码
```

兼容规则：

```text
如果没有 前台车型，会尝试使用 车型名 或 车姓名
如果没有 主车型，会用 品牌 + 前台车型 自动生成
如果没有 最终尺码，但有 对应尺码，会使用 对应尺码
开始年 可为空；为空时从 年份区间 左端解析
年份区间 不能为空；为空会直接报错
```

### 使用字段 profile 兼容自定义列名

可以用 YAML 配置输入 TSV 的列名。脚本内部仍然使用标准字段名，profile 只负责把你的输入列复制/映射到标准字段。

示例命令：

```powershell
python .\process_tsv.py .\data\input\full0628.tsv --field-profile .\field_profile.default.yaml --with-adapter
```

单独跑适配器也支持同一个参数：

```powershell
python .\build_adapter.py .\data\input\full0628.tsv --field-profile .\field_profile.default.yaml
```

profile 示例：

```yaml
columns:
  品牌:
    - Make
    - 品牌
  前台车型:
    - DisplayModel
    - 前台车型
    - 车型名
  年份区间:
    - YearRange
    - 年份区间
  最终尺码:
    - Size
    - 最终尺码
    - 对应尺码
  子车系:
    - SubModel
  驾驶室类型:
    - Cab
  货斗长度_ft:
    - BedFt

derived:
  主车型:
    join:
      - 品牌
      - 前台车型
    sep: " "

defaults:
  # 分类为空时，脚本会退回用 驾驶室类型 / 货斗长度_ft 判断是否皮卡。
  分类: ""
```

左边必须是脚本标准字段名，右边可以写你的 TSV 实际列名。某个标准字段已经存在时会直接使用它；不存在时才会按候选列名从上到下查找。`主车型` 可以通过 `derived` 自动由 `品牌 + 前台车型` 生成。

## 输出结果怎么看

`compress` 目录：

```text
*_非皮卡无损压缩表.tsv    最保守的非皮卡压缩表，不应制造原表不存在的原子事实
*_非皮卡高度压缩表.tsv    更高压缩率的非皮卡表，会经过原子事实校验逻辑
*_皮卡无损压缩.tsv        最保守的皮卡压缩表
*_皮卡高度压缩表.tsv      会尝试闭合年份、合并 BED 范围的皮卡压缩表
*_原子事实表.tsv          从输入展开出的原子事实基准
*_压缩log.tsv             每个车型压缩、合并、fallback 的过程日志
```

`adapter` 目录：

```text
*_适配器.tsv              最终适配器表，字段为 YEAR / MAKE / MODEL / SIZE
*_适配器log.tsv           被子车系事实表或 fitments 事实表过滤掉的记录
submodels_adapter_fact.tsv 子车系事实表展开结果
fitments_adapter_fact.tsv  fitments 事实表标准化结果
```

`check` 目录：

```text
*_非皮卡原子检查.tsv      非皮卡原子事实命中高度压缩表的检查结果
*_皮卡原子检查.tsv        皮卡原子事实命中高度压缩表的检查结果
```

检查表中重点看 `结果` 和 `原因`。如果有未命中、重复命中或尺码不一致，需要回到原始数据或压缩规则排查。

## 压缩逻辑简述

非皮卡会先生成无损压缩表，再尝试在同一品牌车型内继续合并年份、结构和版本。候选合并必须能通过原子事实检查：原表中的一条事实不能被压缩结果匹配到多个尺码，也不能匹配到错误尺码。

皮卡无损压缩按车型、版本、驾驶室、货斗长度和尺码合并连续年份。皮卡高度压缩会继续尝试闭合年份空洞、合并 BED 范围，但如果候选范围内存在不同尺码冲突，会 fallback 到更保守的结果。

适配器直接从全量表展开 `子车系 + 年份区间 + 最终尺码`，然后依次用 `submodels.tsv` 和 `4Afitment_base.tsv` 过滤。被过滤的记录会进入适配器日志。
