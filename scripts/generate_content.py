# -*- coding: utf-8 -*-
"""
小野工作台 - 每日内容自动生成
每天 8:00 / 14:00(北京时间) 由 GitHub Actions 触发
流程: 读取用户画像(Gist profile.json) -> 抓取多平台热榜 -> 调 Kimi 生成 -> 写入公开 Gist
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
    """多源抓取, 每条带平台标签; 全失败则用兜底"""
    items = []
    sources = [
        ("抖音",   "https://api.vvhan.com/api/hotlist/douyinHot"),
        ("B站",    "https://api.vvhan.com/api/hotlist/biliRD"),
        ("小红书", "https://api.vvhan.com/api/hotlist/xhsHot"),
        ("微博",   "https://api.vvhan.com/api/hotlist/wbHot"),
        ("知乎",   "https://api.vvhan.com/api/hotlist/zhihuHot"),
    ]
    for platform, url in sources:
        try:
            data = fetch_json(url)
            arr = data.get("data", []) if isinstance(data, dict) else data
            tag = platform if platform in ("抖音", "B站", "小红书") else "全网"
            for it in arr[:12]:
                t = it.get("title") or it.get("name") or ""
                u = it.get("url") or it.get("link") or ""
                if t:
                    items.append({"platform": tag, "title": t, "url": u})
            if len(items) >= 18:
                break
        except Exception:
            continue
    if not items:
        items = [
            {"platform": "抖音",   "title": "小学生期末复习怎么安排",           "url": ""},
            {"platform": "抖音",   "title": "一二年级数学应用题读不懂怎么办",     "url": ""},
            {"platform": "抖音",   "title": "英语启蒙从几岁开始最好",           "url": ""},
            {"platform": "B站",    "title": "陪孩子写作业忍不住发火",           "url": ""},
            {"platform": "小红书", "title": "背乘法口诀的快捷方法",             "url": ""},
            {"platform": "抖音",   "title": "幼小衔接要做好哪些准备",           "url": ""},
            {"platform": "B站",    "title": "孩子识字慢怎么办",                "url": ""},
            {"platform": "小红书", "title": "计算粗心老出错怎么练",             "url": ""},
        ]
    return items[:20]

# ---------- 调 Kimi 生成 ----------
def call_kimi(profile_str, hot_text):
    sys_prompt = profile_str + "\n\n" + """你现在收到一份今日多平台热榜(含抖音/B站/小红书等)。请基于这些热点,结合上述画像,生成三份内容:

1.【爆款视频】从热榜中挑选10条最适合该画像赛道和目标人群的视频,为每条补充关键词、中心内容和爆火原因。platform字段根据热榜来源设为"抖音"、"B站"或"小红书"。
2.【爆款二创】10条,把热点改编成该博主能直接拍的二创内容,附改编角度、理由和口播文案。
3.【英语学习】5句日常生活中妈妈教孩子时常用的英语口语,简单实用,适合亲子场景,不要太难。

严格只返回一个JSON对象,不要任何解释文字、不要markdown代码块标记。JSON结构:
{"viralVideos":[{"title":"视频标题","keywords":["关键词1","关键词2"],"content":"中心内容(2-3句话概括视频讲了什么)","platform":"抖音","viralReason":"爆火原因(为什么这条能火,1-2句话)"}],"recreations":[{"hot":"原热点标题","angle":"改编角度(怎么改成该博主能拍的内容)","reason":"为什么值得二创","script":"二创文案(30-60字口播稿,有活人感)"}],"englishSentences":[{"en":"English sentence","zh":"中文翻译"}]}"""

    user_msg = "今日热榜:\n" + hot_text
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
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode("utf-8"))
    content = resp["choices"][0]["message"]["content"]
    # 兜底: 去掉可能的 markdown 代码块标记
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())
    return json.loads(content)

# ---------- 匹配URL(从原始热榜数据中查找) ----------
def find_url(title, hot_items):
    for h in hot_items:
        if h["title"] == title:
            return h.get("url", "")
    for h in hot_items:
        if h["title"] in title or title in h["title"]:
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

    # 0. 读取画像
    print("[0/4] 读取用户画像...")
    profile = read_profile_from_gist()
    profile_str = build_profile_str(profile)
    print("  画像: " + profile.get("name", "?") + " / " + profile.get("track", "?"))

    # 1. 抓热榜
    print("[1/4] 抓取热榜...")
    hot = get_hotlist()
    print("  获取到 {} 条热点".format(len(hot)))
    hot_text = "\n".join("{}[{}] {}".format(i+1, h["platform"], h["title"]) for i, h in enumerate(hot))

    # 2. 调 Kimi 生成
    print("[2/4] 调用 Kimi 生成内容...")
    result = call_kimi(profile_str, hot_text)
    videos = result.get("viralVideos", [])
    recr = result.get("recreations", [])
    eng = result.get("englishSentences", [])
    print("  生成 {} 条爆款视频, {} 条二创, {} 句英语".format(len(videos), len(recr), len(eng)))

    # 3. 匹配URL
    for v in videos:
        if not v.get("url"):
            v["url"] = find_url(v.get("title", ""), hot)

    # 4. 写 Gist
    print("[3/4] 写入 Gist...")
    payload = {
        "date": time.strftime("%Y-%m-%d"),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "viralVideos": videos,
        "recreations": recr,
        "englishSentences": eng
    }
    write_gist(payload)
    print("[4/4] === 完成! Gist 已更新 ===")

if __name__ == "__main__":
    main()
