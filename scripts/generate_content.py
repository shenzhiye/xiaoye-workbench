# -*- coding: utf-8 -*-
"""
小野工作台 - 每日内容自动生成
每天 8:00 / 14:00(北京时间) 由 GitHub Actions 触发
流程: 抓取多平台热榜 -> 调 Kimi(kimi-k2.6) 按赛道生成 -> 写入公开 Gist
"""
import os, sys, json, time, re, urllib.request, urllib.error

# ---------- 配置 ----------
KIMI_KEY   = os.environ.get("KIMI_API_KEY", "")
GIST_TOKEN = os.environ.get("GIST_TOKEN", "")
GIST_ID    = os.environ.get("GIST_ID", "")
MODEL      = os.environ.get("KIMI_MODEL", "kimi-k2.6")
KIMI_URL   = "https://api.moonshot.cn/v1/chat/completions"
GIST_URL   = "https://api.github.com/gists/" + GIST_ID

# ---------- 创作者画像(写死在脚本里, 不进网页, 不泄露) ----------
PROFILE = """你是「沈知野」的专属内容策划AI。沈知野的画像如下,所有生成内容必须贴合:

【平台】抖音(主), 未来拓展小红书
【赛道】教育校园
【已发作品主题】一二年级数学应用题解题技巧、英语启蒙、陪孩子写作业片段
【目标人群】28-45岁、负责孩子学习和家庭采买的妈妈
【IP人设】有活力的妈妈、家庭氛围好亲子关系好、对孩子学习很负责、有时间琢磨孩子成长、能给粉丝直接启发;长相甜美
【未来方向】亲子日常、家庭教育口播
【内容风格】灵动、有活人感、真实(不要教条不要爹味)
【关键词】一年级、数学思维、英语启蒙、陪孩子写作业、背单词、计算、识字
【变现模式】带货(生活/日化/美妆/学习类,视频+直播)、接广、心理咨询/陪跑"""

# ---------- 抓热榜 ----------
def fetch_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (WorkBuddy)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def get_hotlist():
    """多源抓取, 任一成功即用, 全失败则用兜底"""
    items = []
    sources = [
        ("微博热搜", "https://api.vvhan.com/api/hotlist/wbHot"),
        ("知乎热榜", "https://api.vvhan.com/api/hotlist/zhihuHot"),
        ("抖音热榜", "https://api.vvhan.com/api/hotlist/douyinHot"),
        ("B站热门", "https://api.vvhan.com/api/hotlist/biliRD"),
    ]
    for name, url in sources:
        try:
            data = fetch_json(url)
            arr = data.get("data", []) if isinstance(data, dict) else data
            for it in arr[:15]:
                t = it.get("title") or it.get("name") or ""
                if t:
                    items.append({"source": name, "title": t})
            if items:
                break
        except Exception:
            continue
    if not items:
        # 兜底: 用教育类常青话题
        items = [
            {"source": "教育常青", "title": "小学生期末复习怎么安排"},
            {"source": "教育常青", "title": "一二年级数学应用题读不懂怎么办"},
            {"source": "教育常青", "title": "英语启蒙从几岁开始最好"},
            {"source": "教育常青", "title": "陪孩子写作业忍不住发火"},
            {"source": "教育常青", "title": "背乘法口诀的快捷方法"},
            {"source": "教育常青", "title": "幼小衔接要做好哪些准备"},
            {"source": "教育常青", "title": "孩子识字慢怎么办"},
            {"source": "教育常青", "title": "计算粗心老出错怎么练"},
        ]
    return items[:20]

# ---------- 调 Kimi 生成 ----------
def call_kimi(hot_text):
    sys_prompt = PROFILE + "\n\n你现在收到一份今日全网热榜。请基于这些热点, 结合沈知野的赛道和风格, 生成两份内容:\n\n1. 【选题灵感】10条, 每条贴合热点的同时转化为沈知野能拍的教育/亲子选题\n2. 【爆款二创】10条, 把热点改编成沈知野能直接拍的二创内容\n\n严格只返回一个JSON对象, 不要任何解释文字、不要markdown代码块标记。JSON结构:\n{\"inspirations\":[{\"title\":\"选题标题\",\"tags\":[\"标签1\",\"标签2\"],\"desc\":\"一句话说明这个选题怎么拍、为什么适合沈知野\"}],\"recreations\":[{\"hot\":\"原热点标题\",\"angle\":\"改编角度(怎么把这个热点改成沈知野能拍的教育内容)\",\"reason\":\"为什么这条值得二创(理由)\",\"script\":\"二创文案(沈知野可以直接念的口播稿,30-60字,有活人感)\"}]}"
    user_msg = "今日热榜:\n" + hot_text
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.85,
        "max_tokens": 6000
    }).encode("utf-8")
    req = urllib.request.Request(KIMI_URL, data=body, headers={
        "Authorization": "Bearer " + KIMI_KEY,
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req, timeout=90) as r:
        resp = json.loads(r.read().decode("utf-8"))
    content = resp["choices"][0]["message"]["content"]
    # 兜底: 去掉可能的 markdown 代码块标记
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())
    return json.loads(content)

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

    # 1. 抓热榜
    print("[1/3] 抓取热榜...")
    hot = get_hotlist()
    print("  获取到 {} 条热点".format(len(hot)))
    hot_text = "\n".join("{}[{}] {}".format(i+1, h["source"], h["title"]) for i, h in enumerate(hot))

    # 2. 调 Kimi 生成
    print("[2/3] 调用 Kimi 生成内容...")
    result = call_kimi(hot_text)
    insp = result.get("inspirations", [])
    recr = result.get("recreations", [])
    print("  生成 {} 条选题, {} 条二创".format(len(insp), len(recr)))

    # 3. 写 Gist
    print("[3/3] 写入 Gist...")
    payload = {
        "date": time.strftime("%Y-%m-%d"),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "hotlist": hot,
        "inspirations": insp,
        "recreations": recr
    }
    write_gist(payload)
    print("=== 完成! Gist 已更新 ===")

if __name__ == "__main__":
    main()
