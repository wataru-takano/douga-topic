#!/usr/bin/env python3
"""RSSからニュースを集めて data/news.json を更新するスクリプト（標準ライブラリのみ）。

- 手で書いたニュース（auto=false）は消さない。自動で追加したもの（auto=true）だけ古くなったら削除する。
- 環境変数 ANTHROPIC_API_KEY があれば、海外記事の題名を日本語にして、短い要約も付ける（任意）。
  なければ、題名と出典リンクだけを載せる。
"""
import json, os, re, sys, html, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_PATH = os.path.join(ROOT, "data", "news.json")
FEEDS_PATH = os.path.join(ROOT, "scripts", "feeds.json")
JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; DougaTopicBot/1.0)"
KEEP_DAYS = 45      # 自動追加分を残す日数
MAX_AI = 12         # 1回にAIで日本語化する件数の上限
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def log(*a):
    print(*a, flush=True)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def strip_tags(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def parse_date(text, tz_name):
    if not text:
        return None
    text = text.strip()
    dt = None
    try:
        dt = parsedate_to_datetime(text)
    except Exception:
        pass
    if dt is None:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST if tz_name == "JST" else timezone.utc)
    return dt


def parse_feed(data, tz_name="UTC"):
    """RSS 2.0 / Atom / RSS 1.0(RDF) をまとめて読む。"""
    root = ET.fromstring(data)
    out = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        d = {}
        for ch in el:
            k = ch.tag.split("}")[-1]
            if k == "title":
                d["title"] = strip_tags(ch.text)
            elif k == "link":
                d["link"] = ch.attrib.get("href") or (ch.text or "").strip()
            elif k in ("pubDate", "date", "published", "updated") and "date" not in d:
                d["date"] = parse_date(ch.text, tz_name)
            elif k in ("description", "summary", "encoded", "content") and "desc" not in d:
                d["desc"] = strip_tags(ch.text)[:400]
        if d.get("title") and d.get("link"):
            out.append(d)
    return out


def norm_url(u):
    return re.sub(r"[?#].*$", "", u.strip()).rstrip("/")


def build_kw_re(words):
    """英語のキーワードは単語単位で一致させる（"nle" が "Stanley" に当たる、などを防ぐ）。"""
    parts = []
    for k in words:
        if re.fullmatch(r"[A-Za-z0-9 .+\-]+", k):
            parts.append(r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z0-9])")
        else:
            parts.append(re.escape(k))
    return re.compile("|".join(parts), re.I)


def matches(item, kw_re, ex_re):
    """題名にキーワードがあり、除外語がないものだけを採用する（本文の抜粋は誤判定が多いので見ない）。"""
    title = item.get("title", "")
    if ex_re and ex_re.search(title):
        return False
    return bool(kw_re.search(title))


VER_RE = re.compile(r"\d+\.\d+(?:\.\d+)?")


def dup_of_manual(title, manual_titles):
    """手で書いたニュースと同じ話題（同じソフト名＋同じバージョン番号）なら重複とみなす。"""
    vers = set(VER_RE.findall(title))
    if not vers:
        return False
    low = title.lower()
    for mt in manual_titles:
        if vers & set(VER_RE.findall(mt)):
            for name in ("resolve", "premiere", "final cut", "filmora", "capcut", "aviutl", "after effects"):
                if name in low and name in mt.lower():
                    return True
    return False


def ai_japanese(new_items):
    """海外記事の題名と要約を日本語にする（任意）。失敗したら何もしない。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    targets = [x for x in new_items if x["r"] == "海外"][:MAX_AI]
    if not key or not targets:
        return
    payload_items = [{"id": i, "title": x["title"], "source": x["source"], "snippet": x.get("_desc", "")[:300]}
                     for i, x in enumerate(targets)]
    prompt = (
        "次は動画編集ニュースの記事リストです。各記事について、日本語の題名(title_ja)と、"
        "60字以内の日本語の要約(summary_ja)を作ってください。"
        "要約は自分の言葉で書き、原文の文章をそのまま引用しないこと。"
        "情報が少ないときは、題名と題材だけを簡潔に書き、推測で事実を足さないこと。"
        "JSONの配列だけを返してください。形式: [{\"id\":0,\"title_ja\":\"...\",\"summary_ja\":\"...\"}]\n\n"
        + json.dumps(payload_items, ensure_ascii=False)
    )
    body = json.dumps({"model": MODEL, "max_tokens": 3000,
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            res = json.loads(r.read().decode("utf-8"))
        text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        for row in json.loads(text):
            t = targets[int(row["id"])]
            if row.get("title_ja"):
                t["title"] = row["title_ja"]
            if row.get("summary_ja"):
                t["summary"] = row["summary_ja"]
        log("AIで日本語化:", len(targets), "件")
    except Exception as e:
        log("AIの日本語化に失敗（題名のまま掲載します）:", repr(e)[:200])


def main():
    cfg = json.load(open(FEEDS_PATH, encoding="utf-8"))
    kw_re = build_kw_re(cfg["keywords"])
    ex = cfg.get("exclude", [])
    ex_re = build_kw_re(ex) if ex else None
    now = datetime.now(JST)
    since = now - timedelta(days=cfg.get("recent_days", 14))

    news = json.load(open(NEWS_PATH, encoding="utf-8"))
    items = news.get("items", [])
    known = {norm_url(l[1]) for x in items for l in (x.get("links") or [])}
    known |= {norm_url(x["url"]) for x in items if x.get("url")}
    manual_titles = [x.get("title", "") for x in items if not x.get("auto")]

    # 以前に自動で入った記事も、今の条件で見直す（関係ない記事・手書きと重複する記事を外す）
    before = len(items)
    items = [x for x in items if not x.get("auto")
             or (matches(x, kw_re, ex_re) and not dup_of_manual(x.get("title", ""), manual_titles))]
    if len(items) != before:
        log("条件に合わない自動追加分を削除:", before - len(items), "件")

    found, ok_feeds = [], 0
    for f in cfg["feeds"]:
        try:
            entries = parse_feed(fetch(f["url"]), f.get("tz", "UTC"))
            ok_feeds += 1
        except Exception as e:
            log("取得失敗:", f["name"], repr(e)[:120])
            continue
        hit = 0
        for e in entries:
            d = e.get("date")
            if not d or d < since or not matches(e, kw_re, ex_re):
                continue
            if dup_of_manual(e["title"], manual_titles):
                continue
            if norm_url(e["link"]) in known:
                continue
            known.add(norm_url(e["link"]))
            found.append({"date": d.astimezone(JST).strftime("%Y-%m-%d"), "r": f["r"], "title": e["title"],
                          "summary": "", "source": f["name"], "url": e["link"], "auto": True,
                          "_desc": e.get("desc", "")})
            hit += 1
        log("OK:", f["name"], "→ 新規", hit, "件")

    if ok_feeds == 0:
        log("すべてのフィードの取得に失敗しました。")
        sys.exit(1)

    found.sort(key=lambda x: x["date"], reverse=True)
    found = found[: cfg.get("max_new_per_run", 15)]
    ai_japanese(found)
    for x in found:
        x.pop("_desc", None)

    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    kept = [x for x in items if not x.get("auto") or x.get("date", "") >= cutoff]
    items = found + kept
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    news = {"updated": now.strftime("%Y-%m-%d"), "items": items}
    with open(NEWS_PATH, "w", encoding="utf-8") as fp:
        json.dump(news, fp, ensure_ascii=False, indent=1)
        fp.write("\n")
    log("追加:", len(found), "件 / 合計:", len(items), "件")


if __name__ == "__main__":
    main()
