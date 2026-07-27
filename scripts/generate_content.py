# -*- coding: utf-8 -*-
"""
小野工作台 - 每日内容自动生成
每天 8:00 / 14:00(北京时间) 由 GitHub Actions 触发
流程: 读取用户画像(Gist profile.json) -> 抓取多平台热榜 -> 调 Kimi 生成 -> 写入公开 Gist
生成: 10条爆款视频 + 10条二创 + 5句英语 + 20条AI资讯(深度解读)
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
    """抓取热榜。知乎用官方API(稳定有url),其他平台用vvhan(备选)。失败返回空列表。"""
    items = []

    # 1. 知乎热榜(官方API,稳定,有url)
    try:
        req = urllib.request.Request('https://api.zhihu.com/topstory/hot-lists/total?limit=15',
            headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode('utf-8'))
        arr = d.get('data', [])
        cnt = 0
        for it in arr[:15]:
            tgt = it.get('target', {})
            t = tgt.get('title', '')
            qid = tgt.get('id') or it.get('id')
            u = tgt.get('url') or ('https://www.zhihu.com/question/'+str(qid) if qid else '')
            if t:
                items.append({'platform':'知乎', 'title': t, 'url': u})
                cnt += 1
        print('  [知乎] 成功抓取 {} 条'.format(cnt))
    except Exception as e:
        print('  [知乎] 抓取失败: {}'.format(str(e)[:50]))

    # 2. vvhan多平台(备选,可能失效)
    vvhan_sources = [
        ('抖音',   'https://api.vvhan.com/api/hotlist/douyinHot'),
        ('B站',    'https://api.vvhan.com/api/hotlist/biliRD'),
        ('小红书', 'https://api.vvhan.com/api/hotlist/xhsHot'),
        ('微博',   'https://api.vvhan.com/api/hotlist/wbHot'),
    ]
    for platform, url in vvhan_sources:
        try:
            data = fetch_json(url)
            arr = data.get('data', []) if isinstance(data, dict) else data
            tag = platform
            cnt = 0
            for it in arr[:10]:
                t = it.get('title') or it.get('name') or ''
                u = it.get('url') or it.get('link') or ''
                if t:
                    items.append({'platform': tag, 'title': t, 'url': u})
                    cnt += 1
            print('  [{}] 成功抓取 {} 条'.format(platform, cnt))
            if len(items) >= 30:
                break
        except Exception as e:
            print('  [{}] 抓取失败: {}'.format(platform, str(e)[:50]))
            continue

    if not items:
        print("  所有热榜源失败,将让Kimi基于当前季节自行生成选题")
    return items[:30]

# ---------- 调 Kimi 生成 ----------
def call_kimi(profile_str, hot_text, date_ctx):
    date_str, season = date_ctx
    if hot_text.strip():
        hot_instr = "你现在收到一份今日多平台实时热榜(含抖音/B站/小红书/知乎)。请严格基于这些热点(不要凭空编造热榜里没有的内容)"
    else:
        hot_instr = "今日热榜抓取失败。请基于当前日期和季节状态,结合目标人群当前最关心的话题,自行生成当前最适合该博主拍摄的选题(例如暑假期间:暑假学习计划/弯道超车/亲子旅行/幼小衔接暑期准备/亲子陪伴妙招等;期末季:期末复习/考前冲刺;开学季:收心/新学期准备)"
    sys_prompt = profile_str + "\n\n" + f"""【重要】今天是 {date_str},处于{season}。生成内容必须与当前时间/季节匹配,绝对不要出现与当前季节矛盾的场景(例如暑假期间不要出现"期末复习""考试")。

{hot_instr},结合上述画像,生成三份内容:

1.【爆款视频】从热榜中挑选10条最适合该画像赛道和目标人群的视频。要求:
  - title字段直接用热榜中的原始标题,不要改写(这样后面才能匹配到原链接)
  - 补充keywords(2-3个)、content(中心内容,2-3句话概括)、viralReason(爆火原因)
  - platform字段根据热榜来源设为"抖音"/"B站"/"小红书"/"知乎"
2.【爆款二创】10条,把热点改编成该博主能直接拍的二创内容。每条:
  - title:二创标题(你的改编)
  - sourceTitle:来源热榜的原始标题(必须与热榜中某条标题一致,用于匹配原链接)
  - angle:改编角度
  - keywords:2-3个关键词
  - reason:为什么值得二创
  - script:30-60字口播文案,有活人感
  - platform:来源平台
3.【英语学习】5句日常生活中妈妈教孩子时常用的英语口语,简单实用,适合亲子场景,不要太难。

严格只返回一个JSON对象,不要任何解释文字、不要markdown代码块标记。JSON结构:
{{"viralVideos":[{{"title":"热榜原始标题(不改写)","keywords":["关键词1","关键词2"],"content":"中心内容","platform":"抖音","viralReason":"爆火原因"}}],"recreations":[{{"title":"二创标题","sourceTitle":"来源热榜原始标题","angle":"改编角度","keywords":["关键词1","关键词2"],"reason":"为什么值得二创","script":"二创文案","platform":"抖音"}}],"englishSentences":[{{"en":"English sentence","zh":"中文翻译"}}]}}"""

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
    print("  调用Kimi生成内容(超时240s)...")
    with urllib.request.urlopen(req, timeout=240) as r:
        resp = json.loads(r.read().decode("utf-8"))
    content = resp["choices"][0]["message"]["content"]
    # 兜底: 去掉可能的 markdown 代码块标记
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())
    return json.loads(content)

# ---------- 生成AI资讯(独立Kimi调用,深度解读) ----------
def generate_ai_news(hot, date_ctx):
    """生成20条AI重要新闻,深度解读,聚焦普通人能用能用懂的第一手资讯。"""
    date_str, season = date_ctx
    ai_kw = ["AI", "人工智能", "GPT", "大模型", "ChatGPT", "Claude", "Gemini",
             "OpenAI", "机器学习", "深度学习", "AGI", "Sora", "智能", "算法",
             "机器人", "自动驾驶", "芯片", "英伟达", "NVIDIA", "百度", "文心",
             "通义", "Kimi", "月之暗面", "豆包", "DeepSeek", "算力", "开源",
             "Llama", "Anthropic", "科技", "数字人", "AIGC", "智能体", "Agent",
             "可灵", "即梦", "通义千问", "智谱", " Manus", "SORA", "视频生成"]
    ai_ref = []
    for h in hot:
        t = h.get("title", "")
        if any(k.lower() in t.lower() for k in ai_kw):
            ai_ref.append("[{}]{}".format(h.get("platform", ""), t))
    ref_text = "\n".join(ai_ref[:15]) if ai_ref else "(热榜中暂无AI相关内容)"

    prompt = f"""你是AI资讯编辑,给不懂技术的家长(28-45岁妈妈)做第一手AI动态解读。今天是{date_str}。

生成今天最重要的20条AI动态,每条让人觉得"我能用上/跟我有关"。每条字段:
- title:标题(12-20字)
- category:从【技能突破】【应用落地】【国内排名】【国际动态】【教育结合】【生活实用】【行业政策】选一个
- plainText:大白话解释是什么(2-3句,不用术语)
- howToUse:怎么用/对普通人影响(1-2句)
- why:跟妈妈群体有什么关系(1句)

必须覆盖7类,【教育结合】【生活实用】要占多数(普通人最关心能用上的)。
参考热榜AI内容:{ref_text}

只返回JSON,不要解释和代码块:
{{"aiNews":[{{"title":"","category":"技能突破","plainText":"","howToUse":"","why":""}}]}}"""

    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 1,
        "max_tokens": 10000
    }).encode("utf-8")
    req = urllib.request.Request(KIMI_URL, data=body, headers={
        "Authorization": "Bearer " + KIMI_KEY,
        "Content-Type": "application/json"
    })
    print("  调用Kimi生成AI资讯(深度解读,超时300s)...")
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read().decode("utf-8"))
    content = resp["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())
    result = json.loads(content)
    return result.get("aiNews", [])

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

    # 4. 匹配URL(viralVideos用title精确匹配;recreations用sourceTitle匹配)
    for v in videos:
        if not v.get("url"):
            v["url"] = find_url(v.get("title", ""), hot)
    matched = 0
    for r in recr:
        if not r.get("url"):
            src = r.get("sourceTitle") or r.get("title", "")
            r["url"] = find_url(src, hot)
            if r["url"]:
                matched += 1
    print("  二创URL匹配: {}/{}".format(matched, len(recr)))

    # 5. 生成AI资讯(独立Kimi调用,深度解读)
    print("[4/5] 生成AI资讯(20条,深度解读)...")
    ai_news = generate_ai_news(hot, date_ctx)
    print("  生成 {} 条AI资讯".format(len(ai_news)))

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
