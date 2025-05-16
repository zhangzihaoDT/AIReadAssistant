const axios = require('axios');
const cheerio = require('cheerio');
const path = require('path');
const fs = require('fs');
const puppeteer = require('puppeteer'); // 新增：引入 puppeteer

// 创建默认代理配置
const defaultProxyConfig = null;

// 创建axios实例
const instance = axios.create({
    timeout: 180000, // 增加默认超时时间到180秒
    maxRedirects: 15, // 增加重定向次数以处理复杂的WordPress站点
    proxy: defaultProxyConfig,
    // 添加代理错误处理
    proxyErrorHandler: async (err) => {
        console.error('代理连接错误:', err.message);
        if (defaultProxyConfig && err.code === 'ECONNREFUSED') { // Check if defaultProxyConfig is not null
            if (defaultProxyConfig.retries > 0) {
                console.log(`代理连接失败，剩余重试次数: ${defaultProxyConfig.retries}`);
                defaultProxyConfig.retries--;
                // 等待一段时间后重试
                await new Promise(resolve => setTimeout(resolve, 2000));
                return instance(err.config); // Ensure 'instance' is correctly referenced or passed
            }
            console.error(`无法连接到代理服务器 ${defaultProxyConfig.host}:${defaultProxyConfig.port}，请确保代理服务正在运行`);
            console.error('如需修改代理配置，请更新defaultProxyConfig对象');
        }
        throw err;
    },
    headers: { // Consolidated headers
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, compress, deflate, br', // 'compress' is less common now, but keeping as per original
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1', // Added from the first headers block
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1'
    },
    validateStatus: function (status) {
        return status >= 200 && status < 500; // 允许处理500以下的状态码
    },
    // 添加重试配置
    retry: 5, // 增加重试次数
    retryDelay: (retryCount) => {
        return Math.min(1000 * Math.pow(2, retryCount), 10000); // 指数退避策略
    },
    retryCondition: (error) => {
        if (axios.isAxiosError(error)) {
            // 记录重试信息
            console.log(`请求失败，准备重试。错误类型: ${error.code}`);
            if (error.response) {
                console.log(`响应状态: ${error.response.status}`);
            }
            
            return (
                error.code === 'ECONNABORTED' ||
                error.code === 'ECONNREFUSED' ||
                error.code === 'ECONNRESET' ||
                error.code === 'ETIMEDOUT' ||
                (error.response && error.response.status >= 500)
            );
        }
        return false;
    }
});

// console.log('使用本地代理配置:', JSON.stringify(instance.defaults.proxy, null, 2)); // 代理配置当前为null，此行可注释

async function link2text(url, options = {}) {
    // 验证URL格式
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        throw new Error('无效的URL格式，URL必须以http://或https://开头');
    }

    let htmlContent;
    let $;
    let text = '';

    if (url.includes('mp.weixin.qq.com')) {
        console.log(`使用 Axios 抓取微信文章 URL: ${url}`);
        try {
            const response = await instance.get(url); // 使用全局配置的axios实例
            console.log(`成功获取页面内容 (Axios)，状态码: ${response.status}`);
            htmlContent = response.data;
            $ = cheerio.load(htmlContent);

            // 移除脚本和样式标签 (对 Axios 获取的静态内容同样有效)
            $('script').remove();
            $('style').remove();

            // 针对微信公众号文章的特殊处理
            const title = $('#activity-name').text().trim();
            if (title) {
                text += title + '\n\n';
            }
            
            const author = $('#js_name').text().trim();
            if (author) {
                text += '作者：' + author + '\n\n';
            }
            
            const contentElement = $('#js_content');
            let content = '';

            if (contentElement.length > 0) {
                content = contentElement.text().replace(/\s+/g, ' ').trim();
            }
            
            if (content) {
                text += content;
            } else {
                // 如果无法通过特定ID获取内容，则回退到通用方法
                text = $('body').text().replace(/\s+/g, ' ').trim();
            }
        } catch (error) {
            console.error(`Axios 抓取或解析URL失败 (${url}): ${error.message}`);
            // 可以根据axios错误类型进行更细致处理
            throw error; 
        }
    } else { // 默认使用 Puppeteer (包括懂车帝等其他动态网站)
        console.log(`使用 Puppeteer 抓取 URL: ${url}`);
        let browser = null; 
        try {
            browser = await puppeteer.launch({
                headless: true, 
                args: ['--no-sandbox', '--disable-setuid-sandbox'] 
            });
            const page = await browser.newPage();
            
            await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36');
            
            await page.goto(url, { waitUntil: 'networkidle0', timeout: 180000 });

            htmlContent = await page.content(); 
            console.log(`成功获取页面内容 (Puppeteer)，准备解析...`);
            $ = cheerio.load(htmlContent);
            
            $('script').remove();
            $('style').remove();
            
            if (url.includes('dongchedi.com')) {
                console.warn(`提示：对于懂车帝页面 (${url})，建议配置更精确的内容选择器以提升提取质量和准确性。目前使用通用提取方式。`);
                // 示例：如果这是懂车帝的文章页，您可能需要找到文章主体内容的特定选择器
                // const articleBody = $('.article-content-selector').text(); // 替换为真实的选择器
                // if (articleBody) {
                //     text = articleBody;
                // } else {
                //     text = $('body').text().replace(/\s+/g, ' ').trim();
                // }
                // 对于车型对比页，结构更复杂，可能需要提取多个部分或表格数据
                // 您可以使用 page.evaluate() 配合浏览器 DOM API 进行更复杂的提取
                /*
                text = await page.evaluate(() => {
                    // 此处编写浏览器环境的JS代码来提取内容
                    // 例如：document.querySelector('.main-content-class')?.innerText
                    // 或更复杂的逻辑来组合多个元素的内容
                    const mainContent = document.querySelector('article') || document.body;
                    return mainContent.innerText.replace(/\s+/g, ' ').trim();
                });
                */
                text = $('body').text().replace(/\s+/g, ' ').trim(); // 当前作为后备
            } else {
                // 其他类型的使用Puppeteer的页面，使用通用提取
                text = $('body').text().replace(/\s+/g, ' ').trim();
            }

        } catch (error) {
            console.error(`Puppeteer 抓取或解析URL失败 (${url}): ${error.message}`);
            if (error.name === 'TimeoutError') {
                console.error('Puppeteer 导航超时，页面可能过于复杂或网络问题。');
            }
            throw error;
        } finally {
            if (browser) {
                await browser.close(); 
                console.log('Puppeteer 浏览器已关闭');
            }
        }
    }
            
    // 通用文本清理
    text = text
        .replace(/[\u200B-\u200D\uFEFF]/g, '') // 移除零宽字符
        .replace(/\s*\n\s*/g, '\n') // 规范化换行
        .trim();
            
    return text;
}

module.exports = link2text;

// 保存提取的文本到文件
async function saveTextToFile(text, outputDir) {
    try {
        // 确保输出目录存在
        if (!fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
        }

        // 使用ISO时间戳作为文件名
        const timestamp = new Date().toISOString().replace(/:/g, '');
        const filePath = path.join(outputDir, `${timestamp}.txt`);

        // 写入文件
        await fs.promises.writeFile(filePath, text, 'utf8');
        console.log(`文本已保存到: ${filePath}`);
        return filePath;
    } catch (error) {
        console.error('保存文件失败:', error.message);
        throw error;
    }
}

// 如果直接运行此文件
if (require.main === module) {
    const url = process.argv[2];
    // const timeout = process.argv[3] ? parseInt(process.argv[3]) : 30000; // 这个 timeout 原本是给 axios 的

    if (!url) {
        console.error('请提供一个URL作为参数');
        process.exit(1);
    }
    
    const outputDir = path.join(__dirname, '../output');
    link2text(url, { outputDir }) // outputDir 选项在当前 link2text 实现中未直接使用，但保留以备将来扩展
        .then(async text => {
            console.log('提取的文本内容 (前200字符):', text.substring(0, 200) + '...');
            await saveTextToFile(text, outputDir);
        })
        .catch(error => {
            // 错误已在 link2text 中打印，这里可以只退出
            // console.error(error.message); 
            process.exit(1);
        });
}