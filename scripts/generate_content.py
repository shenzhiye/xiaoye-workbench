# -*- coding: utf-8 -*-
"""
小野工作台 - 每日内容自动生成
每天 8:00 / 14:00(北京时间) 由 GitHub Actions 触发
流程: 读取用户画像(Gist profile.json) -> 抓取多平台热榜 -> 调 Kimi 生成 -> 写入公开 Gist
生成: 10条爆款视频 + 10条二创 + 5句英语 + 20条AI资讯(国内外覆盖,分2次调用)
"""
import os, sys, json, time, re, urllib.request, urllib.error

# ---------- 配置 ----------
KIMI_KEY   = os.environ.get("KIMI_API_KEY", "")
GIST_TOKEN = os.environ.get("GIST_TOKEN", "")
GIST_ID    = os.environ.get("GIST_ID", "")
MODEL      = os.environ.get("KIMI_MODEL", "kimi-k2.6")
KIMI_URL   = "https://api.moonshot.cn/v1/chat/completions"
GIST_URL   = "https://api.github.com/gists/" + GIST_ID

# ---------- 默认画像(仅在Gist中无profile.json时使用) ----------
DEFAULT_PROFILE = {
    "name": "沈知野",
    "id": "shenzhiye3399",
    "platform": "抖音(主), 未来拓展小红书",
    "track": "教育校园",
    "audience": "28-45岁、负责孩子学习和家庭采买的妈妈",
    "role": "有活力的妈妈、家庭氛围好亲子关系好、对孩子学习很负责、有时间琢磨孩子成长、能给粉丝直接启发;长相甜美",
    "style": "灵动、有活人感、真实(不要教条不要爹味)",
    "monetization": "带货(生活/日化/美妆/学习类,视频+直播)、接广、心理咨询/陪跑",
    "keywords": ["一年级","数学思维","英语启蒙","陪孩子写作业","背单词","计算","识字"],
    "homepage": "https://v.douyin.com/TiKProte9YI/"
}

def build_profile_str(p):
    keywords = "、".join(p.get("keywords", []))
    return f"""你是「{p.get('name','沈知野')}」的专属内容策划AI。{p.get('name','沈知野')}的画像如下,所有生成内容必须贴合:

【平台】{p.get('platform','抖音')}
【赛道】{p.get('track','教育校园')}
【目标人群】{p.get('audience','28-45岁妈妈')}
【IP人设】{p.get('role','...')}
【内容风格】{p.get('style','...')}
【关键词】{keywords}
【变现模式】{p.get('monetization','...')}"""

# ---------- 当前日期与学期季节 ----------
def get_date_context():
    """返回(日期字符串, 学期状态说明)。用于注入prompt,避免AI生成过时场景。"""
    now = time.localtime()
    m = now.tm_mon
    d = now.tm_mday
    wkd = ["周一","周二","周三","周四","周五","周六","周日"][now.tm_wday]
    date_str = "{}年{}月{}日 {}".format(now.tm_year, m, d, wkd)

    if m == 7 and d >= 10:
        season = "暑假中期(学生已放假,围绕暑假安排/弯道超车/亲子陪伴/暑期学习计划/幼小衔接暑假冲刺,绝对不要生成期末复习/考试类内容)"
    elif m == 8:
        season = "暑假中后期(围绕暑假收尾/暑期学习/亲子旅行/开学前收心准备,不要生成期末复习类内容)"
    elif m == 9 and d <= 10:
        season = "开学季(围绕开学收心/新学期准备/一年级新生入学/幼小衔接)"
    elif (m == 8 and d >= 20):
        season = "暑假尾声临近开学(围绕开学收心准备/暑假总结/新学期规划)"
    elif m == 6 or (m == 7 and d <= 5):
        season = "期末考试季(围绕期末复习/考前冲刺/试卷分析/暑假规划)"
    elif m in (1, 2):
        season = "寒假期间(围绕寒假安排/春节/假期学习/下学期预习)"
    elif m == 3 and d <= 10:
        season = "开学初(围绕新学期适应/春季学习计划)"
    else:
        season = "学期中(围绕日常学习/月考/单元复习)"
    return date_str, season

# ---------- 读取Gist中的用户画像 ----------
def read_profile_from_gist():
    """从Gist读取profile.json; 不存在则返回默认画像"""
    try:
        req = urllib.request.Request(GIST_URL, headers={
            "Authorization": "Bearer " + GIST_TOKEN,
            "Accept": "application/vnd.github+json"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            g = json.loads(r.read().decode("utf-8"))
        files = g.get("files", {})
        if "profile.json" in files:
            content = files["profile.json"].get("content", "")
            if content:
                p = json.loads(content)
                print("  从 Gist 读取到用户画像: " + p.get("name", "?"))
                return p
    except Exception as e:
        print("  读取画像失败,使用默认: " + str(e))
    return DEFAULT_PROFILE

# ---------- 抓热榜 ----------
def fetch_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (WorkBuddy)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def get_hotlist():
    """抓取60s.viki.moe的抖音热榜+微博热搜+头条热点(真实近2天热点,带链接)。失败返回空列表。"""
    items = []
    sources = [
        ('抖音', 'https://60s.viki.moe/v2/douyin'),
        ('微博', 'https://60s.viki.moe/v2/weibo'),
        ('头条', 'https://60s.viki.moe/v2/toutiao'),
    ]
    for platform, url in sources:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode('utf-8'))
            arr = d.get('data', [])
            if not isinstance(arr, list):
                arr = arr.get('list', []) if isinstance(arr, dict) else []
            cnt = 0
            for it in arr[:10]:
                t = it.get('title', '')
                u = it.get('link', it.get('url', ''))
                hot_val = it.get('hot_value', it.get('hot', ''))
                if t:
                    items.append({'platform': platform, 'title': t, 'url': u, 'hot': str(hot_val)})
                    cnt += 1
            print('  [{}] 成功抓取 {} 条'.format(platform, cnt))
        except Exception as e:
            print('  [{}] 抓取失败: {}'.format(platform, str(e)[:50]))
            continue

    if not items:
        print("  所有热榜源失败,将让Kimi基于当前季节自行生成选题")
    return items

# ---------- 调 Kimi 生成 ----------
def call_kimi(profile_str, hot_text, date_ctx):
    date_str, season = date_ctx
    if hot_text.strip():
        hot_instr = """以下是今日多平台真实热榜(抖音/微博/头条,近2天热点)。你必须基于这些真实热点来创作选题:
- 从热榜中挑选与教育/亲子/孩子学习生活/家庭相关的热点(哪怕只有一点关联也可以借题发挥)
- 把这些热点改编成符合你赛道的抖音教育选题
- 如果直接相关的热点不够10条,可以基于热点反映的社会趋势/情绪/季节话题延伸创作,但每条都要标注灵感来源(来自哪个热点)
- 每条选题的sourceHot字段必须填来源热点标题(从上面热榜中选最接近的一条),如果是纯季节延伸填"季节延伸"
- 绝对不要凭空围绕某个固定主题(如只写暑假)生成10条,每条都要与当日真实热点有关联"""
    else:
        hot_instr = "今日热榜未抓取到。请基于当前季节和目标人群最关心的话题生成选题,sourceHot填'季节延伸'。"
    sys_prompt = profile_str + "\n\n" + f"""【重要】今天是 {date_str},处于{season}。生成内容必须与当前时间/季节匹配,绝对不要出现与当前季节矛盾的场景(例如暑假期间不要出现"期末复习""考试")。

{hot_instr}

结合上述画像,生成三份内容:

1.【爆款视频】生成10条基于今日真实热点改编的抖音教育赛道选题。内容方向必须覆盖:
  - 低年级学习方法(数学思维/识字/计算/背单词技巧)
  - 陪孩子写作业(高效陪写/不吼不叫/时间管理)
  - 生活习惯培养(作息/自理/专注力/手机管理)
  - 情绪疏导(孩子哭闹/厌学/亲子冲突化解)
  - 亲子日常(亲子关系/家庭氛围/陪伴妙招)
  每条字段:
  - title:选题标题(像真实抖音爆款标题,有吸引力,15-25字)
  - keywords:2-3个关键词
  - content:中心内容(2-3句概括这条视频拍什么)
  - platform:固定"抖音"
  - viralReason:为什么会火(1-2句)
  - searchKeyword:抖音搜索关键词(3-6字,用于在抖音搜到真实同类视频)
  - sourceHot:来源热点标题(从热榜中选最接近的一条原标题;纯季节延伸填"季节延伸")
2.【爆款二创】10条,把上述选题方向改编成该博主能直接拍的具体二创内容。每条:
  - title:二创标题(你的改编)
  - angle:改编角度(怎么改/跟原选题的区别)
  - keywords:2-3个关键词
  - reason:为什么值得二创
  - script:30-60字口播文案(有活人感,像妈妈在说话,不要说教)
  - platform:"抖音"
  - searchKeyword:抖音搜索关键词(3-6字)
  - sourceHot:来源热点标题(同上)
  - sourceTitle:如果借鉴了热榜某条就写原标题(用于匹配原链接),没有就留空字符串""
3.【英语学习】5句日常生活中妈妈教孩子时常用的英语口语,简单实用,适合亲子场景,不要太难。

严格只返回一个JSON对象,不要任何解释文字、不要markdown代码块标记。JSON结构:
{{"viralVideos":[{{"title":"选题标题","keywords":["关键词1","关键词2"],"content":"中心内容","platform":"抖音","viralReason":"爆火原因","searchKeyword":"搜索词","sourceHot":"来源热点"}}],"recreations":[{{"title":"二创标题","angle":"改编角度","keywords":["关键词1","关键词2"],"reason":"为什么值得二创","script":"二创文案","platform":"抖音","searchKeyword":"搜索词","sourceHot":"来源热点","sourceTitle":""}}],"englishSentences":[{{"en":"English sentence","zh":"中文翻译"}}]}}"""

    if hot_text.strip():
        user_msg = "今日热榜({}):\n".format(date_str) + hot_text
    else:
        user_msg = "（今日热榜未抓取到。今天是{}，{}。请按上述要求自行生成适合当前季节的选题。）".format(date_str, season)
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 1,
        "max_tokens": 16000
    }).encode("utf-8")
    req = urllib.request.Request(KIMI_URL, data=body, headers={
        "Authorization": "Bearer " + KIMI_KEY,
        "Content-Type": "application/json"
    })
    print("  调用Kimi生成内容(超时480s,最多重试2次)...")
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=480) as r:
                resp = json.loads(r.read().decode("utf-8"))
            content = resp["choices"][0]["message"]["content"]
            result = _parse_json_safe(content)
            if result is not None:
                return result
            print("  第{}次JSON解析失败,{}".format(attempt+1, "重试..." if attempt==0 else "返回空兜底"))
        except Exception as e:
            print("  第{}次调用失败({}),{}".format(attempt+1, str(e)[:50], "重试..." if attempt==0 else "返回空兜底"))
    return {"viralVideos": [], "recreations": [], "englishSentences": []}

# ---------- 生成AI资讯(分2次调用,每次10条,合并20条,国内外都覆盖) ----------
FIELD_SPEC = """每条字段:
- title:标题(12-20字,点明是什么事)
- category:从下列7类选一个:【技能突破】【应用落地】【国内排名】【国际动态】【教育结合】【生活实用】【行业政策】
- plainText:大白话解释是什么(1-2句,不用术语,像跟朋友聊天)
- whichAI:这条涉及哪个具体AI产品(如豆包/Kimi/ChatGPT/Claude/Gemini/文心/通义/DeepSeek/可灵/即梦/智谱/Sora等)。不涉及具体产品的行业新闻写"行业动态"
- pricing:这个AI是否收费。写"免费"/"部分免费"/"付费(月费约X元)"/"免费+付费版"
- alternatives:同类AI有哪些,核心区别一句话(如"类似还有Kimi(长文本强)、文心(中文好)")
- howToUse:具体怎么用/怎么操作(写清步骤或使用场景;行业动态就写"对普通人的影响")
- why:跟妈妈群体有什么关系(1句)

涉及AI技能升级时,说清楚是哪个AI、是否收费、同类AI区别。涉及国外AI时,说清楚国内能不能用、有没有替代品。
只返回JSON,不要解释和代码块:
{"aiNews":[{"title":"","category":"技能突破","plainText":"","whichAI":"","pricing":"","alternatives":"","howToUse":"","why":""}]}"""

def _parse_json_safe(content):
    """容错解析Kimi返回的JSON,处理常见格式问题(中文引号/多余文字/坏逗号)"""
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())
    # 1.直接解析
    try:
        return json.loads(content)
    except Exception:
        pass
    # 2.只取第一个{ 到最后一个}
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # 3.修复中文引号/尾部多余逗号
    fixed = content.replace("\u201c", '"').replace("\u201d", '"')
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*]", "]", fixed)
    try:
        return json.loads(fixed)
    except Exception:
        pass
    # 4.再尝试提取{}块
    if m:
        fixed2 = m.group(0).replace("\u201c", '"').replace("\u201d", '"')
        fixed2 = re.sub(r",\s*}", "}", fixed2)
        fixed2 = re.sub(r",\s*]", "]", fixed2)
        try:
            return json.loads(fixed2)
        except Exception:
            pass
    return None

def _call_kimi_news(prompt, label, timeout=300):
    """单次Kimi调用生成AI资讯,返回aiNews列表"""
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 1,
        "max_tokens": 8000
    }).encode("utf-8")
    req = urllib.request.Request(KIMI_URL, data=body, headers={
        "Authorization": "Bearer " + KIMI_KEY,
        "Content-Type": "application/json"
    })
    for attempt in range(2):
        print("  调用Kimi生成AI资讯[{}](超时{}s,第{}次)...".format(label, timeout, attempt+1))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
            content = resp["choices"][0]["message"]["content"]
            result = _parse_json_safe(content)
            if result is not None:
                return result.get("aiNews", [])
            print("  [{}]第{}次JSON解析失败,{}".format(label, attempt+1, "重试..." if attempt==0 else "返回空"))
        except Exception as e:
            print("  [{}]第{}次调用失败({}),{}".format(label, attempt+1, str(e)[:50], "重试..." if attempt==0 else "返回空"))
    return []

def generate_ai_news(hot, date_ctx):
    """分2次调用Kimi(每次10条),国内外都覆盖,避免单次生成20条超时。"""
    # 第1次:侧重国内AI + 教育/生活/应用类(普通人最能用上的)
    prompt1 = """你是AI资讯主编,给不懂技术的家长(28-45岁妈妈)做AI动态解读,让普通人"能用上、看得懂"。

请总结10条AI动态,这次侧重【国内AI产品】和【普通人能用上的应用】:
- 国内AI:豆包、Kimi(月之暗面)、DeepSeek、文心一言(百度)、通义千问(阿里)、智谱、可灵/即梦(字节)、腾讯混元、MiniMax等
- 内容方向优先:【教育结合】AI帮孩子学习/辅导作业、【生活实用】AI在生活中的用法、【应用落地】普通人怎么用AI、【国内排名】国产AI谁更强/谁升级了
- 每条让人觉得"我能用上/跟我有关",不要泛泛而谈

""" + FIELD_SPEC

    # 第2次:侧重国外AI + 技能突破/国际动态/行业政策
    prompt2 = """你是AI资讯主编,给不懂技术的家长(28-45岁妈妈)做AI动态解读,让普通人"能用上、看得懂"。

请总结10条AI动态,这次侧重【国外AI产品】和【AI能力突破/行业动态】:
- 国外AI:OpenAI(ChatGPT/Sora)、Google(Gemini)、Anthropic(Claude)、Meta(Llama)、Microsoft(Copilot)、xAI(Grok)、Apple、NVIDIA等
- 内容方向优先:【技能突破】AI能力突破(新模型/多模态/视频生成/Agent)、【国际动态】OpenAI/Google/Anthropic动作、【应用落地】国外AI怎么用、【行业政策】影响普通人的政策
- 涉及国外AI时,务必说清楚国内能不能用、有没有国产替代品

""" + FIELD_SPEC

    part1 = _call_kimi_news(prompt1, "国内侧重")
    print("  第1批(国内侧重)生成 {} 条".format(len(part1)))
    part2 = _call_kimi_news(prompt2, "国外侧重")
    print("  第2批(国外侧重)生成 {} 条".format(len(part2)))
    return part1 + part2

# ---------- 匹配URL(从原始热榜数据中查找) ----------
def find_url(title, hot_items):
    """精确匹配 -> 包含匹配,返回热榜中对应条目的url"""
    for h in hot_items:
        if h["title"] == title:
            return h.get("url", "")
    for h in hot_items:
        if title and (h["title"] in title or title in h["title"]):
            return h.get("url", "")
    return ""

# ---------- 写 Gist ----------
def write_gist(payload):
    body = json.dumps({
        "description": "小野工作台 - 每日内容(自动生成)",
        "files": {"content.json": {"content": json.dumps(payload, ensure_ascii=False, indent=2)}}
    }).encode("utf-8")
    req = urllib.request.Request(GIST_URL, data=body, method="PATCH", headers={
        "Authorization": "Bearer " + GIST_TOKEN,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

# ---------- 主流程 ----------
def main():
    print("=== 小野工作台 内容生成开始 ===")
    if not KIMI_KEY:
        print("ERROR: KIMI_API_KEY 未设置"); sys.exit(1)
    if not GIST_TOKEN:
        print("ERROR: GIST_TOKEN 未设置"); sys.exit(1)
    if not GIST_ID:
        print("ERROR: GIST_ID 未设置"); sys.exit(1)

    # 0. 日期与季节
    date_ctx = get_date_context()
    print("[0/5] {} | {}".format(*date_ctx))

    # 1. 读取画像
    print("[1/5] 读取用户画像...")
    profile = read_profile_from_gist()
    profile_str = build_profile_str(profile)
    print("  画像: " + profile.get("name", "?") + " / " + profile.get("track", "?"))

    # 2. 抓热榜
    print("[2/5] 抓取热榜(含知乎)...")
    hot = get_hotlist()
    print("  共获取 {} 条热点".format(len(hot)))
    hot_text = "\n".join("{}[{}] {}".format(i+1, h["platform"], h["title"]) for i, h in enumerate(hot))

    # 3. 调 Kimi 生成(爆款+二创+英语)
    print("[3/5] 调用 Kimi 生成内容...")
    result = call_kimi(profile_str, hot_text, date_ctx)
    videos = result.get("viralVideos", [])
    recr = result.get("recreations", [])
    eng = result.get("englishSentences", [])
    print("  生成 {} 条爆款视频, {} 条二创, {} 句英语".format(
        len(videos), len(recr), len(eng)))

    # 4. 匹配URL(用sourceHot/sourceTitle匹配热榜原始链接)
    for v in videos:
        if not v.get("url"):
            v["url"] = find_url(v.get("sourceHot", ""), hot)
    matched = 0
    for r in recr:
        if not r.get("url"):
            src = r.get("sourceTitle") or r.get("sourceHot") or r.get("title", "")
            r["url"] = find_url(src, hot)
            if r["url"]:
                matched += 1
    print("  二创URL匹配: {}/{}".format(matched, len(recr)))

    # 5. 生成AI资讯(分2次调用,国内外覆盖) - 失败不中断流程
    print("[4/5] 生成AI资讯(20条,分2次调用国内外覆盖)...")
    try:
        ai_news = generate_ai_news(hot, date_ctx)
        print("  共生成 {} 条AI资讯".format(len(ai_news)))
    except Exception as e:
        print("  AI资讯生成失败(不影响其他内容): {}".format(str(e)[:80]))
        ai_news = [{"title":"AI资讯本次生成超时,点刷新重试","category":"行业政策","plainText":"AI资讯内容较多生成耗时较长,偶有超时。爆款视频和二创已正常更新,稍后点右上角刷新即可重新拉取AI资讯。","whichAI":"行业动态","pricing":"免费","alternatives":"","howToUse":"点页面右上角刷新按钮重新拉取","why":"AI资讯覆盖国内外20条,生成需要更长时间"}]

    # 6. 写 Gist
    print("[5/5] 写入 Gist...")
    payload = {
        "date": time.strftime("%Y-%m-%d"),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "viralVideos": videos,
        "recreations": recr,
        "englishSentences": eng,
        "aiNews": ai_news
    }
    write_gist(payload)
    print("=== 完成! Gist 已更新 ===")

if __name__ == "__main__":
    main()
