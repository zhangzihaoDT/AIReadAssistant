import gradio as gr
import os
import requests
import glob
import shutil
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 加载环境变量
load_dotenv()

# 创建使用火山方舟API的LLM
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
            # 从.env文件加载的环境变量中获取API Key
            openai_api_key=api_key, 
            # 火山方舟的API基础URL
            openai_api_base="https://ark.cn-beijing.volces.com/api/v3",
            # 火山方舟的推理接入点ID
            model_name=model_name,
            temperature=0
        ), None
    except Exception as e:
        return None, f"创建 LLM 实例时出错：{str(e)}"

# 提取文章内容
def extract_article(link):
    try:
        # 调用 Node.js 提取脚本
        os.system(f"node src/index.js {link}")
        
        # 直接从output目录获取最新的文件
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

# 从文章内容中提取标题
def extract_title(article_text):
    # 简单方法：取第一行作为标题
    lines = article_text.strip().split('\n')
    if lines:
        title = lines[0].strip()
        # 如果标题太长，截断它
        if len(title) > 50:
            title = title[:47] + "..."
        return title
    return "无标题文章"

# 获取已保存的文章列表
def get_saved_articles():
    try:
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # 获取所有txt文件
        article_files = glob.glob(f"{output_dir}/*.txt")
        articles = []
        
        for file_path in article_files:
            try:
                # 读取文件的前几行来提取标题
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read(1000)  # 只读取前1000个字符
                    title = extract_title(content)
                    articles.append({"title": title, "path": file_path})
            except Exception as e:
                # 如果无法读取文件，使用文件名作为标题
                filename = os.path.basename(file_path)
                articles.append({"title": filename, "path": file_path})
                
        # 确保返回的是列表，而不是字典
        return articles
    except Exception as e:
        print(f"获取已保存文章列表时出错: {str(e)}")
        return []

# 加载已保存的文章
def load_saved_article(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content, extract_title(content), file_path
    except Exception as e:
        print(f"加载文章时出错: {str(e)}")
        return None, None, None

# 分析文章要点
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

# 全局状态
class State:
    def __init__(self):
        self.article_text = ""
        self.article_title = ""
        self.current_file = ""
        self.article_points = []
        self.link = ""
        self.note_content = ""
        self.chat_history = []

state = State()

# 处理URL提交
def process_url(url):
    state.link = url
    article_text, file_name = extract_article(url)
    if article_text is None:
        return f"错误: {file_name}", None, []
    
    state.article_text = article_text
    state.article_title = extract_title(article_text)
    state.current_file = file_name
    
    # 分析文章要点
    points, error = analyze_article_points(article_text)
    if error:
        return f"文章已提取，但分析要点时出错: {error}", article_text, []
    
    state.article_points = points
    
    # 构建摘要信息
    summary = f"## 《{state.article_title}》\n\n### 主要观点:\n"
    for i, point in enumerate(points):
        summary += f"{i+1}. {point}\n"
    
    # 重置聊天历史
    state.chat_history = []
    
    # 初始化笔记内容
    default_note = f"# {state.article_title}\n\n## 要点摘要\n\n"
    for i, point in enumerate(points):
        default_note += f"{i+1}. {point}\n"
    default_note += "\n## 我的笔记\n\n"
    state.note_content = default_note
    
    return summary, article_text, points, default_note, []

# 处理文件选择
def handle_file_selection(selected_value):
    if selected_value is None:
        return "请选择一个文件", None, [], "", []
    
    # 获取已保存的文章列表
    articles = get_saved_articles()
    
    # 检查selected_value是否为字典类型
    if isinstance(selected_value, dict) and "value" in selected_value:
        idx = selected_value["value"]
    else:
        # 尝试将selected_value转换为整数
        try:
            idx = int(selected_value)
        except (ValueError, TypeError):
            return f"无效的文件选择: {selected_value}", None, [], "", []
    
    # 检查索引是否有效
    if idx < 0 or idx >= len(articles):
        return f"无效的文件索引: {idx}", None, [], "", []
    
    # 获取选中的文章信息
    file_info = articles[idx]
    
    # 加载选中的文章
    article_text, title, file_path = load_saved_article(file_info["path"])
    if article_text is None:
        return f"加载文章失败", None, [], "", []
    
    state.article_text = article_text
    state.article_title = title
    state.current_file = os.path.basename(file_path)
    
    # 分析文章要点
    points, error = analyze_article_points(article_text)
    if error:
        return f"文章已加载，但分析要点时出错: {error}", article_text, [], "", []
    
    state.article_points = points
    
    # 构建摘要信息
    summary = f"## 《{state.article_title}》\n\n### 主要观点:\n"
    for i, point in enumerate(points):
        summary += f"{i+1}. {point}\n"
    
    # 重置聊天历史
    state.chat_history = []
    
    # 初始化笔记内容
    default_note = f"# {state.article_title}\n\n## 要点摘要\n\n"
    for i, point in enumerate(points):
        default_note += f"{i+1}. {point}\n"
    default_note += "\n## 我的笔记\n\n"
    state.note_content = default_note
    
    return summary, article_text, points, default_note, []

# 聊天机器人处理函数
def chatbot(message, history):
    if not state.article_text:
        return "请先加载或提取文章内容。您可以在'文章内容'标签页中提供URL或选择已保存的文章。"
    
    llm, error = get_llm()
    if llm is None:
        return error
    
    # 构建对话历史
    messages = [
        {"role": "system", "content": "你是一个AI伴读助手，帮助用户理解文章。你的回答应该简洁明了，并且在回答后提出一个相关的问题，引导用户继续思考。"},
        {"role": "user", "content": f"文章内容：{state.article_text[:4000]}..."}  # 限制长度
    ]
    
    # 添加对话历史
    for h in history:
        messages.append({"role": "user", "content": h[0]})
        if h[1]:  # 确保有回复
            messages.append({"role": "assistant", "content": h[1]})
    
    # 添加当前问题
    messages.append({"role": "user", "content": message})
    
    try:
        # 调用LLM
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        return f"生成回复时出错：{str(e)}"

# 保存笔记
def save_note(note_content):
    if not state.article_text:
        return "请先加载文章内容"
    
    if not note_content:
        return "笔记内容为空，未保存"
    
    try:
        # 创建保存目录
        output_dir = "output/formatted"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title = state.article_title.replace(" ", "_")[:30]  # 使用标题的前30个字符
        filename = f"{output_dir}/{timestamp}_{title}.md"
        
        # 保存文件
        with open(filename, "w", encoding="utf-8") as f:
            f.write(note_content)
            
        return f"笔记已保存至 {filename}"
    except Exception as e:
        return f"保存笔记失败：{str(e)}"

# 发送笔记到Flomo
def send_to_flomo(note_content):
    if not state.article_text:
        return "请先加载文章内容"
    
    if not note_content:
        return "笔记内容为空，未发送"
    
    try:
        # Flomo API地址
        flomo_api_url = "https://flomoapp.com/iwh/NDIwOTAx/c62bd115ef72eb46a2289296744fe0dc/"
        
        # 准备发送的数据
        # 添加文章标题作为标签
        title_tag = state.article_title.replace(" ", "_")
        data = {
            "content": f"{note_content}\n\n#AI阅读助手 #{title_tag}"
        }
        
        # 发送请求
        headers = {"Content-Type": "application/json"}
        response = requests.post(flomo_api_url, json=data, headers=headers)
        
        # 检查响应
        if response.status_code == 200:
            return "笔记已成功发送到Flomo"
        else:
            return f"发送到Flomo失败：HTTP状态码 {response.status_code}"
    except Exception as e:
        return f"发送到Flomo失败：{str(e)}"

# 更新笔记内容
def update_note_content(note):
    state.note_content = note
    return note

# 构建界面
with gr.Blocks(title="AI阅读助手", theme=gr.themes.Base()) as demo:
    gr.Markdown("# 📚 AI阅读助手")
    gr.Markdown("这个工具可以帮助你提取网页文章内容，分析要点，并与AI交互讨论文章内容。")
    
    with gr.Row():
        with gr.Column(scale=1, min_width=250):
            # 左侧面板 - 文章来源
            gr.Markdown("## 📄 文章来源")
            
            # URL输入
            url_input = gr.Textbox(label="输入文章URL", placeholder="https://example.com/article")
            extract_btn = gr.Button("提取文章", variant="primary")
            
            # 历史文章列表
            gr.Markdown("### 📚 已保存的文章")
            
            # 刷新按钮
            refresh_btn = gr.Button("刷新文章列表")
            
            # 历史文章列表（使用下拉列表展示）
            saved_articles = gr.Dropdown(
                label="选择已保存的文章",
                choices=[{"title": article["title"], "value": i} for i, article in enumerate(get_saved_articles())],
                interactive=True
            )
            
        with gr.Column(scale=4, min_width=400):
            # 中间面板 - 标签页
            with gr.Tabs() as tabs:
                # 文章内容标签页
                with gr.TabItem("📝 文章内容") as tab_article:
                    # 文章摘要
                    summary_output = gr.Markdown(label="文章摘要")
                    
                    # 文章内容
                    article_output = gr.Textbox(label="文章内容", lines=25, max_lines=30)
                
                # 阅读与笔记标签页
                with gr.TabItem("💬 阅读与笔记") as tab_chat:
                    with gr.Row():
                        # 聊天区域
                        with gr.Column(scale=3):
                            chat_interface = gr.Chatbot(
                                label="与文章对话",
                                height=480
                                # 移除不支持的参数
                                # bubble=True,
                                # avatar_images=("👤", "🤖")
                            )
                            
                            with gr.Row():
                                chat_input = gr.Textbox(
                                    placeholder="请输入您关于文章的问题...",
                                    show_label=False,
                                    container=False,
                                    scale=8
                                )
                                chat_send_btn = gr.Button("发送", variant="primary", scale=1)
                            chat_clear_btn = gr.Button("清除对话", scale=1)
                            
                            # 删除示例问题列表
                        
                        # 笔记区域
                        with gr.Column(scale=2):
                            note_input = gr.Textbox(
                                label="我的笔记",
                                lines=20,
                                placeholder="在这里记录你的想法...",
                                value=state.note_content
                            )
                            with gr.Row():   # 发送到Flomo按钮
                                flomo_btn = gr.Button("发送到Flomo", variant="primary", scale=1)
                                save_note_btn = gr.Button("保存笔记", variant="secondary", scale=1)
                            save_status = gr.Textbox(label="操作状态", visible=True)
    
    # 事件处理
    # 提取文章
    extract_btn.click(
        fn=process_url,
        inputs=[url_input],
        outputs=[summary_output, article_output, gr.JSON(visible=False), note_input, chat_interface]
    ).then(lambda: gr.Tabs(selected=0), None, tabs)
    
    # 刷新文章列表
    def update_article_list():
        articles = get_saved_articles()
        return gr.Dropdown(choices=[{"title": article["title"], "value": i} for i, article in enumerate(articles)])
    
    refresh_btn.click(
        fn=update_article_list,
        inputs=[],
        outputs=[saved_articles]
    )
    
    saved_articles.change(
        fn=handle_file_selection,
        inputs=[saved_articles],
        outputs=[summary_output, article_output, gr.JSON(visible=False), note_input, chat_interface]
    ).then(lambda: gr.Tabs(selected=0), None, tabs)
    
    # 聊天功能
    def chat_respond(message, history):
        if not message:
            return history
        
        # 添加用户消息到历史
        history.append([message, None])
        
        # 生成回复
        response = chatbot(message, history[:-1])
        
        # 更新最后一条消息的回复
        history[-1][1] = response
        
        return history
    
    chat_send_btn.click(
        fn=chat_respond,
        inputs=[chat_input, chat_interface],
        outputs=[chat_interface],
        queue=True
    ).then(lambda: "", None, chat_input)
    
    chat_input.submit(
        fn=chat_respond,
        inputs=[chat_input, chat_interface],
        outputs=[chat_interface],
        queue=True
    ).then(lambda: "", None, chat_input)
    
    chat_clear_btn.click(
        fn=lambda: [],
        inputs=[],
        outputs=[chat_interface]
    )
    
    # 保存笔记
    save_note_btn.click(
        fn=save_note,
        inputs=[note_input],
        outputs=[save_status]
    )
    
    # 发送到Flomo
    flomo_btn.click(
        fn=send_to_flomo,
        inputs=[note_input],
        outputs=[save_status]
    )
    
    # 更新笔记内容
    note_input.change(
        fn=update_note_content,
        inputs=[note_input],
        outputs=[]
    )

# 启动应用
if __name__ == "__main__":
    demo.launch()