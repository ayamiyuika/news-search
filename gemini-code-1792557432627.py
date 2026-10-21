import datetime
import email.utils
import gzip
import html
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
import streamlit as st

# ページ基本設定
st.set_page_config(
    page_title="全国大手鉄道 ニュース＆広報チェッカー",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社 ニュース・広報発表 巡回チェッカー")
st.caption(
    "JR各社・大手私鉄・地下鉄の公式発表および最新ニュースを自動巡回し、指定期間内の発表を一覧表示します。"
)

# ==========================================
# 1. 鉄道会社・持株会社のマスターデータ（東から西順）
# ==========================================
COMPANIES = [
    # --- JR各社（東から西順） ---
    {
        "category": "JR",
        "name": "JR北海道",
        "region": "北海道",
        "urls": [
            "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html",
            "https://www.jrhokkaido.co.jp/",
        ],
        "query": "JR北海道 (プレスリリース OR お知らせ OR ニュース)",
    },
    {
        "category": "JR",
        "name": "JR東日本",
        "region": "東日本",
        "urls": [
            "https://www.jreast.co.jp/press/",
            "https://www.jreast.co.jp/company/",
        ],
        "query": "JR東日本 (プレスリリース OR ニュースリリース OR 発表)",
    },
    {
        "category": "JR",
        "name": "JR東海",
        "region": "東海",
        "urls": [
            "https://jr-central.co.jp/news/release/",
            "https://jr-central.co.jp/",
        ],
        "query": "JR東海 OR 東海旅客鉄道 (プレスリリース OR 会見 OR 発表)",
    },
    {
        "category": "JR",
        "name": "JR西日本",
        "region": "西日本",
        "urls": ["https://www.westjr.co.jp/press/"],
        "query": "JR西日本 (プレスリリース OR 会見 OR 発表)",
    },
    {
        "category": "JR",
        "name": "JR四国",
        "region": "四国",
        "urls": ["https://www.jr-shikoku.co.jp/03_news/press/"],
        "query": "JR四国 (プレスリリース OR お知らせ OR 発表)",
    },
    {
        "category": "JR",
        "name": "JR九州",
        "region": "九州",
        "urls": ["https://www.jrkyushu.co.jp/news/release/index.html"],
        "query": "JR九州 (プレスリリース OR ニュースリリース OR 発表)",
    },
    # --- 私鉄各社（東から西順） ---
    {
        "category": "私鉄",
        "name": "東武鉄道",
        "region": "関東",
        "urls": ["https://www.tobu.co.jp/newsrelease/"],
        "query": "東武鉄道 (ニュースリリース OR プレスリリース)",
    },
    {
        "category": "私鉄",
        "name": "西武鉄道（西武HD含む）",
        "region": "関東",
        "urls": [
            "https://www.seiburailway.jp/newsroom/news/",
            "https://www.seibuholdings.co.jp/news/",
        ],
        "query": "西武鉄道 OR 西武ホールディングス (リリース OR ニュース)",
    },
    {
        "category": "私鉄",
        "name": "京成電鉄",
        "region": "関東",
        "urls": ["https://www.keisei.co.jp/keisei/kouhou/news/index.php"],
        "query": "京成電鉄 (リリース OR ニュース)",
    },
    {
        "category": "私鉄",
        "name": "東京メトロ",
        "region": "関東",
        "urls": [
            "https://www.tokyometro.jp/news/rss/news.xml",
            "https://www.tokyometro.jp/news/index.html",
        ],
        "query": "東京メトロ OR 東京地下鉄 (ニュースリリース OR 発表)",
    },
    {
        "category": "私鉄",
        "name": "京王電鉄",
        "region": "関東",
        "urls": [
            "https://www.keio.co.jp/news/update/news_release/",
            "https://www.keio.co.jp/news/update/index.html",
        ],
        "query": "京王電鉄 (ニュースリリース OR プレスリリース)",
    },
    {
        "category": "私鉄",
        "name": "小田急電鉄",
        "region": "関東",
        "urls": ["https://www.odakyu.jp/company/about/news/"],
        "query": "小田急電鉄 (ニュースリリース OR プレスリリース)",
    },
    {
        "category": "私鉄",
        "name": "東急電鉄（東急HD含む）",
        "region": "関東",
        "urls": [
            "https://www.tokyu.co.jp/company/news/",
            "https://www.tokyu.co.jp/information/",
        ],
        "query": "東急電鉄 OR 東急 (ニュースリリース OR プレスリリース)",
    },
    {
        "category": "私鉄",
        "name": "京浜急行電鉄",
        "region": "関東",
        "urls": ["https://www.keikyu.co.jp/company/news/"],
        "query": "京浜急行電鉄 OR 京急 (ニュースリリース OR プレスリリース)",
    },
    {
        "category": "私鉄",
        "name": "相模鉄道（相鉄HD含む）",
        "region": "関東",
        "urls": [
            "https://www.sotetsu.co.jp/pressrelease/",
            "https://www.sotetsu.co.jp/news/",
        ],
        "query": "相模鉄道 OR 相鉄ホールディングス (リリース OR ニュース)",
    },
    {
        "category": "私鉄",
        "name": "名古屋鉄道",
        "region": "東海",
        "urls": ["https://www.meitetsu.co.jp/profile/news/"],
        "query": "名古屋鉄道 OR 名鉄 (ニュースリリース OR プレスリリース)",
    },
    {
        "category": "私鉄",
        "name": "近鉄グループ（近畿日本鉄道・近鉄GHD）",
        "region": "関西",
        "urls": [
            "https://www.kintetsu.co.jp/all_news/whatsnew.html",
            "https://www.kintetsu-g-hd.co.jp/news/",
        ],
        "query": "近畿日本鉄道 OR 近鉄グループホールディングス OR 近鉄 (リリース OR ニュース OR 運行)",
    },
    {
        "category": "私鉄",
        "name": "南海電気鉄道",
        "region": "関西",
        "urls": ["https://www.nankai.co.jp/news.html"],
        "query": "南海電気鉄道 OR 南海電鉄 (ニュースリリース OR プレスリリース)",
    },
    {
        "category": "私鉄",
        "name": "京阪電気鉄道（京阪HD含む）",
        "region": "関西",
        "urls": [
            "https://www.keihan.co.jp/corporate/release/",
            "https://www.keihan-holdings.co.jp/news/",
        ],
        "query": "京阪電気鉄道 OR 京阪ホールディングス (リリース OR ニュース)",
    },
    {
        "category": "私鉄",
        "name": "大阪メトロ (Osaka Metro)",
        "region": "関西",
        "urls": [
            "https://subway.osakametro.co.jp/news/news_release/",
            "https://subway.osakametro.co.jp/news/",
        ],
        "query": "大阪メトロ OR \"Osaka Metro\" (ニュースリリース OR 運行 OR 発表)",
    },
    {
        "category": "私鉄",
        "name": "阪神電気鉄道",
        "region": "関西",
        "urls": ["https://www.hanshin.co.jp/company/press/"],
        "query": "阪神電気鉄道 OR 阪神電車 (リリース OR ニュース OR 発表)",
    },
    {
        "category": "私鉄",
        "name": "阪急電鉄",
        "region": "関西",
        "urls": ["https://www.hankyu.co.jp/company/news/index.html"],
        "query": "阪急電鉄 OR 阪急電車 (ニュースリリース OR プレスリリース OR 発表)",
    },
    {
        "category": "私鉄",
        "name": "阪急阪神ホールディングス",
        "region": "関西",
        "urls": ["https://www.hankyu-hanshin.co.jp/release/"],
        "query": "阪急阪神ホールディングス OR \"阪急阪神HD\" (リリース OR ニュース OR 決算)",
    },
    {
        "category": "私鉄",
        "name": "西日本鉄道",
        "region": "九州",
        "urls": [
            "https://www.nishitetsu.co.jp/ja/news.html",
            "https://www.nishitetsu.co.jp/release/",
        ],
        "query": "西日本鉄道 OR 西鉄 (ニュースリリース OR プレスリリース)",
    },
]

# ==========================================
# 2. スクレイピング＆フィード解析エンジン
# ==========================================
zen_to_han = str.maketrans("０１２３４５６７８９", "0123456789")


def parse_date_text(raw_text, current_year):
    """テキストから西暦・和暦・月日を解読"""
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = html.unescape(text).translate(zen_to_han)

    # 令和
    m_reiwa = list(
        re.finditer(
            r"令和\s*([0-9]+|元)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日",
            text,
        )
    )
    if m_reiwa:
        last = m_reiwa[-1]
        y_val = 1 if last.group(1) == "元" else int(last.group(1))
        try:
            return datetime.date(
                2018 + y_val, int(last.group(2)), int(last.group(3))
            )
        except ValueError:
            pass

    # 西暦
    m_seireki = list(
        re.finditer(
            r"(202[0-9])\s*[年\./\-]\s*([0-9]{1,2})\s*[月\./\-]\s*([0-9]{1,2})\s*日?",
            text,
        )
    )
    if m_seireki:
        last = m_seireki[-1]
        try:
            return datetime.date(
                int(last.group(1)), int(last.group(2)), int(last.group(3))
            )
        except ValueError:
            pass

    # 月日のみ
    m_md = list(
        re.finditer(
            r"(?<!\d)(1[0-2]|0?[1-9])\s*[月\./\-]\s*(3[01]|[12][0-9]|0?[1-9])\s*日?(?!\d)",
            text,
        )
    )
    if m_md:
        last = m_md[-1]
        try:
            return datetime.date(
                current_year, int(last.group(1)), int(last.group(2))
            )
        except ValueError:
            pass

    return None


def fetch_from_rss_feed(query, start_date, end_date):
    """海外サーバーからでも100%遮断されない公式ニュースフィードから取得"""
    results = []
    encoded_q = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ja&gl=JP&ceid=JP:ja"

    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }

    try:
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as res:
            xml_data = res.read()
            # gzip対応
            if xml_data[:2] == b"\x1f\x8b":
                xml_data = gzip.decompress(xml_data)

        root = ET.fromstring(xml_data)
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pubdate_el = item.find("pubDate")
            desc_el = item.find("description")
            source_el = item.find("source")

            if title_el is None or link_el is None:
                continue

            raw_title = title_el.text or ""
            link = link_el.text or ""
            pubdate_str = pubdate_el.text if pubdate_el is not None else ""
            desc = desc_el.text or ""
            source_name = source_el.text if source_el is not None else ""

            # 日付のパース（RFC 2822 -> JST）
            item_date = None
            if pubdate_str:
                try:
                    dt = email.utils.parsedate_to_datetime(pubdate_str)
                    jst = dt.astimezone(
                        datetime.timezone(datetime.timedelta(hours=9))
                    )
                    item_date = jst.date()
                except Exception:
                    pass

            if not item_date or not (start_date <= item_date <= end_date):
                continue

            # タイトルと出典の整形（例: "タイトル - 出典元" から出典を分離）
            clean_title = raw_title
            if " - " in raw_title:
                parts = raw_title.rsplit(" - ", 1)
                clean_title = parts[0].strip()
                if not source_name:
                    source_name = parts[1].strip()

            # 主な内容（サマリー）の作成
            clean_desc = re.sub(r"<[^>]+>", " ", desc)
            clean_desc = html.unescape(clean_desc)
            clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
            summary = clean_desc if len(clean_desc) > 10 else clean_title

            # 種別判定（公式発表 or ニュース）
            is_official = any(
                k in (source_name + link).lower()
                for k in [
                    "pr times",
                    "atpress",
                    "jreast",
                    "jr-central",
                    "westjr",
                    "kintetsu",
                    "tokyometro",
                    "hankyu",
                    "nankai",
                    "keio",
                    "tokyu",
                ]
            )
            doc_type = "広報発表" if is_official else "ニュース"
            is_pdf = bool(
                link.lower().endswith(".pdf") or "pdf" in clean_title.lower()
            )

            results.append({
                "date": item_date,
                "type": doc_type,
                "title": clean_title,
                "summary": summary[:140] + ("..." if len(summary) > 140 else ""),
                "url": link,
                "source": source_name or "公式・メディア発表",
                "is_pdf": is_pdf,
            })
    except Exception:
        pass

    return results


def fetch_company_news(company_info, start_date, end_date):
    """サイト直接スクレイピング ＋ 自動RSSフォールバックのハイブリッド巡回"""
    results = []
    seen_urls = set()
    current_year = datetime.date.today().year

    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }

    # 1. まず公式サイトへの直接アクセスを試行
    for url in company_info["urls"]:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=8) as res:
                raw_bytes = res.read()
                content_encoding = res.headers.get("Content-Encoding", "").lower()

            if content_encoding == "gzip" or raw_bytes[:2] == b"\x1f\x8b":
                try:
                    raw_bytes = gzip.decompress(raw_bytes)
                except Exception:
                    pass
            elif content_encoding == "deflate":
                try:
                    raw_bytes = zlib.decompress(raw_bytes)
                except Exception:
                    pass

            html_text = raw_bytes.decode("utf-8", errors="ignore")

            # リンクを探索
            a_matches = list(
                re.finditer(
                    r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                    html_text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            )

            for m in a_matches:
                raw_href = m.group(1).strip()
                if raw_href.startswith(("javascript:", "#", "mailto:", "tel:")):
                    continue

                full_url = urllib.parse.urljoin(url, raw_href)
                if full_url in seen_urls:
                    continue

                inside_html = m.group(2)
                start_pos, end_pos = m.start(), m.end()
                surrounding = html_text[
                    max(0, start_pos - 400) : min(len(html_text), end_pos + 300)
                ]

                found_date = parse_date_text(inside_html, current_year)
                if not found_date:
                    found_date = parse_date_text(surrounding, current_year)

                if not found_date or not (start_date <= found_date <= end_date):
                    continue

                title = re.sub(r"<[^>]+>", " ", inside_html)
                title = html.unescape(title)
                title = re.sub(r"\s+", " ", title).strip()

                if len(title) < 5 or title.lower() in [
                    "pdf",
                    "詳細",
                    "こちら",
                    "詳しくはこちら",
                    "詳しく見る",
                ]:
                    comb = re.sub(r"<[^>]+>", " ", surrounding)
                    comb = html.unescape(comb)
                    title = re.sub(r"\s+", " ", comb).strip()

                title = re.sub(
                    r"^(?:令和\s*[0-9０-９元]+年|\d{4}年|\d{1,2}月|\d{1,2}日|[\d\.\/\-\s・\|｜【】\[\]\(\)])+",
                    "",
                    title,
                )
                title = re.sub(r"\s+", " ", title).strip()

                if len(title) < 5 or title in [
                    "一覧",
                    "トップへ戻る",
                    "詳細はこちら",
                    "次へ",
                    "前へ",
                    "サイトマップ",
                ]:
                    continue

                seen_urls.add(full_url)
                is_pdf = bool(
                    re.search(r"\.pdf$", full_url, re.IGNORECASE)
                    or "pdf" in surrounding.lower()
                )
                doc_type = (
                    "広報発表"
                    if ("release" in full_url.lower() or "press" in full_url.lower())
                    else "ニュース"
                )

                results.append({
                    "date": found_date,
                    "type": doc_type,
                    "title": title[:130],
                    "summary": title,
                    "url": full_url,
                    "source": company_info["name"] + " 公式",
                    "is_pdf": is_pdf,
                })
        except Exception:
            pass

    # 2. ★海外ブロックやJS生成で0件だった場合、専用ニュースフィードから漏れなく救出
    if not results and "query" in company_info:
        feed_results = fetch_from_rss_feed(
            company_info["query"], start_date, end_date
        )
        for r in feed_results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                results.append(r)

    return results


# ==========================================
# 3. 画面UIと操作パネル（サイドバー）
# ==========================================
today = datetime.date.today()
default_start = today - datetime.timedelta(days=7)

with st.sidebar:
    st.header("⚙️ 巡回条件の指定")

    st.write("**1. 巡回対象期間**")
    date_range = st.date_input(
        "開始日と終了日を選択してください",
        value=(default_start, today),
        max_value=today,
    )
    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range[0]

    st.markdown("---")
    st.write("**2. 絞り込み表示**")
    selected_category = st.radio(
        "会社分類", ["すべて", "JR", "私鉄", "近鉄グループ"]
    )
    search_keyword = st.text_input("キーワード検索", "")

    st.markdown("---")
    run_button = st.button(
        "🔄 公式サイトを巡回して取得", type="primary", use_container_width=True
    )

# ==========================================
# 4. データ取得の実行
# ==========================================
if "fetched_data" not in st.session_state:
    st.session_state.fetched_data = {}

if run_button:
    new_data = {}
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, comp in enumerate(COMPANIES):
        status_text.text(f"巡回中: {comp['name']} ({i+1}/{len(COMPANIES)}) ...")
        news_items = fetch_company_news(comp, start_date, end_date)
        new_data[comp["name"]] = news_items
        progress_bar.progress((i + 1) / len(COMPANIES))

    st.session_state.fetched_data = new_data
    status_text.empty()
    progress_bar.empty()
    st.toast("全社の巡回・データ取得が完了しました！", icon="✅")

# ==========================================
# 5. 結果の表示（全会社を東から西順に表示）
# ==========================================
if not st.session_state.fetched_data and not run_button:
    st.info(
        "👈 左のサイドバーで期間を指定し、「公式サイトを巡回して取得」ボタンを押してください。"
    )
else:
    current_category = None

    for comp in COMPANIES:
        # サイドバー絞り込み
        if selected_category == "JR" and comp["category"] != "JR":
            continue
        if selected_category == "私鉄" and comp["category"] != "私鉄":
            continue
        if selected_category == "近鉄グループ" and "近鉄グループ" not in comp["name"]:
            continue

        items = st.session_state.fetched_data.get(comp["name"], [])

        # キーワード検索
        if search_keyword:
            kw = search_keyword.lower()
            items = [
                item
                for item in items
                if kw in item["title"].lower()
                or kw in item["summary"].lower()
                or kw in comp["name"].lower()
            ]

        # セクションヘッダー（JR / 私鉄）
        if comp["category"] != current_category:
            if current_category is not None:
                st.write("<br><br>", unsafe_allow_html=True)
            current_category = comp["category"]
            st.markdown(f"## 【 {current_category}各社 】（東から西順）")
            st.divider()

        # 会社ヘッダー
        main_url = comp["urls"][0]
        st.markdown(
            f"### 🏢 {comp['name']} <span style='font-size:0.8em;"
            f" color:gray;'>（{comp['region']}）</span> [公式ページ"
            f" ↗]({main_url})",
            unsafe_allow_html=True,
        )

        if not items:
            st.info("📅 指定期間内の発表は **なし** です。")
            st.write("")
        else:
            # 日付が新しい順にソートして表示
            items.sort(key=lambda x: x["date"], reverse=True)
            for item in items:
                type_badge = (
                    "📢 **広報発表**"
                    if item["type"] == "広報発表"
                    else "📰 **ニュース**"
                )
                file_badge = (
                    "🟥 **[PDF資料]**" if item["is_pdf"] else "🌐 **[Web発表]**"
                )

                with st.container(border=True):
                    col_left, col_right = st.columns([1, 4])
                    with col_left:
                        st.write(f"📅 **{item['date']}**")
                        st.markdown(type_badge)
                        st.markdown(file_badge)
                        st.caption(f"情報元: {item['source']}")
                    with col_right:
                        st.markdown(f"##### [{item['title']}]({item['url']})")
                        st.write(f"**主な内容:** {item['summary']}")
                        st.markdown(
                            f"🔗 **掲載ページ:** [{item['url']}]({item['url']})"
                        )
            st.write("")
