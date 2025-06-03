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
        output_dir = "output/formatted"  # 修改路径
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)  # 确保目录存在，并允许父目录已存在
            
        # 获取所有md文件
        article_files = glob.glob(f"{output_dir}/*.md")  # 修改为查找 .md 文件
        articles = []
        
        for file_path in article_files:
            try:
                # 读取文件的前几行来提取标题
                with open(file_path, "r", encoding="utf-8") as f:
                    # 优化标题提取，尝试读取完整的第一行
                    first_line = f.readline().strip()
                    if not first_line: # 如果第一行是空的，尝试读取整个文件获取标题
                        content_for_title = f.read(1000)
                        title = extract_title(content_for_title)
                    else:
                        title = extract_title(first_line)

                articles.append({"title": title, "path": file_path})
            except Exception as e:
                # 如果无法读取文件，使用文件名作为标题
                filename = os.path.basename(file_path)
                articles.append({"title": filename, "path": file_path})
                
        # 按文件名（通常包含日期）降序排序，最新的在前面
        articles.sort(key=lambda x: os.path.basename(x['path']), reverse=True)
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
        # 返回错误信息给summary_output，其他输出保持不变或设为None/默认值
        return f"错误: {file_name}", None, "", [], "", [], gr.update(choices=[(a["title"], a["path"]) for a in get_saved_articles()])
    
    state.article_text = article_text
    state.article_title = extract_title(article_text)
    state.current_file = file_name
    
    # 分析文章要点
    points, error = analyze_article_points(article_text)
    if error:
        return f"文章已提取，但分析要点时出错: {error}", article_text, state.article_title, [], "", [], gr.update(choices=[(a["title"], a["path"]) for a in get_saved_articles()])
    
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
    
    # 更新对比文章选择器的选项
    comparison_choices = [(a["title"], a["path"]) for a in get_saved_articles()]
    
    return summary, article_text, state.article_title, points, default_note, [], gr.update(choices=comparison_choices, value=[])

# 处理文件选择
def handle_file_selection(selected_value):
    if selected_value is None:
        # 返回错误信息给summary_output，其他输出保持不变或设为None/默认值
        return "请选择一个文件", None, "", [], "", [], gr.update(choices=[(a["title"], a["path"]) for a in get_saved_articles()])
    
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
            return f"无效的文件选择: {selected_value}", None, "", [], "", [], gr.update(choices=[(a["title"], a["path"]) for a in get_saved_articles()])
    
    # 检查索引是否有效
    if idx < 0 or idx >= len(articles):
        # 返回错误信息给summary_output，其他输出保持不变或设为None/默认值
        return f"无效的文件索引: {idx}", None, "", [], "", [], gr.update(choices=[(a["title"], a["path"]) for a in get_saved_articles()])
    
    # 获取选中的文章信息
    file_info = articles[idx]
    
    # 加载选中的文章
    article_text, title, file_path = load_saved_article(file_info["path"])
    if article_text is None:
        # 返回错误信息给summary_output，其他输出保持不变或设为None/默认值
        return f"加载文章失败", None, "", [], "", [], gr.update(choices=[(a["title"], a["path"]) for a in get_saved_articles()])
    
    state.article_text = article_text
    state.article_title = title
    state.current_file = os.path.basename(file_path)
    
    # 分析文章要点
    points, error = analyze_article_points(article_text)
    if error:
        return f"文章已加载，但分析要点时出错: {error}", article_text, title, [], "", [], gr.update(choices=[(a["title"], a["path"]) for a in get_saved_articles()])
    
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
    
    # 更新对比文章选择器的选项
    comparison_choices = [(a["title"], a["path"]) for a in get_saved_articles()]
    
    return summary, article_text, title, points, default_note, [], gr.update(choices=comparison_choices, value=[])

# 聊天机器人处理函数
def chatbot(message, history, comparison_article_paths=None):
    if not state.article_text:
        return "请先加载或提取主文章内容。您可以在'文章来源'部分提供URL或选择已保存的文章。"
    
    llm, error = get_llm()
    if llm is None:
        return error

    # 构建基础上下文和系统提示
    # 考虑LLM的总上下文窗口，例如 deepseek-chat 通常有 32k tokens
    # 假设平均一个中文字符约等于2个token，一个英文字符约等于1个token
    # 主文章内容限制，例如 8000 字符 (约 16k tokens，留足空间给其他内容和回复)
    main_article_char_limit = 8000
    # 每篇对比文章内容限制，例如 4000 字符 (约 8k tokens)
    comparison_article_char_limit = 4000

    system_prompt = "你是一个AI伴读助手，帮助用户理解文章。你的回答应该简洁明了，并且在回答后提出一个相关的问题，引导用户继续思考。"
    current_article_context = f"主文章《{state.article_title}》内容摘要：\n{state.article_text[:main_article_char_limit]}...\n\n"

    if comparison_article_paths:
        system_prompt = (
            "你是一位专业的AI研究助手，擅长深度对比和分析多篇文章。\n"
            "请仔细阅读以下所有提供的文章材料。\n"
            "针对用户的问题，你需要：\n"
            "1. 明确指出信息来源于哪篇文章（例如，'根据《文章A》...' 或 '《文章B》则认为...'）。\n"
            "2. 深入比较这些文章在相关观点上的异同点、各自的侧重点和论证方式。\n"
            "3. 如果适用，整合不同文章的观点，形成一个更全面的看法。\n"
            "4. 避免简单罗列，要进行有深度的分析和综合。\n"
            "5. 在回答后，可以提出一个引导用户进一步思考这些文章间联系或差异的问题。"
        )
        current_article_context += "以下是用于对比分析的其他文章材料：\n"
        for i, path in enumerate(comparison_article_paths):
            try:
                comp_content, comp_title, _ = load_saved_article(path)
                if comp_content:
                    current_article_context += f"\n--- 对比文章 {i+1}: 《{comp_title}》内容摘要 ---\n{comp_content[:comparison_article_char_limit]}...\n"
            except Exception as e:
                current_article_context += f"\n--- 无法加载对比文章 {i+1} ({os.path.basename(path)}): {e} ---\n"
        current_article_context += "\n请基于以上所有文章材料进行回答。\n"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请分析以下文本：\n{current_article_context}\n\n现在，针对以上内容，回答我的问题。"} # 更明确地指示LLM基于提供的上下文
    ]
    
    # 添加对话历史
    for h_user, h_assistant in history:
        messages.append({"role": "user", "content": h_user})
        if h_assistant:
            messages.append({"role": "assistant", "content": h_assistant})
    
    # 添加当前问题
    messages.append({"role": "user", "content": message})
    
    try:
        # 调用LLM
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        return f"生成回复时出错：{str(e)}"

# 新增：保存当前文章到 formatted 文件夹
def save_article_to_formatted(article_content, base_article_title, user_custom_title=None):
    if not article_content:
        return "文章内容为空，未保存"
    
    effective_title = base_article_title
    content_to_save = article_content

    if user_custom_title and user_custom_title.strip():
        effective_title = user_custom_title.strip()
        content_to_save = f"{effective_title}\n\n{article_content}"
    
    if not effective_title: # Fallback if all titles are empty
        effective_title = "无标题文章"

    try:
        output_dir = "output/formatted"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 清理标题以用作文件名，并限制长度
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in effective_title)[:50]
        filename = f"{output_dir}/{timestamp}_{safe_title}.md"

        with open(filename, "w", encoding="utf-8") as f:
            f.write(content_to_save)

        return f"文章已保存至 {filename}"
    except Exception as e:
        return f"保存文章失败：{str(e)}"

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
                choices=[{"title": article["title"], "value": i} for i, article in enumerate(get_saved_articles())], # value is index
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

                    # 新增：自定义标题输入框
                    custom_title_input = gr.Textbox(
                        label="自定义文章标题 (可选, 用于保存)", 
                        placeholder="输入自定义标题，将覆盖提取的标题用于保存"
                    )

                    # 新增：保存文章按钮和状态显示
                    with gr.Row():
                        save_article_btn = gr.Button("保存当前文章到 formatted 文件夹", variant="primary")
                    save_article_status_output = gr.Textbox(label="保存状态", interactive=False, visible=True)
                
                # 阅读与笔记标签页
                with gr.TabItem("💬 阅读与笔记") as tab_chat:
                    with gr.Row():
                        # 聊天区域
                        with gr.Column(scale=3):
                            gr.Markdown("#### 多文章对比选择")
                            comparison_article_selector = gr.CheckboxGroup(
                                label="选择其他已保存的文章加入对比 (可选):",
                                choices=[(article["title"], article["path"]) for article in get_saved_articles()], # value is path
                                value=[],
                                interactive=True
                            )
                            gr.Markdown("---") # 分隔线
                            
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
                                # 移除了 save_note_btn
                            save_status = gr.Textbox(label="操作状态", visible=True) # 此状态框现在主要由Flomo使用
    
    # 事件处理
    # 提取文章
    extract_btn.click(
        fn=process_url,
        inputs=[url_input],
        outputs=[summary_output, article_output, custom_title_input, gr.JSON(visible=False), note_input, chat_interface, comparison_article_selector]
    ).then(lambda: gr.Tabs(selected=0), None, tabs)
    
    # 刷新文章列表
    def update_all_article_lists():
        articles = get_saved_articles()
        dropdown_choices = [{"title": article["title"], "value": i} for i, article in enumerate(articles)]
        checkbox_choices = [(article["title"], article["path"]) for article in articles]
        return gr.update(choices=dropdown_choices), gr.update(choices=checkbox_choices, value=[])
    
    refresh_btn.click(
        fn=update_all_article_lists,
        inputs=[],
        outputs=[saved_articles, comparison_article_selector]
    )
    
    saved_articles.change(
        fn=handle_file_selection,
        inputs=[saved_articles],
        outputs=[summary_output, article_output, custom_title_input, gr.JSON(visible=False), note_input, chat_interface, comparison_article_selector]
    ).then(lambda: gr.Tabs(selected=0), None, tabs)
    
    # 新增：处理保存文章按钮点击事件
    def handle_save_article_click(custom_title_from_input): # 接收自定义标题
        if not state.article_text:
            return "没有文章内容可保存。"
        # 将 state.article_title 作为基础标题，custom_title_from_input 作为用户自定义标题传入
        return save_article_to_formatted(state.article_text, state.article_title, custom_title_from_input)

    save_article_btn.click(
        fn=handle_save_article_click,
        inputs=[custom_title_input], # 从自定义标题输入框获取输入
        outputs=[save_article_status_output]
    )
    
    # 聊天功能
    def chat_respond(message, history, comparison_paths): # Added comparison_paths
        if not message:
            # Return current history and empty input string if message is empty
            return history, "" 
        
        # 添加用户消息到历史
        history.append([message, None])
        
        # 生成回复
        response_text = chatbot(message, history[:-1], comparison_paths) # Pass comparison_paths
        
        # 更新最后一条消息的回复
        history[-1][1] = response_text
        
        return history, "" # Return updated history and clear input
    
    chat_send_btn.click(
        fn=chat_respond,
        inputs=[chat_input, chat_interface, comparison_article_selector], # Added comparison_article_selector
        outputs=[chat_interface, chat_input], # chat_input to clear it
        queue=True
    ) # .then(lambda: "", None, chat_input) # This is now handled by chat_respond returning "" for chat_input
    
    chat_input.submit(
        fn=chat_respond,
        inputs=[chat_input, chat_interface, comparison_article_selector], # Added comparison_article_selector
        outputs=[chat_interface, chat_input], # chat_input to clear it
        queue=True
    ) # .then(lambda: "", None, chat_input) # This is now handled by chat_respond returning "" for chat_input
    
    # 清除笔记输入框内容
    chat_clear_btn.click(
        fn=lambda: [],
        inputs=[],
        outputs=[chat_interface]
    )# 如果有清除笔记按钮，可以保留
    
    # 发送到Flomo
    flomo_btn.click(
        fn=send_to_flomo,
        inputs=[note_input],
        outputs=[save_status] # Flomo 操作状态会更新到笔记区的 save_status
    )
    
    # 实时更新笔记内容到state
    note_input.change(
        fn=update_note_content,
        inputs=[note_input],
        outputs=[] # 不需要直接输出，只更新state
    )

demo.launch(share=True, server_name="0.0.0.0", server_port=7860)