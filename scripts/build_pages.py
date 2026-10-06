#!/usr/bin/env python3
"""検索エンジン向けのページを作るスクリプト（標準ライブラリのみ）。

index.html の中のデータ（var D = {...};）と data/news.json から、
- タブごとの静的ページ（例：premiere/index.html）… 本文をHTMLとして直接書き込む
- sitemap.xml と robots.txt
を作り、index.html 自体にも説明文（meta）・本文の下書き・ページ一覧のリンクを書き込む。
見た目は index.html の <style> をそのまま使うので、デザインは変わらない。

独自ドメインに移ったら、SITE_URL だけ書き換えてください。
"""
import html as H, json, os, re
from datetime import datetime, timezone, timedelta

SITE_URL = "https://wataru-takano.github.io/douga-topic/"
SITE_NAME = "動画編集トピック"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
NEWS = os.path.join(ROOT, "data", "news.json")
JST = timezone(timedelta(hours=9))

# タブ名 → URL（総合はトップページ）
SLUGS = {
    "総合": "", "ニュース": "news", "動画": "videos", "Premiere": "premiere", "プラグイン": "plugins",
    "セール": "sale", "素材サイト": "materials", "DaVinci Resolve": "davinci-resolve", "CapCut": "capcut",
    "Filmora": "filmora", "Final Cut Pro": "final-cut-pro", "AviUtl": "aviutl", "その他": "others",
}
TITLES = {
    "総合": "動画編集ソフトの最新ニュース・価格・セールまとめ",
    "ニュース": "動画編集の最新ニュース",
    "動画": "動画編集のおすすめ解説動画（YouTube）",
    "Premiere": "Adobe Premiere の最新情報・価格・セール",
    "プラグイン": "動画編集プラグインの最新情報・価格",
    "セール": "動画編集ソフト・プラグインのセール情報",
    "素材サイト": "動画編集に使える無料・有料の素材サイト",
    "DaVinci Resolve": "DaVinci Resolve の最新情報・価格・プラグイン",
    "CapCut": "CapCut の最新情報・料金",
    "Filmora": "Filmora の最新情報・価格・セール",
    "Final Cut Pro": "Final Cut Pro の最新情報・価格・プラグイン",
    "AviUtl": "AviUtl2（AviUtl ExEdit2）の最新版・プラグイン",
    "その他": "その他の動画編集ソフトの最新情報・価格",
}
EXTRA_CSS = (".tabs a{flex:none;border:1px solid var(--line);background:#03060a;color:var(--sub);padding:8px 14px;"
             "border-radius:4px;font-size:.9rem;text-decoration:none}.tabs a:hover{color:var(--text);border-color:var(--acc)}"
             ".tabs a[aria-current=\"page\"]{background:var(--acc);border-color:var(--acc);color:#001015;font-weight:700;"
             "box-shadow:0 0 16px rgba(39,224,255,.55)}"
             ".wrap>h1,.wrap>.upd,.tabs{padding-left:54px}"
             # 右上の「☰」メニュー（JavaScriptなしで開閉できる）
             "details.menu{position:fixed;top:calc(env(safe-area-inset-top,0px) + 14px);left:max(16px,calc((100vw - 860px) / 2 + 16px));z-index:20}"
             "details.menu summary{list-style:none;cursor:pointer;width:40px;height:40px;display:flex;align-items:center;"
             "justify-content:center;font-size:1.35rem;line-height:1;color:var(--acc);background:rgba(3,6,10,.92);"
             "border:1px solid var(--acc);border-radius:6px;box-shadow:0 0 12px rgba(39,224,255,.35);user-select:none}"
             "details.menu summary::-webkit-details-marker{display:none}"
             "details.menu summary:hover,details.menu[open] summary{background:var(--acc);color:#001015}"
             "details.menu[open] summary .i::before{content:\"✕\"}details.menu summary .i::before{content:\"☰\"}"
             "details.menu nav{position:absolute;left:0;top:48px;width:min(240px,calc(100vw - 32px));max-height:calc(100vh - 90px);"
             "overflow:auto;background:var(--card);border:1px solid var(--acc);border-radius:6px;padding:8px 0;"
             "box-shadow:0 0 24px rgba(39,224,255,.3)}"
             "details.menu nav p{margin:4px 14px 6px;color:var(--acc);font-family:var(--mono);font-size:.8rem}"
             "details.menu ul{list-style:none;margin:0;padding:0}"
             "details.menu li a{display:block;padding:10px 14px;color:var(--text);text-decoration:none;font-size:.9rem;"
             "border-top:1px solid var(--line)}details.menu li a:hover{background:rgba(39,224,255,.1);color:var(--acc)}"
             "details.menu li a[aria-current=\"page\"]{color:var(--acc);font-weight:700}"
             ".pr{color:var(--sub);font-size:.8rem;margin:8px 0 0}")


def url_of(name):
    return SITE_URL + (SLUGS[name] + "/" if SLUGS[name] else "")


def rel_of(name, depth):
    """depth=0 はトップ、1 はサブページから見た相対パス。"""
    up = "../" * depth
    return up + (SLUGS[name] + "/" if SLUGS[name] else "")


def fix_go(s, depth):
    """総合タブの <a href="#" data-go="タブ名"> を、実際のページへのリンクに変える。"""
    def rep(m):
        n = H.unescape(m.group(1))
        return f'<a href="{rel_of(n, depth) or "./"}" data-go="{m.group(1)}">' if n in SLUGS else m.group(0)
    return re.sub(r'<a href="#" data-go="([^"]+)">', rep, s)


def card(c, depth):
    h = '<div class="card"><h3>'
    if c.get("r"):
        h += f'<span class="tag reg {"jp" if c["r"] == "国内" else "ov"}">{c["r"]}</span>'
    if c.get("tag"):
        h += f'<span class="tag">{c["tag"]}</span>'
    h += c["t"] + "</h3>"
    for x in c.get("p") or []:
        h += f"<p>{x}</p>"
    if c.get("ol"):
        h += "<ol>" + "".join(f"<li>{x}</li>" for x in c["ol"]) + "</ol>"
    if c.get("pl"):
        last, rows = "", ""
        for x in c["pl"]:
            if len(x) > 3 and x[3] and x[3] != last:
                last = x[3]
                rows += f'<li class="cat">{x[3]}</li>'
            rows += f'<li><a href="{x[2]}" target="_blank" rel="noopener noreferrer">{x[0]} ↗</a><span>{x[1]}</span></li>'
        h += (f'<details class="plg"{" open" if c.get("open") else ""}><summary>一覧表示（全{len(c["pl"])}件）</summary>'
              f'<ul class="pll">{rows}</ul><p class="date">リンクは公式・販売・紹介ページです。価格や対応状況は、リンク先で確認してください。</p></details>')
    if c.get("tbl"):
        t = c["tbl"]
        h += ('<div class="tw"><table><tr>' + "".join(f"<th>{x}</th>" for x in t["head"]) + "</tr>"
              + "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in t.get("rows", [])) + "</table></div>")
    if c.get("ul"):
        h += "<ul>" + "".join(f"<li>{x}</li>" for x in c["ul"]) + "</ul>"
    if c.get("d"):
        h += f'<p class="date">{c["d"]}</p>'
    if c.get("l"):
        h += '<p class="lk">' + " ／ ".join(f'<a href="{x[1]}" target="_blank" rel="noopener noreferrer">{x[0]} ↗</a>' for x in c["l"]) + "</p>"
    return fix_go(h + "</div>", depth)


def panel(tab, depth):
    h = ""
    for title, cards in tab.get("sections", []):
        h += f"<h2>{title}</h2>" + "".join(card(c, depth) for c in cards)
    if tab.get("table"):
        t = tab["table"]
        h += ('<h2>価格の目安</h2><div class="tw"><table><tr>' + "".join(f"<th>{x}</th>" for x in t["head"]) + "</tr>"
              + "".join("<tr>" + "".join(f"<td>{fix_go(x, depth)}</td>" for x in r) + "</tr>" for r in t["rows"])
              + "</table></div>")
    return h


def news_tab(news):
    """index.html の読み込み処理と同じ形で、ニュースをカードにする。"""
    e = lambda t: H.escape(str(t if t is not None else ""), quote=True)
    safe = lambda u: u if re.match(r"^https?://", str(u or "")) else "#"
    cards = []
    for x in sorted(news.get("items", []), key=lambda x: x.get("date", ""), reverse=True):
        d = (x.get("date") or "").split("-")
        links = x.get("links") or [[x.get("label") or "記事を開く", x.get("url")]]
        cards.append({"r": x.get("r"), "tag": e(x.get("tag") or (f"{int(d[1])}月{int(d[2])}日" if len(d) == 3 else "")),
                      "t": e(x.get("title")), "p": [e(x["summary"])] if x.get("summary") else [],
                      "d": e(x["note"]) if x.get("note") else ("出典：" + e(x["source"]) if x.get("source") else ""),
                      "l": [[e(l[0]), safe(l[1])] for l in links]})
    return {"sections": [[f"最新ニュース（自動更新：{e(news.get('updated', ''))}）", cards]]}


def describe(tab, name):
    """検索結果に出る説明文（120字程度）を、タブの中身から作る。"""
    texts = []
    for _, cards in tab.get("sections", []):
        for c in cards:
            texts.append(re.sub(r"<[^>]+>", "", c["t"]))
            if len(texts) >= 6:
                break
        if len(texts) >= 6:
            break
    base = f"{TITLES[name]}。"
    s = base + "、".join(H.unescape(t) for t in texts)
    s = re.sub(r"\s+", " ", s)
    return (s[:118] + "…") if len(s) > 120 else s


def meta_tags(name, desc):
    title = f"{TITLES[name]}｜{SITE_NAME}" if name != "総合" else f"{SITE_NAME}｜{TITLES[name]}"
    u = url_of(name)
    return (f'<meta name="description" content="{H.escape(desc)}">\n'
            f'<link rel="canonical" href="{u}">\n'
            f'<meta property="og:type" content="website">\n<meta property="og:site_name" content="{SITE_NAME}">\n'
            f'<meta property="og:title" content="{H.escape(title)}">\n<meta property="og:description" content="{H.escape(desc)}">\n'
            f'<meta property="og:url" content="{u}">\n<meta property="og:locale" content="ja_JP">\n'
            f'<meta name="twitter:card" content="summary">'), title


def nav_tabs(names, current, depth):
    return ('<nav class="tabs" aria-label="ページ">' + "".join(
        f'<a href="{rel_of(n, depth)}"{" aria-current=\"page\"" if n == current else ""}>{n}</a>' for n in names) + "</nav>")


def page_list(names, depth, current=None):
    """右上の「☰」を押すと開くページ一覧（JavaScriptなしで動く）。"""
    items = "".join(
        f'<li><a href="{rel_of(n, depth) or "./"}"{" aria-current=\"page\"" if n == current else ""}>{n}</a></li>'
        for n in names)
    return ('<details class="menu"><summary aria-label="ページ一覧を開く"><span class="i" aria-hidden="true"></span></summary>'
            f'<nav aria-label="ページ一覧"><p>MENU</p><ul>{items}</ul></nav></details>')


def replace_block(src, tag, content, fallback_anchor, before=True, css=False):
    """<!--TAG-->...<!--/TAG-->（CSSの中では /*TAG*/.../*/TAG*/）の中身を差し替える。
    まだ無ければ目印の前（後）に入れる。"""
    o, c = (f"/*{tag}*/", f"/*/{tag}*/") if css else (f"<!--{tag}-->", f"<!--/{tag}-->")
    block = o + content + c
    pat = re.compile(re.escape(o) + ".*?" + re.escape(c), re.S)
    if pat.search(src):
        return pat.sub(lambda m: block, src, count=1)
    i = src.find(fallback_anchor)
    if i < 0:
        raise SystemExit(f"index.html に {fallback_anchor} が見つかりません")
    j = i if before else i + len(fallback_anchor)
    return src[:j] + block + src[j:]


def main():
    src = open(INDEX, encoding="utf-8").read()
    D = json.loads(re.search(r"^var D = (\{.*\});[ \t]*$", src, re.M).group(1))
    names = json.loads(re.search(r"^var names=(\[.*?\])", src, re.M).group(1))
    names = [n for n in names if n in SLUGS]
    news = json.load(open(NEWS, encoding="utf-8")) if os.path.exists(NEWS) else {"items": []}
    D = dict(D, **{"ニュース": news_tab(news)})

    head = src[:src.index("</head>")]
    style = re.search(r"<style>(.*?)</style>", head, re.S).group(1)
    style = re.sub(r"/\*SEOCSS\*/.*?/\*/SEOCSS\*/", "", style, flags=re.S)
    fonts = "\n".join(re.findall(r'<link [^>]*fonts\.(?:googleapis|gstatic)[^>]*>', head))
    upd = (re.search(r'<p class="upd">([^<]*)</p>', src) or [None, ""])[1]
    note = (re.search(r'<div class="note">.*?</div>', src, re.S) or [""])[0]
    pr = (re.search(r'<p class="pr">.*?</p>', src, re.S) or [""])[0]
    footer = (re.search(r"<footer>.*?</footer>", src, re.S) or [""])[0]

    # ---- タブごとのページ ----
    for name in names:
        if not SLUGS[name]:
            continue
        tab = D[name]
        desc = describe(tab, name)
        metas, title = meta_tags(name, desc)
        page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{H.escape(title)}</title>
{metas}
{fonts}
<style>{style}{EXTRA_CSS}</style>
</head>
<body>
<div class="wrap">
<p class="upd"><a href="../" style="color:inherit;text-decoration:none">🎬 {SITE_NAME}</a> ／ {upd}</p>
<h1>{H.escape(TITLES[name])}</h1>
{note}
{pr}
{nav_tabs(names, name, 1)}
<main id="panel">{panel(tab, 1)}</main>
{page_list(names, 1, name)}
{footer}
</div>
</body>
</html>
"""
        os.makedirs(os.path.join(ROOT, SLUGS[name]), exist_ok=True)
        open(os.path.join(ROOT, SLUGS[name], "index.html"), "w", encoding="utf-8").write(page)

    # ---- トップページ（index.html）に説明文・本文の下書き・ページ一覧を書き込む ----
    metas, title = meta_tags("総合", describe(D["総合"], "総合"))
    src = re.sub(r"<title>[^<]*</title>", f"<title>{H.escape(title)}</title>", src, count=1)
    src = replace_block(src, "SEO", "\n" + metas + "\n", "</head>")
    src = replace_block(src, "SEOCSS", EXTRA_CSS, "</style>", css=True)
    # 本文の下書き（JavaScriptが動けば、いつも通りの表示に置き換わる）
    src = replace_block(src, "PRE", panel(D["総合"], 0), '<div id="panel">', before=False)
    src = replace_block(src, "PAGES", page_list(names, 0, "総合"), "<footer>")
    open(INDEX, "w", encoding="utf-8").write(src)

    # ---- sitemap.xml / robots.txt ----
    today = datetime.now(JST).strftime("%Y-%m-%d")
    urls = "".join(f"<url><loc>{url_of(n)}</loc><lastmod>{today}</lastmod></url>\n" for n in names)
    open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")
    open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n")
    print("作成:", len([n for n in names if SLUGS[n]]), "ページ ＋ トップ ＋ sitemap.xml ＋ robots.txt")


if __name__ == "__main__":
    main()
