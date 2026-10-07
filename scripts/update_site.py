#!/usr/bin/env python3
"""index.html の中のデータ（var D = {...};）を、Claude（Web検索つき）で最新にするスクリプト。

- タブごとに Claude API を呼び、Web検索で確認できた情報だけでそのタブのデータを書き直してもらう。
- 返ってきたデータは機械的にチェックし、問題があるタブは元のまま残す（壊れたデータは載せない）。
- 「ニュース」タブは data/news.json（update_news.py）が担当するので、ここでは触らない。
- 標準ライブラリのみ。環境変数 ANTHROPIC_API_KEY が必要。

使い方: python scripts/update_site.py            # 設定ファイルの全タブ
        python scripts/update_site.py セール 総合  # 指定したタブだけ
"""
import json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
CFG_PATH = os.path.join(ROOT, "scripts", "site_update.json")
REPORT = os.path.join(ROOT, "update_report.md")   # PR の説明文に使う（コミットしない）
JST = timezone(timedelta(hours=9))
API = "https://api.anthropic.com/v1/messages"
D_RE = re.compile(r"^var D = (\{.*\});[ \t]*$", re.M)
UPD_RE = re.compile(r'(<p class="upd">最終更新：)[^<]*(</p>)')
ALLOWED_KEYS = {"t", "tag", "r", "p", "d", "l", "ul", "ol", "pl", "tbl", "open"}


def log(*a):
    print(*a, flush=True)


# ---------- index.html の読み書き ----------

def load_index():
    html = open(INDEX, encoding="utf-8").read()
    m = D_RE.search(html)
    if not m:
        sys.exit("index.html の中に「var D = {...};」の行が見つかりません。")
    return html, m, json.loads(m.group(1))


def save_index(html, m, data, today):
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html[:m.start(1)] + js + html[m.end(1):]
    html = UPD_RE.sub(lambda x: x.group(1) + f"{today.year}年{today.month}月{today.day}日" + x.group(2), html, count=1)
    open(INDEX, "w", encoding="utf-8").write(html)


# ---------- Claude API ----------

def call_claude(key, model, system, user, max_uses, max_tokens):
    msgs = [{"role": "user", "content": user}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}]
    for _ in range(6):  # pause_turn のときは続きを依頼する
        body = json.dumps({"model": model, "max_tokens": max_tokens, "system": system,
                           "messages": msgs, "tools": tools}).encode("utf-8")
        req = urllib.request.Request(API, data=body, method="POST", headers={
            "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    res = json.loads(r.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                    wait = 30 * (attempt + 1)
                    log(f"  API {e.code}。{wait}秒後に再試行")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"API {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
        if res.get("stop_reason") == "pause_turn":
            msgs.append({"role": "assistant", "content": res["content"]})
            continue
        u = res.get("usage", {})
        searches = (u.get("server_tool_use") or {}).get("web_search_requests", 0)
        log(f"  使用量: 入力 {u.get('input_tokens')} / 出力 {u.get('output_tokens')} トークン、検索 {searches} 回")
        if res.get("stop_reason") == "max_tokens":
            raise RuntimeError("出力が上限で途切れました（max_tokens を増やしてください）")
        return "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
    raise RuntimeError("pause_turn が続いたため中断しました")


def extract_json(text):
    m = re.search(r"<result>\s*(\{.*\})\s*</result>", text, re.S)
    if not m:
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if not m:
        raise ValueError("結果のJSONが見つかりません")
    return json.loads(m.group(1))


# ---------- チェック ----------

BAD = re.compile(r"<\s*(script|iframe|object|embed|style|form|input)|\son\w+\s*=|javascript:", re.I)
URL_OK = re.compile(r"^https?://[^\s\"'<>]+$")


def walk_strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, list):
        for y in x:
            yield from walk_strings(y)
    elif isinstance(x, dict):
        for y in x.values():
            yield from walk_strings(y)


URL_ANY = re.compile(r"https?://[^\s\"'<>]+")
AVOID = []   # main() で site_update.json の source_policy.avoid_domains を読み込む


def host_of(u):
    return re.sub(r"^www\.", "", re.sub(r"^https?://([^/:?#]+).*$", r"\1", u).lower())


def is_avoided(u):
    h = host_of(u)
    return any(h == d or h.endswith("." + d) for d in AVOID)


def cards_of(tab):
    return [c for s in tab.get("sections", []) for c in s[1]]


def validate(name, old, new, removed):
    """問題があればエラー文のリストを返す。"""
    errs = []
    if not isinstance(new, dict) or not isinstance(new.get("sections"), list):
        return ["sections がありません"]
    for s in new["sections"]:
        if not (isinstance(s, list) and len(s) == 2 and isinstance(s[0], str) and isinstance(s[1], list)):
            return ["sections の形が違います"]
        for c in s[1]:
            if not isinstance(c, dict) or not isinstance(c.get("t"), str):
                return ["カードの形が違います"]
            extra = set(c) - ALLOWED_KEYS
            if extra:
                errs.append(f"使えない項目: {sorted(extra)}")
            for l in c.get("l", []) or []:
                if not (isinstance(l, list) and len(l) == 2 and URL_OK.match(str(l[1]))):
                    errs.append(f"リンクの形が違います: {l}")
            tb = c.get("tbl")
            if tb is not None and not (isinstance(tb, dict) and isinstance(tb.get("head"), list)
                                       and all(isinstance(r, list) and len(r) == len(tb["head"]) for r in tb.get("rows", []))):
                errs.append(f"表（tbl）の形が違います: {c['t']}")
            for p in c.get("pl", []) or []:
                if not (isinstance(p, list) and len(p) >= 3 and URL_OK.match(str(p[2]))):
                    errs.append(f"一覧のリンクの形が違います: {p[:1]}")
    for s in walk_strings(new):
        if BAD.search(s):
            errs.append("使えないHTML（script など）が含まれています")
            break
    # セクション見出しは変えない（タブ構成を守る）
    if [s[0] for s in old.get("sections", [])] != [s[0] for s in new["sections"]]:
        errs.append("セクションの見出しや順番が変わっています")
    # 根拠のない削除はしない：消えたカードは removed に理由と出典が必要
    new_titles = {c["t"] for c in cards_of(new)}
    ok_removed = {r.get("t") for r in removed if isinstance(r, dict) and URL_OK.match(str(r.get("source", "")))}
    for c in cards_of(old):
        if c["t"] not in new_titles and c["t"] not in ok_removed:
            errs.append(f"出典なしで消えたカード: {c['t']}")
    # プラグイン等の一覧（pl）は減らさない
    old_pl = {p[0] for c in cards_of(old) for p in (c.get("pl") or [])}
    new_pl = {p[0] for c in cards_of(new) for p in (c.get("pl") or [])}
    lost = old_pl - new_pl
    if lost:
        errs.append(f"一覧から消えた項目: {sorted(lost)[:5]}")
    # 価格表（総合タブ）の行は減らさない
    if "table" in old:
        t = new.get("table")
        if not isinstance(t, dict) or t.get("head") != old["table"]["head"]:
            errs.append("価格表の見出しが変わっています")
        elif len(t.get("rows", [])) < len(old["table"]["rows"]):
            errs.append("価格表の行が減っています")
        elif any(not isinstance(r, list) or len(r) != len(t["head"]) for r in t.get("rows", [])):
            errs.append("価格表の列の数が合いません")
    # 出典は公式サイトなどから：新しく加わったリンクに、個人ブログ・クーポン・Q&Aサイトなどが無いか
    old_urls = set(URL_ANY.findall(json.dumps(old, ensure_ascii=False)))
    new_urls = set(URL_ANY.findall(json.dumps(new, ensure_ascii=False)))
    new_urls |= {str(r.get("source", "")) for r in removed if isinstance(r, dict)}
    bad = sorted(u for u in new_urls - old_urls if is_avoided(u))
    if bad:
        errs.append(f"公式以外（個人サイト等）の出典が追加されています: {bad[:3]}")
    if len(json.dumps(new, ensure_ascii=False)) < 0.7 * len(json.dumps(old, ensure_ascii=False)):
        errs.append("データ量が3割以上減っています")
    return errs


# ---------- メイン ----------

SYSTEM = """あなたは日本語の「動画編集ニュース＆セールまとめ」サイトの編集者です。
Web検索で最新情報を調べ、指定されたタブのデータ（JSON）を更新します。

守ること：
- 検索で確認できた情報だけを書く。確認できないものは「要確認」と書く。推測で事実を足さない。
- 出典は、メーカー・開発元の公式サイト（製品ページ、価格ページ、リリースノート、公式ブログ、公式ニュースルーム）を最優先にする。
  公式で確認できないときだけ、大手の報道・専門メディアを使う。
  個人ブログ、まとめ・アフィリエイト記事、クーポンサイト、Q&Aサイト、SNS、wiki は出典にしない。
  それらでしか確認できない情報は書かない（既存の内容を変えるだけの根拠にもしない）。
- 新しく書いた情報・変えた情報には、出典のリンクをカードの "l"（[[表示名, URL], ...]）に必ず付ける。URLは検索結果で実際に見たものだけ。
- 古い情報は、新しい情報で確認できた場合だけ差し替える。根拠なくカードを消さない。
  カードを消すときは、"removed" に {"t": カードのタイトル, "reason": 理由, "source": 根拠のURL} を書く。
- 日付が入る確認済み表示（例「10月5日確認」）は、今回確認できたものだけ今日の日付に変える。
- 価格は税込の円で。海外価格しか確認できないときはドル表記のまま「円価格は要確認」と書く。
- 海外記事は日本語で要約する。原文の文章をそのまま引用しない。
- セクションの見出し・順番は変えない。カードの形（t, tag, r, p, d, l, ul, ol, pl, tbl, open の項目）を守る。tbl は {"head": [...], "rows": [[...], ...]} で、列の数を head と揃える。
  総合タブの "table" は列（head）を変えない。行は追加・更新してよいが減らさない。
- "pl"（プラグインなどの一覧）は、重要な新しいものがあるときだけ末尾付近に追記する。既存の項目は消さない。
- 文字列の中で使ってよいHTMLは <b> と、総合タブで既に使われている <a href="#" data-go="タブ名"> と <a href="https://..." target="_blank" rel="noopener noreferrer"> だけ。
- 文章は短く、わかりやすい日本語で。

最後に、次の形で結果だけを <result> と </result> の間に出力する（前置きの文章は短くてよい）：
<result>
{"tab": {更新後のタブのJSON（"sections" ほか元と同じ形）},
 "changes": ["変更点を1行ずつ（出典ドメインも添える）"],
 "removed": []}
</result>
変更が不要なら "tab" は元のまま、"changes" は空にする。"""


def main():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY が設定されていません（Settings → Secrets and variables → Actions）。")
    cfg = json.load(open(CFG_PATH, encoding="utf-8"))
    AVOID[:] = [d.lower() for d in cfg.get("source_policy", {}).get("avoid_domains", [])]
    official = cfg.get("source_policy", {}).get("official_domains", [])
    model = os.environ.get("ANTHROPIC_MODEL") or cfg.get("model", "claude-sonnet-5-5")
    tabs = sys.argv[1:] or cfg["tabs"]
    today = datetime.now(JST)
    html, m, D = load_index()

    report, updated, failed = [], [], []
    for name in tabs:
        if name not in D or name == "ニュース":
            log(f"スキップ: {name}")
            continue
        log(f"■ {name} を更新中…")
        old = D[name]
        focus = cfg.get("focus", {}).get(name, "")
        user = (f"今日は {today:%Y年%m月%d日}（日本時間）です。\n"
                f"タブ「{name}」を最新の情報に更新してください。\n"
                + (f"重点的に調べること：{focus}\n" if focus else "")
                + (f"優先する公式サイトの例：{', '.join(official)}\n" if official else "")
                + "\n現在のデータ：\n" + json.dumps(old, ensure_ascii=False))
        try:
            text = call_claude(key, model, SYSTEM, user, cfg.get("max_searches_per_tab", 8),
                               cfg.get("max_tokens", 32000))
            res = extract_json(text)
            new, changes, removed = res.get("tab"), res.get("changes") or [], res.get("removed") or []
            errs = validate(name, old, new, removed)
        except Exception as e:
            errs, changes, removed = [f"{type(e).__name__}: {str(e)[:200]}"], [], []
        if errs:
            log(f"  ✗ 採用しません（元のまま）: {errs[:3]}")
            failed.append((name, errs))
            continue
        if new == old:
            log("  変更なし")
            continue
        D[name] = new
        updated.append(name)
        report.append(f"### {name}\n" + "\n".join(f"- {c}" for c in changes)
                      + ("".join(f"\n- 削除：{r.get('t')}（{r.get('reason')}／{r.get('source')}）" for r in removed)))
        log(f"  ✓ 更新（{len(changes)} 件の変更）")

    if updated:
        save_index(html, m, D, today)
    lines = [f"## サイト自動更新 {today:%Y-%m-%d}", "",
             "AIがWeb検索で調べた更新案です。**価格・セール・日付を中心に、出典リンクを開いて確認してから Merge してください。**", ""]
    lines += report or ["（更新されたタブはありません）"]
    if failed:
        lines += ["", "### 更新できなかったタブ（元のまま）"] + [f"- {n}：{'; '.join(e[:2])}" for n, e in failed]
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    log(f"完了：更新 {len(updated)} タブ / 失敗 {len(failed)} タブ")
    if failed and not updated:
        sys.exit(1)


if __name__ == "__main__":
    main()
