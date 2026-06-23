# TSV to Pandas Converter

这个项目用于把 Power Query 的处理逻辑迁移成 Python pandas 脚本。

## 目录

```text
.
├── data/
│   ├── input/      # 放原始 TSV 文件
│   └── output/     # 生成结果
├── process_tsv.py
├── requirements.txt
└── README.md
```

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 运行

```powershell
python .\process_tsv.py .\data\input\your_file.tsv
```

默认会在 `data/output/输入文件名/` 下输出三个 TSV 和一个多 sheet Excel：

```text
data/output/your_file/your_file_非皮卡尺码压缩.tsv
data/output/your_file/your_file_皮卡尺码压缩.tsv
data/output/your_file/your_file_适配器.tsv
data/output/your_file/your_file_output.xlsx
```

## 下一步

请把以下内容发给我：

1. TSV 表头或一个小样本。
2. Power Query 的 M 代码，通常在 Power Query 高级编辑器里复制。
3. 你希望后续字段名或输出文件名怎么调整。
