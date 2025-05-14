const axios = require('axios');
const cheerio = require('cheerio');
const path = require('path');
const fs = require('fs');

// 创建axios实例，配置重试机制和代理支持
// 创建默认代理配置
const defaultProxyConfig = null;

// 创建axios实例
const instance = axios.create({
    timeout: 180000, // 增加默认超时时间到180秒
    maxRedirects: 15, // 增加重定向次数以处理复杂的WordPress站点
    proxy: defaultProxyConfig,
    // 添加微信公众号文章的特殊处理
    headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1'
    },
    // 添加代理错误处理
    proxyErrorHandler: async (err) => {
        console.error('代理连接错误:', err.message);
        if (err.code === 'ECONNREFUSED') {
            if (defaultProxyConfig.retries > 0) {
                console.log(`代理连接失败，剩余重试次数: ${defaultProxyConfig.retries}`);
                defaultProxyConfig.retries--;
                // 等待一段时间后重试
                await new Promise(resolve => setTimeout(resolve, 2000));
                return instance(err.config);
            }
            console.error(`无法连接到代理服务器 ${defaultProxyConfig.host}:${defaultProxyConfig.port}，请确保代理服务正在运行`);
            console.error('如需修改代理配置，请更新defaultProxyConfig对象');
        }
        throw err;
    },
    headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, compress, deflate, br',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
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

console.log('使用本地代理配置:', JSON.stringify(instance.defaults.proxy, null, 2));

async function link2text(url, options = {}) {
    try {
        // 验证URL格式
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            throw new Error('无效的URL格式，URL必须以http://或https://开头');
        }

        // 如果是WordPress站点，添加特殊处理
        if (url.includes('wordpress.com') || url.includes('wp-content')) {
            // 设置WordPress专用请求头
            const wpHeaders = {
                'Cookie': 'wp-settings=1; wp-settings-time=1; wordpress_test_cookie=WP Cookie check',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': url,
                'DNT': '1',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1'
            };
            Object.assign(instance.defaults.headers, wpHeaders);
            
            // 使用命令行参数中的超时时间，如果没有则使用默认值180秒
            const timeout = process.argv[3] ? parseInt(process.argv[3]) : 180000;
            instance.defaults.timeout = timeout;
            instance.defaults.maxRedirects = 15; // 增加重定向次数
            
            // 优化重试配置
            instance.defaults.retry = 3;
            instance.defaults.retryDelay = (retryCount) => {
                return Math.min(1000 * Math.pow(2, retryCount), 10000);
            };
            
            console.log(`检测到WordPress站点，已配置专用请求头和重试策略，超时时间: ${timeout}ms`);
        }

        try {
            const response = await instance.get(url);
            console.log(`成功获取页面内容，状态码: ${response.status}`);
            
            // 记录响应头信息，用于调试
            console.log('响应头信息:', JSON.stringify(response.headers, null, 2));
            
            const $ = cheerio.load(response.data);
            
            // 移除脚本和样式标签
            $('script').remove();
            $('style').remove();
            
            // 获取文本内容
            // 针对微信公众号文章的特殊处理
            let text = '';
            
            // 获取文章标题
            const title = $('#activity-name').text().trim();
            if (title) {
                text += title + '\n\n';
            }
            
            // 获取作者信息
            const author = $('#js_name').text().trim();
            if (author) {
                text += '作者：' + author + '\n\n';
            }
            
            // 获取文章主体内容
            const content = $('#js_content').text()
                .replace(/\s+/g, ' ')
                .trim();
            
            if (content) {
                text += content;
            } else {
                // 如果无法通过特定ID获取内容，则回退到通用方法
                text = $('body').text()
                    .replace(/\s+/g, ' ')
                    .trim();
            }
            
            // 清理特殊字符和多余空白
            text = text
                .replace(/[\u200B-\u200D\uFEFF]/g, '') // 移除零宽字符
                .replace(/\s*\n\s*/g, '\n') // 规范化换行
                .trim();
            
            return text;
        } catch (error) {
            if (error.code === 'ECONNREFUSED' || error.code === 'ETIMEDOUT') {
                console.error('连接被拒绝或超时，请检查网络连接和代理配置是否正常');
                console.error('详细错误信息:', error.message);
                if (error.address && error.port) {
                    console.error(`无法连接到 ${error.address}:${error.port}`);
                }
                if (error.config && error.config.proxy) {
                    console.error('当前代理配置:', JSON.stringify(error.config.proxy, null, 2));
                }
            } else if (error.response && error.response.status === 403) {
                console.error('访问被拒绝，可能需要登录或授权');
            } else {
                console.error(`请求失败: ${error.message}`);
                if (error.config) {
                    console.error('请求配置:', JSON.stringify(error.config, null, 2));
                }
            }
            throw error;
        }
    } catch (error) {
        console.error(`抓取或解析URL失败 (${url}): ${error.message}`);
        throw error;
    }
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
    const timeout = process.argv[3] ? parseInt(process.argv[3]) : 30000;

    if (!url) {
        console.error('请提供一个URL作为参数');
        process.exit(1);
    }
    
    const outputDir = path.join(__dirname, '../output');
    link2text(url, { outputDir })
        .then(async text => {
            console.log('提取的文本内容:', text.substring(0, 200) + '...');
            await saveTextToFile(text, outputDir);
        })
        .catch(error => {
            console.error(error.message);
            process.exit(1);
        });
}