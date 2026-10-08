# -*- coding: utf-8 -*-
"""
南京绿灯活动日报 · 云端生成器
信源：豆瓣同城(南京/week-all) + 活动行(南京)
输出：index.html（部署到 GitHub Pages）+ data/seen.json（去重档案）
推送：ntfy（仅在 NTFY_PUSH=1 且设置了 NTFY_TOPIC 时）
仅用 Python 标准库，无需安装依赖。
"""
import html as html_mod
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ)
TODAY = NOW.date()
SITE_URL = "https://fizchmpz.github.io/nj-green-daily/"
ROOT = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# ---------------- 信源抓取 ----------------

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")

def scrape_douban():
    """豆瓣同城南京·未来一周。列表字段：标题/起止时间/链接。"""
    h = fetch("https://www.douban.com/location/nanjing/events/week-all")
    blocks = re.findall(r'<li class="list-entry".*?</li>', h, re.S)
    out = []
    for b in blocks:
        m_id = re.search(r'/event/(\d+)/', b)
        m_tt = re.search(r'itemprop="summary">([^<]+)<', b)
        if not (m_id and m_tt):
            continue
        m_sd = re.search(r'startDate" datetime="([0-9T:+-]+)"', b)
        m_ed = re.search(r'endDate" datetime="([0-9T:+-]+)"', b)
        m_tx = re.search(r'时间：</span>\s*([^<]*\S)', b)
        out.append({
            "id": "db-" + m_id.group(1),
            "title": html_mod.unescape(m_tt.group(1)).strip(),
            "link": "https://www.douban.com/event/%s/" % m_id.group(1),
            "start": m_sd.group(1)[:10] if m_sd else "",
            "end": m_ed.group(1)[:10] if m_ed else "",
            "time_text": re.sub(r"\s+", " ", m_tx.group(1)).strip() if m_tx else "",
            "source": "豆瓣同城",
        })
    return out

def scrape_hdx():
    """活动行南京（页面直出部分，AJAX 部分抓不到）。"""
    h = fetch("https://www.huodongxing.com/events?city=%E5%8D%97%E4%BA%AC")
    parts = re.split(r'class="search-tab-content-item-mesh"', h)[1:]
    out, seen = [], set()
    for p in parts:
        seg = p[:4000]
        m_id = re.search(r'/event/(\d+)', seg)
        m_tt = re.search(r'item-title[^>]*>\s*(?:<img[^>]*>)?\s*<span[^>]*>([^<]+)</span>', seg)
        if not (m_id and m_tt):
            continue
        eid = m_id.group(1)
        if eid in seen:
            continue
        seen.add(eid)
        m_dm = re.search(r'<p>\s*([^<]*?\d{1,2}/\d{1,2}[^<]*?)\s*</p>', seg)
        m_vm = re.search(r'item-dress-pp">\s*([^<]+)', seg)
        title = html_mod.unescape(m_tt.group(1)).strip()
        if not re.search(r"南京|Nanjing", title + (m_vm.group(1) if m_vm else "")):
            # 城市过滤兜底：标题和场地都不含南京的跳过
            continue
        out.append({
            "id": "hdx-" + eid,
            "title": title,
            "link": "https://www.huodongxing.com/event/" + eid,
            "start": "",
            "end": "",
            "time_text": html_mod.unescape(m_dm.group(1)).strip() if m_dm else "详见活动页",
            "venue": html_mod.unescape(m_vm.group(1)).strip() if m_vm else "",
            "source": "活动行",
        })
    return out

# ---------------- 分类与过滤 ----------------

YELLOW = re.compile(r"相亲|脱单|婚恋|交友|联谊|恋爱|红娘|处对象|cpdd|搭子", re.I)

CATS = [
    ("讲座 · 峰会 · 行业", re.compile(r"讲座|论坛|峰会|大会|会议|研讨会|分享会|路演|创投|沙龙|TED|演讲", re.I)),
    ("读书 · 学习", re.compile(r"读书|夜校|课堂|公开课|培训|语言角|工作坊|研学", re.I)),
    ("运动 · 户外", re.compile(r"徒步|爬山|登山|跑团|马拉松|夜跑|骑行|飞盘|羽毛球|篮球|足球|网球|乒乓球|攀岩|滑雪|露营|桨板|皮划艇|citywalk|City walk|Citywalk|夜走|健走", re.I)),
    ("展览 · 文艺 · 演出", re.compile(r"展览|展会|艺术|美术|音乐|livehouse|话剧|戏剧|喜剧|脱口秀|相声|曲艺|戏曲|京昆|演出|市集|博物馆|美术馆|观影|摄影|非遗|手作", re.I)),
    ("公益 · 志愿", re.compile(r"志愿者|公益|支教|救助|义务|献血", re.I)),
]

def classify(ev):
    text = ev["title"]
    if YELLOW.search(text):
        return "⚠ 需甄别（社交导向局）"
    for name, pat in CATS:
        if pat.search(text):
            return name
    if text.rstrip().endswith("展"):  # 「年货礼盒展」等展会尾巴
        return "展览 · 文艺 · 演出"
    return "其他 · 待归类"

# ---------------- 去重档案 ----------------

def load_seen():
    path = os.path.join(ROOT, "data", "seen.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_seen(seen):
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    cut = (TODAY - timedelta(days=60)).isoformat()
    for k in [k for k, v in seen.items() if v.get("last", "") < cut]:
        del seen[k]
    with open(os.path.join(ROOT, "data", "seen.json"), "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=1)

# ---------------- 页面生成 ----------------

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{background:#f4f1ea;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#2b2b28;line-height:1.6}
.wrap{max-width:720px;margin:0 auto;padding:28px 16px 60px}
.mast{text-align:center;border-bottom:3px double #1f4d3a;padding-bottom:18px;margin-bottom:6px}
.mast h1{font-family:Georgia,"STSong","SimSun",serif;font-size:34px;letter-spacing:6px;color:#1f4d3a}
.mast .sub{margin-top:8px;color:#8a8577;font-size:13px;letter-spacing:2px}
.status{font-size:12px;color:#8a8577;text-align:center;padding:10px 0 26px;border-bottom:1px solid #d9d4c7;margin-bottom:26px}
.status .ok{color:#1f7a4d}.status .bad{color:#b3541e}
h2.sec{font-size:18px;color:#1f4d3a;border-left:4px solid #1f4d3a;padding-left:10px;margin:34px 0 14px;display:flex;justify-content:space-between;align-items:baseline}
h2.sec small{font-weight:normal;color:#8a8577;font-size:12px}
.card{background:#fff;border:1px solid #d9d4c7;border-radius:8px;padding:16px 18px;margin-bottom:14px}
.card .tt{font-size:16.5px;font-weight:600;line-height:1.5}
.card .tt a{color:#2b2b28;text-decoration:none}
.card .tt a:active{color:#1f4d3a}
.card .meta{margin-top:8px;font-size:13px;color:#6b6659}
.card .meta b{color:#1f4d3a;font-weight:600}
.badge{display:inline-block;font-size:11px;padding:1px 8px;border:1px solid #1f4d3a;border-radius:10px;color:#1f4d3a;margin-left:8px;vertical-align:1px}
.badge.new{background:#1f4d3a;color:#fff}
.card.yellow{border-color:#c9a24b;background:#fffdf5}
.card.yellow .tt a{color:#7a5a12}
.warn{background:#fdf6ec;border:1px solid #e3c98f;border-radius:8px;padding:14px 16px;font-size:13px;color:#7a5a12;margin:14px 0}
.foot{margin-top:44px;border-top:1px solid #d9d4c7;padding-top:18px;font-size:12.5px;color:#8a8577;line-height:1.9}
.foot b{color:#5c5748}
"""

def build_html(events, src_status):
    seen = load_seen()
    today_iso = TODAY.isoformat()
    for ev in events:
        rec = seen.get(ev["id"], {})
        ev["is_new"] = rec.get("first") != today_iso  # 今天之前没见过 = 新增
        if "first" not in rec:
            rec["first"] = today_iso
        rec["last"] = today_iso
        seen[ev["id"]] = rec
    save_seen(seen)

    # 过滤已结束
    events = [e for e in events if not (e.get("end") and e["end"] < today_iso)]
    # 去重（同 id 保一条）
    uniq, ids = [], set()
    for e in events:
        if e["id"] not in ids:
            ids.add(e["id"])
            uniq.append(e)
    events = uniq

    groups = {}
    for e in events:
        groups.setdefault(classify(e), []).append(e)
    order = [c for c, _ in CATS] + ["其他 · 待归类", "⚠ 需甄别（社交导向局）"]
    order = [o for o in order if o in groups]
    for g in groups:
        groups[g].sort(key=lambda e: e.get("start") or "9999")

    n_new = sum(1 for e in events if e["is_new"])
    cards = []
    for g in order:
        evs = groups[g]
        yellow = g.startswith("⚠")
        cards.append('<h2 class="sec">%s<small>%d 条</small></h2>' % (html_mod.escape(g), len(evs)))
        if yellow:
            cards.append('<div class="warn">⚠ 以下为「社交导向」活动（相亲/交友/联谊类）。此前风评审核结论：'
                         '此类局鱼龙混杂、曾有诈骗案例，去之前先核实主办方资质，勿现场大额付费。</div>')
        for e in evs:
            badge = '<span class="badge new">新增</span>' if e["is_new"] else ""
            venue = ('<div class="meta">地点：<b>%s</b></div>' % html_mod.escape(e["venue"])) if e.get("venue") else ""
            cards.append(
                '<div class="card%s">'
                '<div class="tt"><a href="%s" target="_blank">%s</a>%s%s</div>'
                '<div class="meta">时间：<b>%s</b>｜来源：%s</div>%s'
                '</div>' % (
                    " yellow" if yellow else "",
                    html_mod.escape(e["link"], quote=True),
                    html_mod.escape(e["title"]),
                    '<span class="badge">%s</span>' % html_mod.escape(e["source"]),
                    badge,
                    html_mod.escape(e.get("time_text") or "详见活动页"),
                    e["source"], venue))
        _ = e  # noqa

    src_bits = []
    for name, ok, n in src_status:
        cls = "ok" if ok else "bad"
        src_bits.append('<span class="%s">%s %s（%s条）</span>' %
                        (cls, "✓" if ok else "✗", name, n))

    week = "周" + "一二三四五六日"[NOW.weekday()]
    page = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>南京绿灯活动日报 · %s</title>
<style>%s</style></head><body><div class="wrap">
<div class="mast"><h1>南京绿灯活动日报</h1>
<div class="sub">%s · %s · 第 %s 期</div></div>
<div class="status">信源状态：%s<br>今日收录 <b>%d</b> 条，其中新增 <b>%d</b> 条 ｜ 固定网址，每天 8:00 前后更新</div>
%s
<div class="foot">
<b>阅读须知</b><br>
1 · 本页由云服务器每天自动抓取公开活动页生成（豆瓣同城南京 + 活动行南京），名额与价格以你点开的报名页实时显示为准。<br>
2 · 活动门槛、人群画像等深度信息云端脚本无法自动核验，报名前请自行查看主办方与往期评价。<br>
3 · 行业峰会、博物馆预约、官方讲座等「深水区」活动不在自动抓取范围，待电脑开机时由 AI 深度版补充。<br>
4 · 「需甄别」分区是社交导向活动（相亲/交友/联谊），参照此前风评审核结论保留并单独提示。<br>
生成时间：%s（北京时间）
</div></div></body></html>""" % (
        today_iso, CSS, today_iso, week, TODAY.strftime("%Y%m%d"),
        " ".join(src_bits), len(events), n_new,
        "\n".join(cards),
        NOW.strftime("%Y-%m-%d %H:%M"))
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    return events, groups, n_new

# ---------------- ntfy 推送 ----------------

def push_ntfy(total, n_new, groups, src_status):
    topic = os.environ.get("NTFY_TOPIC", "")
    if os.environ.get("NTFY_PUSH") != "1" or not topic:
        print("[ntfy] skip (NTFY_PUSH!=1 or no topic)")
        return
    parts = []
    for g, evs in groups.items():
        if not g.startswith("⚠"):
            parts.append("%s%d" % (g.split(" ")[0], len(evs)))
    body = "今日收录 %d 条（新增 %d）：%s。点开查看详情与报名链接。" % (
        total, n_new, " · ".join(parts) if parts else "详情见页面")
    failed = [n for n, ok, _ in src_status if not ok]
    if failed:
        body += "（信源异常：%s）" % ",".join(failed)
    url = "https://ntfy.sh/" + topic
    data = body.encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Title": ("南京绿灯日报 %s" % TODAY.strftime("%m-%d")).encode("utf-8"),
        "Click": SITE_URL,
        "Tags": "newspaper",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("[ntfy] pushed:", r.status)
    except Exception as exc:
        print("[ntfy] push failed:", exc)

# ---------------- 主流程 ----------------

def main():
    src_status = []
    events = []
    for name, fn in [("豆瓣同城", scrape_douban), ("活动行", scrape_hdx)]:
        try:
            got = fn()
            src_status.append((name, True, len(got)))
            events += got
            print("[%s] %d 条" % (name, len(got)))
        except Exception as exc:
            src_status.append((name, False, 0))
            print("[%s] FAILED: %r" % (name, exc))
    if not events:
        raise SystemExit("所有信源均失败，退出以触发告警")
    events, groups, n_new = build_html(events, src_status)
    print("total %d, new %d" % (len(events), n_new))
    push_ntfy(len(events), n_new, groups, src_status)

if __name__ == "__main__":
    main()
