


          
# AI阅读助手

## 项目概述

AI阅读助手是一个智能工具，旨在帮助用户从网络文章中提取、分析和整理信息。该工具可以自动从URL中提取文章内容，分析文章的主要观点，并允许用户与文章内容进行交互式对话，同时提供笔记功能以便记录重要信息。

## 应用界面

![AI阅读助手界面](./images/WX20250514-134220@2x.png)

## 主要功能

- **文章提取**：从网页URL自动提取文章内容
- **要点分析**：使用AI自动分析并提取文章的3-5个主要观点
- **智能问答**：基于文章内容回答用户的问题
- **笔记功能**：自动生成包含文章要点的笔记模板，并支持用户编辑和保存
- **文章管理**：保存和管理已提取的文章，方便后续查阅

## 技术架构

项目使用以下技术栈：

- **前端界面**：Gradio（Python的Web界面库）
- **文章提取**：Node.js脚本（src/index.js）
- **AI模型**：火山方舟API（基于deepseek模型）
- **自然语言处理**：LangChain框架

## 安装与配置

### 前提条件

- Python 3.8+
- Node.js 14+
- 火山方舟API密钥

### 安装步骤

1. 克隆仓库到本地

```bash
git clone <repository-url>
cd AIReadingAssistant
```

2. 安装Python依赖

```bash
pip install -r requirements.txt
```

3. 安装Node.js依赖

```bash
npm install
```

4. 创建.env文件并配置API密钥

```
ARK_API_KEY=your_api_key_here
deepseek0324=your_model_endpoint_id
```

## 使用方法

1. 启动应用

```bash
python main.py
```

2. 在浏览器中访问Gradio界面（通常为http://127.0.0.1:7860）

3. 输入文章URL并点击"提取文章"按钮

4. 查看提取的文章内容和AI分析的要点

5. 使用聊天功能提问关于文章的问题

6. 编辑和保存笔记

## 项目结构

```
AIReadingAssistant/
├── .env                  # 环境变量配置文件
├── main.py               # 主程序入口
├── intro.md              # 项目介绍文档
├── package.json          # Node.js依赖配置
├── package-lock.json     # Node.js依赖锁定文件
├── src/
│   └── index.js          # 文章提取脚本
└── output/               # 提取的文章存储目录
    └── formatted/        # 格式化后的文章目录
```

## 核心功能实现

### 文章提取

使用Node.js脚本从网页中提取文章内容，并保存为文本文件：

```python
def extract_article(link):
    try:
        # 调用 Node.js 提取脚本
        os.system(f"node src/index.js {link}")
        
        # 从output目录获取最新的文件
        output_files = glob.glob("output/*.txt")
        if not output_files:
            return None, "未找到提取的文章文件"
            
        # 按修改时间排序，获取最新的文件
        latest_file = max(output_files, key=os.path.getmtime)
        
        # 读取文件内容
        with open(latest_file, "r", encoding="utf-8") as f:
            content = f.read()
            return content, os.path.basename(latest_file)
    except Exception as e:
        return None, f"文章提取失败：{str(e)}"
```

### AI模型集成

使用火山方舟API创建LLM实例：

```python
def get_llm():
    """创建使用火山方舟API的LLM"""
    try:
        # 检查API密钥
        api_key = os.getenv("ARK_API_KEY")
        if not api_key:
            return None, "错误：未找到 ARK_API_KEY 环境变量，请检查 .env 文件"
        
        # 检查模型名称环境变量
        model_name = os.getenv("deepseek0324")
        if not model_name:
            model_name = "deepseek0324"  # 使用默认模型名称
        
        return ChatOpenAI(
            openai_api_key=api_key, 
            openai_api_base="https://ark.cn-beijing.volces.com/api/v3",
            model_name=model_name,
            temperature=0
        ), None
    except Exception as e:
        return None, f"创建 LLM 实例时出错：{str(e)}"
```

### 文章分析

使用AI模型分析文章要点：

```python
def analyze_article_points(article_text):
    try:
        llm, error = get_llm()
        if llm is None:
            return [], error
        
        messages = [
            {"role": "system", "content": "你是一个擅长分析文章的AI助手。请提取文章的3个主要观点，并以简洁的方式呈现。"},
            {"role": "user", "content": f"请分析以下文章，提取3-5个主要观点，每个观点用一句话概括：\n\n{article_text}"}
        ]
        response = llm.invoke(messages)
        
        # 处理响应，提取要点列表
        points_text = response.content
        points = []
        
        # 简单处理，按行分割并清理
        for line in points_text.split('\n'):
            line = line.strip()
            if line and (line.startswith('- ') or line.startswith('• ') or 
                        line.startswith('1.') or line.startswith('2.') or 
                        line.startswith('3.') or line.startswith('4.') or 
                        line.startswith('5.')):
                # 移除前缀符号
                clean_line = line.lstrip('- •').lstrip('1234567890.').strip()
                if clean_line:
                    points.append(clean_line)
        
        # 如果没有正确解析出要点，则使用整个响应
        if not points:
            points = [points_text]
            
        return points, None
    except Exception as e:
        return [], f"分析文章要点失败：{str(e)}"
```

## 贡献指南

欢迎对项目进行贡献！请遵循以下步骤：

1. Fork本仓库
2. 创建您的特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交您的更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启一个Pull Request

## 许可证

本项目采用MIT许可证 - 详情请参见LICENSE文件

## 联系方式

如有任何问题或建议，请通过以下方式联系我们：

- 项目Issues页面
- 电子邮件：[your-email@example.com]

---

*注：本README文档基于项目当前状态编写，随着项目发展可能需要更新。*