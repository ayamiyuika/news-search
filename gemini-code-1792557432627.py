import urllib.request
import urllib.parse
import re
import datetime
import html
import streamlit as st
from html.parser import HTMLParser

# ページ設定
st.set_page_config(
    page_title="全国大手鉄道 ニュース＆広報チェッカー",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社 ニュース・広報発表 巡回チェッカー")
st.caption("指定した期間内の各社の公式ページを実際に自動巡回し、見出しを抽出・表示します。")

# ==========================================
# 1. 鉄道会社のマスターデータ（東から西順）
# ==========================================
COMPANIES = [
    {"category": "JR", "name": "JR北海道", "order": 1, "region": "北海道", "url": "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html"},
    {"category": "JR", "name": "JR東日本", "order": 2, "region": "東日本", "url": "https://www.jreast.co.jp/company/"},
    {"category": "JR", "name": "JR東海", "order": 3, "region": "東海", "url": "https://jr-central.co.jp/"},
    {"category": "JR", "name": "JR西日本", "order": 4, "region": "西日本", "url": "https://www.westjr.co.jp/press/"},
    {"category": "JR", "name": "JR四国", "order": 5, "region": "四国", "url": "https://www.jr-shikoku.co.jp/03_news/press/"},
    {"category": "JR", "name": "JR九州", "order": 6, "region": "九州", "url": "https://www.jrkyushu.co.jp/news/release/index.html"},
    {"category": "私鉄（メトロ含む）", "name": "東武鉄道", "order": 101, "region": "関東", "url": "https://www.tobu.co.jp/newsrelease/"},
    {"category": "私鉄（メトロ含む）", "name": "京成電鉄", "order": 102, "region": "関東", "url": "https://www.keisei.co.jp/keisei/kouhou/news/index.php"},
    {"category": "私鉄（メトロ含む）", "name": "東京メトロ", "order": 103, "region": "関東", "url": "https://www.tokyometro.jp/news/index.html"},
    {"category": "私鉄（メトロ含む）", "name": "西武鉄道", "order": 104, "region": "関東", "url": "https://www.seiburailway.jp/newsroom/news/"},
    {"category": "私鉄（メトロ含む）", "name": "京王電鉄", "order": 105, "region": "関東", "url": "https://www.keio.co.jp/news/update/index.html"},
    {"category": "私鉄（メトロ含む）", "name": "小田急電鉄", "order": 106, "region": "関東", "url": "https://www.odakyu.jp/company/about/news/"},
    {"category": "私鉄（メトロ含む）", "name": "東急電鉄", "order": 107, "region": "関東", "url": "https://www.tokyu.co.jp/information/"},
    {"category": "私鉄（メトロ含む）", "name": "京浜急行電鉄", "order": 108, "region": "関東", "url": "https://www.keikyu.co.jp/company/news/"},
    {"category": "私鉄（メトロ含む）", "name": "相模鉄道", "order": 109, "region": "関東", "url": "https://www.sotetsu.co.jp/pressrelease/"},
    {"category": "私鉄（メトロ含む）", "name": "名古屋鉄道", "order": 110, "region": "東海", "url": "https://www.meitetsu.co.jp/profile/news/"},
    {"category": "私鉄（メトロ含む）", "name": "近畿日本鉄道", "order": 111, "region": "関西", "url": "https://www.kintetsu.co.jp/all_news/whatsnew.html"},
    {"category": "私鉄（メトロ含む）", "name": "京阪電気鉄道", "order": 112, "region": "関西", "url": "https://www.keihan.co.jp/corporate/release/"},
    {"category": "私鉄（メトロ含む）", "name": "南海電気鉄道", "order": 113, "region": "関西", "url": "https://www.nankai.co.jp/news.html"},
    {"category": "私鉄（メトロ含む）", "name": "阪神電気鉄道", "order": 114, "region": "関西", "url": "https://www.hanshin.co.jp/company/press/"},
    {"category": "私鉄（メトロ含む）", "name": "阪急電鉄", "order": 115, "region": "関西", "url": "https://www.hankyu.co.jp/company/news/index.html"},
    {"category": "私鉄（メトロ含む）", "name": "西日本鉄道", "order": 116, "region": "九州", "url": "https://www.nishitetsu.co.jp/release/"},
]

# ==========================================
# 2. Webサイト解析（スクレイピング）エンジン
# ==========================================
class NewsParser(HTMLParser):
    """HTMLから日付とリンクの塊（ブロック）を抽出する専用パーサー"""
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.blocks = []
        self.current_text_parts = []
        self.current_hrefs = []
        # これらで囲まれた部分を1つのニュース記事として認識する
        self.block_tags = {"div", "li", "tr", "dd", "p", "article", "section", "ul", "dl"}
        
    def handle_starttag(self, tag, attrs):
        if tag in self.block_tags:
            self._save_block()
        elif tag == "a":
            for attr in attrs:
                if attr[0] == "href":
                    link = urllib.parse.urljoin(self.base_url, attr[1])
                    if not link.startswith("javascript:") and not link.startswith("#"):
                        self.current_hrefs.append(link)

    def handle_endtag(self, tag):
        if tag in self.block_tags:
            self._save_block()

    def handle_data(self, data):
        text = data.strip()
        if text:
            text = re.sub(r'\s+', ' ', text) # 余分な空白を削除
            self.current_text_parts.append(text)

    def _save_block(self):
        full_text = " ".join(self.current_text_parts).strip()
        # テキストとリンクが存在する場合のみ保存
        if full_text and self.current_hrefs:
            self.blocks.append((full_text, self.current_hrefs[0]))
        self.current_text_parts = []
        self.current_hrefs = []

def extract_date(text, current_year):
    """テキストから日付らしきものを探し出す"""
    # 2026年10月21日, 2026.10.21, 2026/10/21
    m1 = re.search(r'(202[0-9])[年\./]\s*(1[0-2]|0?[1-9])[月\./]\s*(3[01]|[12][0-9]|0?[1-9])', text)
    if m1:
        try:
            return datetime.date(int(m1.group(1)), int(m1.group(2)), int(m1.group(3)))
        except ValueError:
            pass
            
    # 10月21日, 10.21, 10/21
    m2 = re.search(r'(1[0-2]|0?[1-9])[月\./]\s*(3[01]|[12][0-9]|0?[1-9])[日]?', text)
    if m2:
        try:
            return datetime.date(current_year, int(m2.group(1)), int(m2.group(2)))
        except ValueError:
            pass
    return None

def fetch_real_news(company_info, start_date, end_date):
    """指定された会社のURLにアクセスし、期間内のニュースを抽出する"""
    url = company_info["url"]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    req = urllib.request.Request(url, headers=headers)
    results = []
    current_year = datetime.date.today().year

    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            html_bytes = res.read()
            # 文字化け防止（UTF-8かShift_JISを自動判別して解読）
            try:
                html_content = html_bytes.decode('utf-8')
            except UnicodeDecodeError:
                html_content = html_bytes.decode('shift_jis', errors='ignore')

        parser = NewsParser(url)
        parser.feed(html_content)
        
        seen_urls = set()
        for text, href in parser.blocks:
            # ニュースではないシステム用のリンクを除外
            if len(text) < 10 or text in ["一覧", "トップへ戻る", "詳細はこちら"]:
                continue
                
            found_date = extract_date(text, current_year)
            # 指定された期間内の日付ならリストに追加
            if found_date and (start_date <= found_date <= end_date):
                if href not in seen_urls:
                    seen_urls.add(href)
                    
                    is_pdf = bool(re.search(r'\.pdf$', href, re.IGNORECASE) or "PDF" in text.upper())
                    doc_type = "広報発表" if ("release" in href.lower() or "press" in href.lower() or "ニュースリリース" in text) else "ニュース"
                    
                    # 見出しから日付部分を取り除いてすっきりさせる
                    clean_title = re.sub(r'^(202[0-9])[年\./]\s*(1[0-2]|0?[1-9])[月\./]\s*(3[01]|[12][0-9]|0?[1-9])日?\s*', '', text)
                    clean_title = re.sub(r'^(1[0-2]|0?[1-9])[月\./]\s*(3[01]|[12][0-9]|0?[1-9])日?\s*', '', clean_title)
                    
                    results.append({
                        "company": company_info["name"],
                        "date": found_date,
                        "type": doc_type,
                        "title": clean_title,
                        "url": href,
                        "is_pdf": is_pdf,
                        "order": company_info["order"],
                        "category": company_info["category"],
                        "official_url": company_info["url"],
                        "region": company_info["region"]
                    })
    except Exception as e:
        # サイトが重い・接続できない等のエラー時はスキップ
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
    
    # 期間の確定（日付が1つだけ選ばれた場合のエラー回避）
    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = date_range[0]
        end_date = date_range[0]

    st.markdown("---")
    st.write("**2. 絞り込み表示**")
    selected_category = st.radio("会社分類", ["すべて", "JR", "私鉄（メトロ含む）"])
    search_keyword = st.text_input("キーワード検索", "")
    
    st.markdown("---")
    # このボタンを押したときだけ、実際にサイトへ情報を取りに行く
    run_button = st.button("🔄 公式サイトを巡回して取得", type="primary", use_container_width=True)

# ==========================================
# 4. データ取得の実行と表示処理
# ==========================================
# 取得したデータを保持する領域
if "fetched_data" not in st.session_state:
    st.session_state.fetched_data = []

if run_button:
    all_news = []
    # 進行状況バーを表示
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, comp in enumerate(COMPANIES):
        status_text.text(f"巡回中: {comp['name']} ({i+1}/{len(COMPANIES)}) ...")
        # 実際のサイトへアクセス
        news_items = fetch_real_news(comp, start_date, end_date)
        all_news.extend(news_items)
        progress_bar.progress((i + 1) / len(COMPANIES))
        
    st.session_state.fetched_data = all_news
    status_text.empty()
    progress_bar.empty()
    st.toast("全社の巡回・データ取得が完了しました！", icon="✅")

# データの表示
filtered_items = []
for item in st.session_state.fetched_data:
    # 絞り込み判定
    if selected_category != "すべて" and item["category"] != selected_category:
        continue
    if search_keyword:
        kw = search_keyword.lower()
        if kw not in item["title"].lower() and kw not in item["company"].lower():
            continue
    filtered_items.append(item)

# 会社順（東から西）、日付順（新しい順）に並び替え
filtered_items.sort(key=lambda x: (x["order"], x["date"]), reverse=False)

# 会社ごとにグループ分け
grouped_data = {}
for item in filtered_items:
    c_name = item["company"]
    if c_name not in grouped_data:
        grouped_data[c_name] = []
    grouped_data[c_name].append(item)

# 会社内では日付が新しい順にする
for c_name in grouped_data:
    grouped_data[c_name].sort(key=lambda x: x["date"], reverse=True)

# 画面への書き出し
if not st.session_state.fetched_data and not run_button:
    st.info("👈 左のサイドバーで期間を指定し、「公式サイトを巡回して取得」ボタンを押してください。")
elif not grouped_data:
    st.warning("指定した条件（期間・キーワード）に該当する発表は見つかりませんでした。")
else:
    current_category = None

    for comp_name, items in grouped_data.items():
        # JR / 私鉄のセクション見出しを自動挿入
        cat = items[0]["category"]
        if cat != current_category:
            current_category = cat
            st.markdown(f"## 【 {current_category}各社 】（東から西順）")
            st.divider()

        region = items[0]["region"]
        official_url = items[0]["official_url"]
        
        st.markdown(f"### 🏢 {comp_name} <span style='font-size:0.8em; color:gray;'>（{region}）</span> [公式ページ ↗]({official_url})", unsafe_allow_html=True)

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
                    # 見出しタイトル（短縮せずに全表示）とリンク
                    st.markdown(f"##### [{item['title']}]({item['url']})")
                    st.markdown(f"🔗 **リンク:** [{item['url']}]({item['url']})")
        st.write("") # 少し余白を空ける
