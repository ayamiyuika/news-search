import urllib.request
import urllib.parse
import re
import datetime
import html
import streamlit as st

# ページ設定
st.set_page_config(
    page_title="全国大手鉄道 ニュース＆広報チェッカー",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社 ニュース・広報発表 巡回チェッカー")
st.caption("指定した期間内の各社の公式ページ（持株会社含む）を自動巡回し、すべての会社の状況を表示します。")

# ==========================================
# 1. 鉄道会社・持株会社のマスターデータ
# ==========================================
COMPANIES = [
    # --- JR各社 ---
    {"category": "JR", "name": "JR北海道", "region": "北海道", "urls": ["https://www.jrhokkaido.co.jp/CM/info/press/presstop.html"]},
    {"category": "JR", "name": "JR東日本", "region": "東日本", "urls": ["https://www.jreast.co.jp/company/"]},
    {"category": "JR", "name": "JR東海", "region": "東海", "urls": ["https://jr-central.co.jp/"]},
    {"category": "JR", "name": "JR西日本", "region": "西日本", "urls": ["https://www.westjr.co.jp/press/"]},
    {"category": "JR", "name": "JR四国", "region": "四国", "urls": ["https://www.jr-shikoku.co.jp/03_news/press/"]},
    {"category": "JR", "name": "JR九州", "region": "九州", "urls": ["https://www.jrkyushu.co.jp/news/release/index.html"]},
    
    # --- 私鉄・メトロ各社（東から順） ---
    {"category": "私鉄（メトロ含む）", "name": "東武鉄道", "region": "関東", "urls": ["https://www.tobu.co.jp/newsrelease/"]},
    {"category": "私鉄（メトロ含む）", "name": "西武鉄道（西武HD含む）", "region": "関東", "urls": ["https://www.seiburailway.jp/newsroom/news/", "https://www.seibuholdings.co.jp/news/"]},
    {"category": "私鉄（メトロ含む）", "name": "京成電鉄", "region": "関東", "urls": ["https://www.keisei.co.jp/keisei/kouhou/news/index.php"]},
    {"category": "私鉄（メトロ含む）", "name": "東京メトロ", "region": "関東", "urls": ["https://www.tokyometro.jp/news/index.html"]},
    {"category": "私鉄（メトロ含む）", "name": "京王電鉄", "region": "関東", "urls": ["https://www.keio.co.jp/news/update/index.html"]},
    {"category": "私鉄（メトロ含む）", "name": "小田急電鉄", "region": "関東", "urls": ["https://www.odakyu.jp/company/about/news/"]},
    {"category": "私鉄（メトロ含む）", "name": "東急電鉄（東急HD相当含む）", "region": "関東", "urls": ["https://www.tokyu.co.jp/information/", "https://www.tokyu.co.jp/company/news/"]},
    {"category": "私鉄（メトロ含む）", "name": "京浜急行電鉄", "region": "関東", "urls": ["https://www.keikyu.co.jp/company/news/"]},
    {"category": "私鉄（メトロ含む）", "name": "相模鉄道（相鉄HD含む）", "region": "関東", "urls": ["https://www.sotetsu.co.jp/pressrelease/", "https://www.sotetsu.co.jp/news/"]},
    {"category": "私鉄（メトロ含む）", "name": "名古屋鉄道", "region": "東海", "urls": ["https://www.meitetsu.co.jp/profile/news/"]},
    {"category": "私鉄（メトロ含む）", "name": "近畿日本鉄道（近鉄グループHD含む）", "region": "関西", "urls": ["https://www.kintetsu.co.jp/all_news/whatsnew.html", "https://www.kintetsu-g-hd.co.jp/news/"]},
    {"category": "私鉄（メトロ含む）", "name": "京阪電気鉄道（京阪HD含む）", "region": "関西", "urls": ["https://www.keihan.co.jp/corporate/release/", "https://www.keihan-holdings.co.jp/news/"]},
    {"category": "私鉄（メトロ含む）", "name": "南海電気鉄道", "region": "関西", "urls": ["https://www.nankai.co.jp/news.html"]},
    {"category": "私鉄（メトロ含む）", "name": "大阪メトロ (Osaka Metro)", "region": "関西", "urls": ["https://subway.osakametro.co.jp/news/"]},
    {"category": "私鉄（メトロ含む）", "name": "阪神電気鉄道（阪急阪神HD含む）", "region": "関西", "urls": ["https://www.hanshin.co.jp/company/press/", "https://www.hankyu-hanshin.co.jp/release/"]},
    {"category": "私鉄（メトロ含む）", "name": "阪急電鉄（阪急阪神HD含む）", "region": "関西", "urls": ["https://www.hankyu.co.jp/company/news/index.html", "https://www.hankyu-hanshin.co.jp/release/"]},
    {"category": "私鉄（メトロ含む）", "name": "西日本鉄道", "region": "九州", "urls": ["https://www.nishitetsu.co.jp/ja/news.html"]},
]

# ==========================================
# 2. 強力なWebサイト解析（スクレイピング）エンジン
# ==========================================
def fetch_company_news(urls, start_date, end_date):
    """指定された複数のURL（子会社＋親会社）にアクセスし、期間内のニュースを抽出する"""
    results = []
    current_year = datetime.date.today().year
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    seen_urls = set()
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as res:
                html_bytes = res.read()
                try:
                    html_content = html_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    html_content = html_bytes.decode('shift_jis', errors='ignore')

            # スクリプトとスタイルタグを削除してプレーンテキストにしやすくする
            clean_html = re.sub(r'<script.*?>.*?</script>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
            clean_html = re.sub(r'<style.*?>.*?</style>', '', clean_html, flags=re.DOTALL|re.IGNORECASE)

            # 記事ブロックになりそうなタグでHTMLを分割
            blocks = re.split(r'</?(?:div|li|tr|dd|p|article|section|ul|dl|dt)[^>]*>', clean_html, flags=re.IGNORECASE)

            for block in blocks:
                # <a>タグ（リンク）を探す
                a_match = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, flags=re.IGNORECASE|re.DOTALL)
                if not a_match:
                    continue

                href = a_match.group(1)
                # HTMLタグを取り除いて純粋なテキストにする
                link_text = re.sub(r'<[^>]+>', '', a_match.group(2)).strip()
                link_text = html.unescape(link_text)

                block_text = re.sub(r'<[^>]+>', '', block)
                block_text = html.unescape(block_text)
                block_text = re.sub(r'\s+', ' ', block_text).strip()

                # リンク自体の文字が短すぎる場合は、周辺のテキストを見出しとして採用
                title_text = link_text if len(link_text) > 8 else block_text

                if len(title_text) < 5 or title_text in ["一覧", "トップへ戻る", "詳細はこちら", "次へ", "前へ"]:
                    continue

                full_url = urllib.parse.urljoin(url, href)
                if full_url.startswith("javascript:") or full_url.startswith("#"):
                    continue

                # 日付の抽出
                found_date = None
                # yyyy.mm.dd または yyyy年mm月dd日 のパターン
                m1 = re.search(r'(202[0-9])[年\./]\s*(1[0-2]|0?[1-9])[月\./]\s*(3[01]|[12][0-9]|0?[1-9])', block_text)
                if m1:
                    try:
                        found_date = datetime.date(int(m1.group(1)), int(m1.group(2)), int(m1.group(3)))
                    except ValueError:
                        pass
                else:
                    # mm.dd または mm月dd日 のパターン（今年は自動補完）
                    m2 = re.search(r'(1[0-2]|0?[1-9])[月\./]\s*(3[01]|[12][0-9]|0?[1-9])[日]?', block_text)
                    if m2:
                        try:
                            found_date = datetime.date(current_year, int(m2.group(1)), int(m2.group(2)))
                        except ValueError:
                            pass

                # 指定期間内の日付が検出できたらリストに追加
                if found_date and (start_date <= found_date <= end_date):
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        
                        is_pdf = bool(re.search(r'\.pdf$', full_url, re.IGNORECASE) or "PDF" in block_text.upper())
                        doc_type = "広報発表" if ("release" in full_url.lower() or "press" in full_url.lower() or "ニュースリリース" in block_text) else "ニュース"

                        # 見出しの先頭にある日付テキストを削除してスッキリさせる
                        clean_title = re.sub(r'^(202[0-9])[年\./]\s*(1[0-2]|0?[1-9])[月\./]\s*(3[01]|[12][0-9]|0?[1-9])日?\s*', '', title_text)
                        clean_title = re.sub(r'^(1[0-2]|0?[1-9])[月\./]\s*(3[01]|[12][0-9]|0?[1-9])日?\s*', '', clean_title)

                        results.append({
                            "date": found_date,
                            "type": doc_type,
                            "title": clean_title,
                            "url": full_url,
                            "is_pdf": is_pdf,
                        })
        except Exception:
            # サイトへのアクセスに失敗した場合はスキップ（表示側で「なし」になる）
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
        max_value=today
    )
    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range[0]

    st.markdown("---")
    st.write("**2. 絞り込み表示**")
    # 「近鉄」の専用ボタンを追加
    selected_category = st.radio("会社分類", ["すべて", "JR", "私鉄（メトロ含む）", "近鉄（近畿日本鉄道のみ）"])
    search_keyword = st.text_input("キーワード検索", "")
    
    st.markdown("---")
    run_button = st.button("🔄 公式サイトを巡回して取得", type="primary", use_container_width=True)

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
        # 会社本体とHD（持株会社）のURLを巡回
        news_items = fetch_company_news(comp["urls"], start_date, end_date)
        new_data[comp["name"]] = news_items
        progress_bar.progress((i + 1) / len(COMPANIES))
        
    st.session_state.fetched_data = new_data
    status_text.empty()
    progress_bar.empty()
    st.toast("全社の巡回・データ取得が完了しました！", icon="✅")

# ==========================================
# 5. 結果の表示（必ず全会社を表示するロジック）
# ==========================================
if not st.session_state.fetched_data and not run_button:
    st.info("👈 左のサイドバーで期間を指定し、「公式サイトを巡回して取得」ボタンを押してください。")
else:
    current_category = None

    # COMPANIESリストの順番（東から西）に沿って必ずループを回す
    for comp in COMPANIES:
        
        # --- サイドバーの絞り込み処理 ---
        if selected_category == "JR" and comp["category"] != "JR":
            continue
        if selected_category == "私鉄（メトロ含む）" and comp["category"] != "私鉄（メトロ含む）":
            continue
        if selected_category == "近鉄（近畿日本鉄道のみ）" and "近畿日本鉄道" not in comp["name"]:
            continue
            
        # 取得したニュースリストを取り出す
        items = st.session_state.fetched_data.get(comp["name"], [])
        
        # キーワード検索でさらに絞り込む
        if search_keyword:
            kw = search_keyword.lower()
            items = [item for item in items if kw in item["title"].lower() or kw in comp["name"].lower()]

        # --- 画面の描画 ---
        # JRと私鉄の区切り線を引く
        if comp["category"] != current_category:
            if current_category is not None:
                st.write("<br><br>", unsafe_allow_html=True)
            current_category = comp["category"]
            st.markdown(f"## 【 {current_category}各社 】（東から西順）")
            st.divider()

        # 会社名と公式ページへのリンクを表示（ここは必ず表示される）
        main_url = comp["urls"][0]
        hd_label = " ＆ 持株会社" if len(comp["urls"]) > 1 else ""
        st.markdown(f"### 🏢 {comp['name']} <span style='font-size:0.8em; color:gray;'>（{comp['region']}）</span> [公式ページ{hd_label} ↗]({main_url})", unsafe_allow_html=True)

        # 発表が「ある」か「ない（なし）」かで分岐
        if not items:
            # 発表がない場合は「なし」と表示
            st.info("📅 指定期間内の発表は **なし** です。")
            st.write("")
        else:
            # 発表がある場合は新しい日付順にソートしてカードで表示
            items.sort(key=lambda x: x["date"], reverse=True)
            for item in items:
                type_badge = "📢 **広報発表**" if item["type"] == "広報発表" else "📰 **ニュース**"
                file_badge = "🟥 **[PDF資料]**" if item["is_pdf"] else "🌐 **[Web発表]**"

                with st.container(border=True):
                    col_left, col_right = st.columns([1, 4])
                    with col_left:
                        st.write(f"📅 **{item['date']}**")
                        st.markdown(type_badge)
                        st.markdown(file_badge)
                    with col_right:
                        st.markdown(f"##### [{item['title']}]({item['url']})")
                        st.markdown(f"🔗 **リンク:** [{item['url']}]({item['url']})")
            st.write("")
