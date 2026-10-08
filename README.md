# nj-green-daily · 南京绿灯活动日报

云端自动抓取南京及周边「绿灯活动」（讲座/读书/运动/展览/公益等，社交导向局单独标注需甄别），每天生成一页手机可读的日报。

- **页面**：https://fizchmpz.github.io/nj-green-daily/ （手机浏览器打开 → 添加到主屏幕 ≈ App）
- **推送**：ntfy（订阅主题见 GitHub Secrets 里的 `NTFY_TOPIC`）
- **信源**：豆瓣同城（南京·未来一周）+ 活动行（南京）
- **更新时间**：每天北京时间 08:00 前后（GitHub Actions 定时可能延迟几分钟）

## 文件

- `scraper.py` — 抓取 + 分类 + 生成 index.html + ntfy 推送（纯标准库）
- `.github/workflows/daily.yml` — 每天 UTC 00:00 跑，自动提交更新
- `data/seen.json` — 活动去重档案（识别「新增」）

## 手动运行

```bash
python scraper.py          # 本地生成 index.html，不推送
NTFY_PUSH=1 NTFY_TOPIC=xxx python scraper.py   # 生成并推送
```

## 加信源

在 `scraper.py` 的 `main()` 里仿照现有两项加一个 `scrape_xxx()`，并在 `CATS` 里确认分类关键词覆盖。
