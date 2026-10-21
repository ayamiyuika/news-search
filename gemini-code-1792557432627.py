import datetime
import html
import re
import ssl
import urllib.parse
import urllib.request
import streamlit as st

# ページ設定
st.set_page_config(
    page_title="全国大手鉄道 ニュース＆広報チェッカー",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社 ニュース・広報発表 巡回チェッカー")
st.caption(
    "JR各社・大手私鉄・東京メトロ・大阪メトロの公式ページ（持株会社含む）を巡回し、指定期間内の発表を一覧表示します。"
)

# ==========================================
# 1. 鉄道会社・持株会社のマスターデータ（東から西順）
# ==========================================
COMPANIES = [
    # --- JR各社 ---
    {
        "category": "JR",
        "name": "JR北海道",
        "region": "北海道",
        "urls": ["https://www.jrhokkaido.co.jp/CM/info/press/presstop.html"],
    },
    {
        "category": "JR",
        "name": "JR東日本",
        "region": "東日本",
        "urls": ["https://www.jreast.co.jp/press/"],
    },
    {
        "category": "JR",
        "name": "JR東海",
        "region": "東海",
        "urls": [
            "https://jr-central.co.jp/news/release/",
            "https://jr-central.co.jp/",
        ],
    },
    {
        "category": "JR",
        "name": "JR西日本",
        "region": "西日本",
        "urls": ["https://www.westjr.co.jp/press/"],
    },
    {
        "category": "JR",
        "name": "JR四国",
        "region": "四国",
        "urls": ["https://www.jr-shikoku.co.jp/03_news/press/"],
    },
    {
        "category": "JR",
        "name": "JR九州",
        "region": "九州",
        "urls": ["https://www.jrkyushu.co.jp/news/release/index.html"],
    },
    # --- 私鉄・メトロ各社（東から西順） ---
    {
        "category": "私鉄（メトロ含む）",
        "name": "東武鉄道",
        "region": "関東",
        "urls": ["https://www.tobu.co.jp/newsrelease/"],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "西武鉄道（西武HD含む）",
        "region": "関東",
        "urls": [
            "https://www.seiburailway.jp/newsroom/news/",
            "https://www.seibuholdings.co.jp/news/",
        ],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京成電鉄",
        "region": "関東",
        "urls": ["https://www.keisei.co.jp/keisei/kouhou/news/index.php"],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "東京メトロ",
        "region": "関東",
        "urls": ["https://www.tokyometro.jp/news/index.html"],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京王電鉄",
        "region": "関東",
        "urls": ["https://www.keio.co.jp/news/update/index.html"],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "小田急電鉄",
        "region": "関東",
        "urls": ["https://www.odakyu.jp/company/about/news/"],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "東急電鉄（東急HD相当含む）",
        "region": "関東",
        "urls": [
            "https://www.tokyu.co.jp/information/",
            "https://www.tokyu.co.jp/company/news/",
        ],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京浜急行電鉄",
        "region": "関東",
        "urls": ["https://www.keikyu.co.jp/company/news/"],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "相模鉄道（相鉄HD含む）",
        "region": "関東",
        "urls": [
            "https://www.sotetsu.co.jp/pressrelease/",
            "https://www.sotetsu.co.jp/news/",
        ],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "名古屋鉄道",
        "region": "東海",
        "urls": ["https://www.meitetsu.co.jp/profile/news/"],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "近畿日本鉄道（近鉄グループHD含む）",
        "region": "関西",
        "urls": [
            "https://www.kintetsu.co.jp/all_news/whatsnew.html",
            "https://www.kintetsu-g-hd.co.jp/news/",
        ],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "京阪電気鉄道（京阪HD含む）",
        "region": "関西",
        "urls": [
            "https://www.keihan.co.jp/corporate/release/",
            "https://www.keihan-holdings.co.jp/news/",
        ],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "南海電気鉄道",
        "region": "関西",
        "urls": ["https://www.nankai.co.jp/news.html"],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "大阪メトロ (Osaka Metro)",
        "region": "関西",
        "urls": ["https://subway.osakametro.co.jp/news/"],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "阪神電気鉄道（阪急阪神HD含む）",
        "region": "関西",
        "urls": [
            "https://www.hanshin.co.jp/company/press/",
            "https://www.hankyu-hanshin.co.jp/release/",
        ],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "阪急電鉄（阪急阪神HD含む）",
        "region": "関西",
        "urls": [
            "https://www.hankyu.co.jp/company/news/index.html",
            "https://www.hankyu-hanshin.co.jp/release/",
        ],
    },
    {
        "category": "私鉄（メトロ含む）",
        "name": "西日本鉄道",
        "region": "九州",
        "urls": ["https://www.nishitetsu.co.jp/ja/news.html"],
    },
]

# ==========================================
# 2. 高精度な日付・リンク解析ロジック（標準機能のみ）
# ==========================================
zen_to_han = str.maketrans("０１２３４５６７８９", "0123456789")


def parse_date_text(raw_text, current_year):
    """テキストから西暦・和暦（令和）を正確に読み取る"""
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = html.unescape(text)

    # 1. 令和表記（令和8年、令和元年など）
    m_reiwa = list(
        re.finditer(
            r"令和\s*([0-9０-９]+|元)\s*年\s*([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日",
            text,
        )
    )
    if m_reiwa:
        last = m_reiwa[-1]
        y_val = 1 if last.group(1) == "元" else int(last.group(1).translate(zen_to_han))
        y = 2018 + y_val
        m = int(last.group(2).translate(zen_to_han))
        d = int(last.group(3).translate(zen_to_han))
        try:
            return datetime.date(y, m, d)
        except ValueError:
            pass

    # 2. 西暦表記（202x年xx月xx日 / 202x.xx.xx / 202x/xx/xx / 202x-xx-xx）
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

    # 3. 月日のみ（xx月xx日 / xx.xx / xx/xx）
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


def fetch_company_news(urls, start_date, end_date):
    results = []
    seen_urls = set()
    current_year = datetime.date.today().year

    # SSL証明書エラーを回避するための設定
    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }

    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as res:
                raw_bytes = res.read()

            # 文字コードの自動判別（UTF-8, Shift_JIS, CP932, EUC-JP）
            html_text = None
            charset_m = re.search(
                rb'charset=["\']?([a-zA-Z0-9_\-]+)', raw_bytes[:2048]
            )
            detected = (
                charset_m.group(1).decode("ascii", errors="ignore").lower()
                if charset_m
                else "utf-8"
            )

            for enc in [detected, "utf-8", "cp932", "shift_jis", "euc-jp"]:
                try:
                    html_text = raw_bytes.decode(enc)
                    break
                except Exception:
                    continue
            if not html_text:
                html_text = raw_bytes.decode("utf-8", errors="ignore")

            # 不要なスクリプトタグを削除
            clean_html = re.sub(
                r"<script.*?>.*?</script>",
                "",
                html_text,
                flags=re.DOTALL | re.IGNORECASE,
            )
            clean_html = re.sub(
                r"<style.*?>.*?</style>",
                "",
                clean_html,
                flags=re.DOTALL | re.IGNORECASE,
            )

            # ページ内のすべてのリンク <a> を抽出
            a_matches = list(
                re.finditer(
                    r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                    clean_html,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            )

            for m in a_matches:
                raw_href = m.group(1).strip()
                inside_html = m.group(2)

                if raw_href.startswith(
                    ("javascript:", "#", "mailto:", "tel:")
                ):
                    continue

                full_url = urllib.parse.urljoin(url, raw_href)
                if full_url in seen_urls:
                    continue

                inside_text = re.sub(r"<[^>]+>", " ", inside_html)
                inside_text = html.unescape(inside_text)
                inside_text = re.sub(r"\s+", " ", inside_text).strip()

                # ★リンクの「直前250文字」と「直後100文字」を取得
                # これにより、近鉄などの <dt>日付</dt><dd><a href=...>見出し</a></dd> 構造も確実に捉えます
                start_pos = m.start()
                end_pos = m.end()
                before_html = clean_html[max(0, start_pos - 250) : start_pos]
                after_html = clean_html[
                    end_pos : min(len(clean_html), end_pos + 100)
                ]

                # 日付の探索（リンク内 -> リンク直前 -> リンク直後の順）
                found_date = parse_date_text(inside_html, current_year)
                if not found_date:
                    found_date = parse_date_text(before_html, current_year)
                if not found_date:
                    found_date = parse_date_text(after_html, current_year)

                if not found_date:
                    continue

                # 期間内判定
                if not (start_date <= found_date <= end_date):
                    continue

                # 見出しタイトルの決定
                title = inside_text
                if len(title) < 5 or title.lower() in [
                    "pdf",
                    "詳細",
                    "こちら",
                    "詳しくはこちら",
                ]:
                    comb = re.sub(
                        r"<[^>]+>",
                        " ",
                        before_html + " " + inside_html + " " + after_html,
                    )
                    comb = html.unescape(comb)
                    title = re.sub(r"\s+", " ", comb).strip()

                # タイトル先頭の日付・不要記号を削除
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

                is_pdf = bool(
                    re.search(r"\.pdf$", full_url, re.IGNORECASE)
                    or "pdf" in inside_html.lower()
                    or "pdf" in before_html.lower()
                )
                doc_type = (
                    "広報発表"
                    if (
                        "release" in full_url.lower()
                        or "press" in full_url.lower()
                        or "ニュースリリース" in (inside_text + before_html)
                    )
                    else "ニュース"
                )

                seen_urls.add(full_url)
                results.append({
                    "date": found_date,
                    "type": doc_type,
                    "title": title,
                    "url": full_url,
                    "is_pdf": is_pdf,
                })
        except Exception:
            pass

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
        "会社分類",
        ["すべて", "JR", "私鉄（メトロ含む）", "近鉄（近畿日本鉄道のみ）"],
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
        news_items = fetch_company_news(comp["urls"], start_date, end_date)
        new_data[comp["name"]] = news_items
        progress_bar.progress((i + 1) / len(COMPANIES))

    st.session_state.fetched_data = new_data
    status_text.empty()
    progress_bar.empty()
    st.toast("全社の巡回・データ取得が完了しました！", icon="✅")

# ==========================================
# 5. 結果の表示（全会社を必ず表示、無ければ「なし」）
# ==========================================
if not st.session_state.fetched_data and not run_button:
    st.info(
        "👈 左のサイドバーで期間を指定し、「公式サイトを巡回して取得」ボタンを押してください。"
    )
else:
    current_category = None

    for comp in COMPANIES:
        # サイドバーの絞り込み処理
        if selected_category == "JR" and comp["category"] != "JR":
            continue
        if (
            selected_category == "私鉄（メトロ含む）"
            and comp["category"] != "私鉄（メトロ含む）"
        ):
            continue
        if (
            selected_category == "近鉄（近畿日本鉄道のみ）"
            and "近畿日本鉄道" not in comp["name"]
        ):
            continue

        items = st.session_state.fetched_data.get(comp["name"], [])

        # キーワード検索
        if search_keyword:
            kw = search_keyword.lower()
            items = [
                item
                for item in items
                if kw in item["title"].lower() or kw in comp["name"].lower()
            ]

        # JR / 私鉄のセクション見出し
        if comp["category"] != current_category:
            if current_category is not None:
                st.write("<br><br>", unsafe_allow_html=True)
            current_category = comp["category"]
            st.markdown(f"## 【 {current_category}各社 】（東から西順）")
            st.divider()

        # 会社ヘッダー
        main_url = comp["urls"][0]
        hd_label = " ＆ 持株会社" if len(comp["urls"]) > 1 else ""
        st.markdown(
            f"### 🏢 {comp['name']} <span style='font-size:0.8em;"
            f" color:gray;'>（{comp['region']}）</span> [公式ページ{hd_label}"
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
                    with col_right:
                        st.markdown(f"##### [{item['title']}]({item['url']})")
                        st.markdown(
                            f"🔗 **リンク:** [{item['url']}]({item['url']})"
                        )
            st.write("")
