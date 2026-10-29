import base64
import datetime
import email.utils
import gzip
import html
import http.cookiejar
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
import streamlit as st
import streamlit.components.v1 as components

# 日本標準時（JST）の定義
JST = datetime.timezone(datetime.timedelta(hours=9))

# ページ基本設定
st.set_page_config(
    page_title="全国大手鉄道会社 公式発表・ニュース 概要",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社 公式発表・ニュース 概要")
st.caption("JR・大手私鉄・近鉄グループ各社の公式発表・最新ニュースを一覧表示します。")

# ==========================================
# 0. メディア優先度スコア定義（有力メディア優先判定用）
# ==========================================
MEDIA_PRIORITY = {
    "NHK NEWS": 100, "日本経済新聞": 95, "読売新聞オンライン": 90, "朝日新聞デジタル": 90,
    "共同通信": 85, "毎日新聞": 85, "産経ニュース": 85, "時事通信": 80, "Yahoo!ニュース": 75,
    "乗りものニュース": 72, "鉄道コム": 70, "鉄道ファン (railf.jp)": 70, "マイナビニュース": 65,
    "東洋経済オンライン": 65, "ITmedia": 60, "ダイヤモンド・オンライン": 60,
    "FNNプライムオンライン": 55, "テレ朝news": 55, "TBS NEWS DIG": 55, "日テレNEWS": 55,
    "神戸新聞NEXT": 50, "京都新聞": 50, "中日新聞": 50, "東京新聞": 50, "北海道新聞": 50, "西日本新聞": 50
}

MEDIA_NAME_MAP = {
    "asahi.com": "朝日新聞デジタル", "nikkei.com": "日本経済新聞", "yomiuri.co.jp": "読売新聞オンライン",
    "mainichi.jp": "毎日新聞", "sankei.com": "産経ニュース", "yahoo.co.jp": "Yahoo!ニュース",
    "trafficnews.jp": "乗りものニュース", "tetsudo.com": "鉄道コム", "railf.jp": "鉄道ファン (railf.jp)",
    "news.mynavi.jp": "マイナビニュース", "itmedia.co.jp": "ITmedia", "toyokeizai.net": "東洋経済オンライン",
    "diamond.jp": "ダイヤモンド・オンライン", "kyodo.co.jp": "共同通信", "nordot.app": "ノードット (共同通信系)",
    "jiji.com": "時事通信", "nhk.or.jp": "NHK NEWS", "kobe-np.co.jp": "神戸新聞NEXT", "kyoto-np.co.jp": "京都新聞",
    "chunichi.co.jp": "中日新聞", "tokyo-np.co.jp": "東京新聞", "hokkaido-np.co.jp": "北海道新聞",
    "nishinippon.co.jp": "西日本新聞", "reuters.com": "ロイター", "bloomberg.co.jp": "ブルームバーグ",
    "fnn.jp": "FNNプライムオンライン", "tv-asahi.co.jp": "テレ朝news", "tbs.co.jp": "TBS NEWS DIG",
    "ntv.co.jp": "日テレNEWS", "prtimes.jp": "PR TIMES",
}

NAV_EXCLUDE_WORDS = {
    "キャラクター", "インスタ映え", "アトラクション", "関連事業", "採用情報", "リンク集",
    "会社概要", "経営理念", "企業情報", "サイトマップ", "プライバシーポリシー", "アクセス",
    "お問い合わせ", "よくあるご質問", "電子公告", "運賃", "時刻表", "路線図", "サービス",
    "ハーベス", "kinsho", "店舗情報", "チラシ情報", "もっと見る", "もっと、", "一覧",
    "ホーム", "top", "トップ", "企業・ir情報", "企業サイト", "安全報告書", "役員一覧",
    "組織図", "沿革", "次へ", "前へ", "« 前ページへ", "前ページへ »", "次ページへ", "«", "»",
    "空港リムジンバス", "路線バス", "貸切バス", "高速バス"
}

# セッションステートの初期化（完全排他：初期は公式発表のみ青色ON）
today = datetime.datetime.now(JST).date()

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "official"  # "official" または "news"
if "period_days" not in st.session_state:
    st.session_state.period_days = 3          # 初期：3日間
if "custom_date_range" not in st.session_state:
    st.session_state.custom_date_range = (today - datetime.timedelta(days=2), today)
if "hidden_companies" not in st.session_state:
    st.session_state.hidden_companies = set()
if "selected_filter_companies" not in st.session_state:
    st.session_state.selected_filter_companies = set()
if "diag_logs" not in st.session_state:
    st.session_state.diag_logs = {}

# クエリパラメータ処理
selected_from_query = []
try:
    if hasattr(st.query_params, "get_all"):
        selected_from_query = st.query_params.get_all("c")
    else:
        val = st.query_params.get("c")
        if isinstance(val, list):
            selected_from_query = val
        elif isinstance(val, str):
            selected_from_query = [val]
except Exception:
    pass

if "submitted" in st.query_params:
    st.session_state.selected_filter_companies = set(selected_from_query)
    st.query_params.clear()
elif "reset" in st.query_params:
    st.session_state.selected_filter_companies.clear()
    st.query_params.clear()

# ==========================================
# 1. 会社マスタープール（JR東日本・近鉄GHD・近鉄・阪急にPR TIMES設定追加）
# ==========================================
COMPANY_POOL = {
    # --- JR各社 ---
    "jr-hokkaido": {
        "id": "jr-hokkaido", "name": "JR北海道", "top_url": "https://www.jrhokkaido.co.jp/",
        "official_domains": ["jrhokkaido.co.jp"],
        "urls": ["https://www.jrhokkaido.co.jp/CM/info/press/presstop.html", "https://www.jrhokkaido.co.jp/"],
        "query": "JR北海道 OR 北海道旅客鉄道",
    },
    # ★ JR東日本（PR TIMES直接取得 ＋ 公式巡回）
    "jr-east": {
        "id": "jr-east", "name": "JR東日本", "is_jr_east": True, "top_url": "https://www.jreast.co.jp/",
        "official_domains": ["jreast.co.jp", "prtimes.jp", "tetsudo.com"],
        "prtimes_url": "https://prtimes.jp/main/html/searchrlp/company_id/17557",
        "urls": [
            "https://prtimes.jp/main/html/searchrlp/company_id/17557",
            "https://www.jreast.co.jp/press/",
            "https://www.tetsudo.com/railway/0002/release/",
        ],
        "query": "JR東日本 OR 東日本旅客鉄道",
    },
    "jr-central": {
        "id": "jr-central", "name": "JR東海", "top_url": "https://jr-central.co.jp/",
        "official_domains": ["jr-central.co.jp"],
        "urls": ["https://jr-central.co.jp/news/release/", "https://jr-central.co.jp/news/", "https://jr-central.co.jp/"],
        "query": "JR東海 OR 東海旅客鉄道",
    },
    "jr-west": {
        "id": "jr-west", "name": "JR西日本", "top_url": "https://www.westjr.co.jp/",
        "official_domains": ["westjr.co.jp"],
        "urls": ["https://www.westjr.co.jp/press/article/", "https://www.westjr.co.jp/press/", "https://www.westjr.co.jp/"],
        "query": "JR西日本 OR 西日本旅客鉄道",
    },
    "jr-shikoku": {
        "id": "jr-shikoku", "name": "JR四国", "top_url": "https://www.jr-shikoku.co.jp/",
        "official_domains": ["jr-shikoku.co.jp"],
        "urls": ["https://www.jr-shikoku.co.jp/03_news/press/", "https://www.jr-shikoku.co.jp/"],
        "query": "JR四国 OR 四国旅客鉄道",
    },
    "jr-kyushu": {
        "id": "jr-kyushu", "name": "JR九州", "top_url": "https://www.jrkyushu.co.jp/",
        "official_domains": ["jrkyushu.co.jp"],
        "urls": ["https://www.jrkyushu.co.jp/news/release/index.html", "https://www.jrkyushu.co.jp/news/"],
        "query": "JR九州 OR 九州旅客鉄道",
    },
    # --- 私鉄各社 ---
    "tobu": {
        "id": "tobu", "name": "東武鉄道", "top_url": "https://www.tobu.co.jp/",
        "official_domains": ["tobu.co.jp"],
        "urls": ["https://www.tobu.co.jp/newsrelease/", "https://www.tobu.co.jp/"],
        "query": "東武鉄道",
    },
    "seibu": {
        "id": "seibu", "name": "西武鉄道（西武HD含む）", "top_url": "https://www.seiburailway.jp/",
        "official_domains": ["seiburailway.jp", "seibuholdings.co.jp"],
        "urls": ["https://www.seiburailway.jp/newsroom/news/", "https://www.seibuholdings.co.jp/news/", "https://www.seiburailway.jp/"],
        "query": "西武鉄道 OR 西武ホールディングス",
    },
    "keisei": {
        "id": "keisei", "name": "京成電鉄", "top_url": "https://www.keisei.co.jp/",
        "official_domains": ["keisei.co.jp"],
        "urls": ["https://www.keisei.co.jp/", "https://www.keisei.co.jp/news/"],
        "query": "京成電鉄",
    },
    "keio": {
        "id": "keio", "name": "京王電鉄", "top_url": "https://www.keio.co.jp/",
        "official_domains": ["keio.co.jp"],
        "urls": ["https://www.keio.co.jp/news/update/news_release/", "https://www.keio.co.jp/news/update/index.html", "https://www.keio.co.jp/"],
        "query": "京王電鉄",
    },
    "odakyu": {
        "id": "odakyu", "name": "小田急電鉄", "top_url": "https://www.odakyu.jp/company/about/news/",
        "official_domains": ["odakyu.jp"],
        "urls": ["https://www.odakyu.jp/company/about/news/", "https://www.odakyu.jp/news/"],
        "query": "小田急電鉄",
    },
    "tokyu": {
        "id": "tokyu", "name": "東急電鉄（東急を含む）", "top_url": "https://www.tokyu.co.jp/company/news/",
        "official_domains": ["tokyu.co.jp"],
        "urls": [
            "https://www.tokyu.co.jp/company/news/",
            "https://www.tokyu.co.jp/information/",
            "https://www.tokyu.co.jp/",
        ],
        "query": "東急電鉄 OR 東急",
    },
    "keikyu": {
        "id": "keikyu", "name": "京浜急行電鉄", "top_url": "https://www.keikyu.co.jp/company/news/",
        "official_domains": ["keikyu.co.jp"],
        "urls": ["https://www.keikyu.co.jp/company/news/", "https://www.keikyu.co.jp/report/", "https://www.keikyu.co.jp/"],
        "query": "京浜急行電鉄 OR 京急",
    },
    "sotetsu": {
        "id": "sotetsu", "name": "相模鉄道（相鉄HD含む）", "top_url": "https://www.sotetsu.co.jp/",
        "official_domains": ["sotetsu.co.jp"],
        "urls": ["https://www.sotetsu.co.jp/pressrelease/", "https://www.sotetsu.co.jp/news/", "https://www.sotetsu.co.jp/"],
        "query": "相模鉄道 OR 相鉄ホールディングス",
    },
    "meitetsu": {
        "id": "meitetsu", "name": "名古屋鉄道", "top_url": "https://www.meitetsu.co.jp/",
        "official_domains": ["meitetsu.co.jp"],
        "urls": ["https://www.meitetsu.co.jp/profile/news/", "https://www.meitetsu.co.jp/"],
        "query": "名古屋鉄道 OR 名鉄",
    },
    "nankai": {
        "id": "nankai", "name": "南海電気鉄道", "top_url": "https://www.nankai.co.jp/",
        "official_domains": ["nankai.co.jp"],
        "urls": ["https://www.nankai.co.jp/news.html", "https://www.nankai.co.jp/company/news/", "https://www.nankai.co.jp/"],
        "query": "南海電気鉄道 OR 南海電鉄",
    },
    "keihan": {
        "id": "keihan", "name": "京阪電気鉄道（京阪HD含む）", "top_url": "https://www.keihan.co.jp/",
        "official_domains": ["keihan.co.jp", "keihan-holdings.co.jp"],
        "urls": ["https://www.keihan.co.jp/corporate/release/", "https://www.keihan-holdings.co.jp/news/", "https://www.keihan.co.jp/"],
        "query": "京阪電気鉄道 OR 京阪ホールディングス",
    },
    "hanshin": {
        "id": "hanshin", "name": "阪神電気鉄道", "top_url": "https://www.hanshin.co.jp/",
        "official_domains": ["hanshin.co.jp", "hankyu-hanshin.co.jp"],
        "urls": ["https://www.hanshin.co.jp/press/", "https://www.hanshin.co.jp/release/", "https://www.hanshin.co.jp/"],
        "query": "阪神電気鉄道 OR 阪神電車",
    },
    # ★ 阪急電鉄（PR TIMES直接取得 ＋ ニュースリリース巡回）
    "hankyu": {
        "id": "hankyu", "name": "阪急電鉄", "top_url": "https://www.hankyu.co.jp/",
        "official_domains": ["hankyu.co.jp", "hankyu-hanshin.co.jp", "prtimes.jp"],
        "prtimes_url": "https://prtimes.jp/main/html/searchrlp/company_id/8943",
        "urls": [
            "https://prtimes.jp/main/html/searchrlp/company_id/8943",
            "https://www.hankyu.co.jp/company/news/",
            "https://www.hankyu.co.jp/company/news/index.html",
            "https://www.hankyu-hanshin.co.jp/release/",
        ],
        "query": "阪急電鉄 OR 阪急電車",
    },
    # ★ 阪急阪神HD
    "hankyu-hanshin-hd": {
        "id": "hankyu-hanshin-hd", "name": "阪急阪神ホールディングス", "top_url": "https://www.hankyu-hanshin.co.jp/release/",
        "official_domains": ["hankyu-hanshin.co.jp", "prtimes.jp"],
        "urls": [
            "https://prtimes.jp/main/html/searchrlp/company_id/8943",
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hankyu-hanshin.co.jp/",
        ],
        "query": "阪急阪神ホールディングス OR \"阪急阪神HD\"",
    },
    # ★ 西日本鉄道（リリースページ最優先）
    "nishitetsu": {
        "id": "nishitetsu", "name": "西日本鉄道", "top_url": "https://www.nishitetsu.co.jp/ja/news.html",
        "official_domains": ["nishitetsu.co.jp"],
        "urls": [
            "https://www.nishitetsu.co.jp/ja/news.html",
            "https://www.nishitetsu.co.jp/release/",
        ],
        "query": "西日本鉄道 OR 西鉄",
    },
    # --- 近鉄グループ（17社・海遊館なし） ---
    # ★ 近鉄GHD（PR TIMES直接取得 ＋ 自社巡回）
    "kintetsu-ghd": {
        "id": "kintetsu-ghd", "name": "近鉄GHD", "top_url": "https://www.kintetsu-g-hd.co.jp/news-hd/",
        "official_domains": ["kintetsu-g-hd.co.jp", "prtimes.jp"],
        "prtimes_url": "https://prtimes.jp/main/html/searchrlp/company_id/71236",
        "urls": [
            "https://prtimes.jp/main/html/searchrlp/company_id/71236",
            "https://www.kintetsu-g-hd.co.jp/news-hd/",
            "https://www.kintetsu-g-hd.co.jp/news-kg/",
        ],
        "query": "近鉄グループホールディングス OR 近鉄グループHD OR 近鉄GHD OR 近鉄グループ OR 近鉄",
    },
    # ★ 近畿日本鉄道（PR TIMES直接取得 ＋ whatsnew巡回）
    "kintetsu-railway": {
        "id": "kintetsu-railway", "name": "近畿日本鉄道", "top_url": "https://www.kintetsu.co.jp/all_news/whatsnew.html",
        "official_domains": ["kintetsu.co.jp", "prtimes.jp"],
        "prtimes_url": "https://prtimes.jp/main/html/searchrlp/company_id/71236",
        "urls": [
            "https://prtimes.jp/main/html/searchrlp/company_id/71236",
            "https://www.kintetsu.co.jp/all_news/whatsnew.html",
            "https://www.kintetsu.co.jp/all_info/whatsnew.html",
        ],
        "query": "近畿日本鉄道 OR 近鉄電車 OR 近鉄特急 OR 近鉄線 OR 近鉄",
    },
    "kintetsu-fudosan": {
        "id": "kintetsu-fudosan", "name": "近鉄不動産", "top_url": "https://www.kintetsu-re.co.jp/",
        "official_domains": ["kintetsu-re.co.jp"],
        "urls": ["https://www.kintetsu-re.co.jp/news/", "https://www.kintetsu-re.co.jp/corporate/news/", "https://www.kintetsu-re.co.jp/corporate/"],
        "query": "近鉄不動産",
    },
    "abeno-art-museum": {
        "id": "abeno-art-museum", "name": "あべのハルカス美術館", "top_url": "https://www.aham.jp/",
        "official_domains": ["aham.jp"],
        "urls": ["https://www.aham.jp/news/", "https://www.aham.jp/information/", "https://www.aham.jp/"],
        "query": '"あべのハルカス美術館"',
    },
    "kwe": {
        "id": "kwe", "name": "近鉄エクスプレス", "top_url": "https://www.kwe.co.jp/",
        "official_domains": ["kwe.co.jp"],
        "urls": ["https://www.kwe.co.jp/news/", "https://www.kwe.co.jp/"],
        "query": '"近鉄エクスプレス"',
    },
    "kintetsu-dept": {
        "id": "kintetsu-dept", "name": "近鉄百貨店", "top_url": "https://www.d-kintetsu.co.jp/",
        "official_domains": ["d-kintetsu.co.jp"],
        "urls": ["https://www.d-kintetsu.co.jp/corporate/ir/whatsnew.html", "https://www.d-kintetsu.co.jp/corporate/", "https://www.d-kintetsu.co.jp/"],
        "query": '"近鉄百貨店"',
    },
    "kintetsu-retailing": {
        "id": "kintetsu-retailing", "name": "近鉄リテーリング", "top_url": "https://knt-rt.co.jp/",
        "official_domains": ["knt-rt.co.jp"],
        "urls": ["https://knt-rt.co.jp/news/", "https://knt-rt.co.jp/"],
        "query": '"近鉄リテーリング"',
    },
    "kinsho-store": {
        "id": "kinsho-store", "name": "近商ストア", "top_url": "https://www.kinshostore.co.jp/",
        "official_domains": ["kinsho-store.co.jp", "kinshostore.co.jp"],
        "urls": ["https://www.kinshostore.co.jp/html/news.php", "https://www.kinsho-store.co.jp/html/news.php", "https://www.kinshostore.co.jp/"],
        "query": '"近商ストア"',
    },
    # ★ 近鉄・都ホテルズ（正規URL: pressrelease/）
    "miyako-hotels": {
        "id": "miyako-hotels", "name": "近鉄・都ホテルズ", "top_url": "https://www.miyakohotels.ne.jp/pressrelease/",
        "official_domains": ["miyakohotels.ne.jp"],
        "urls": ["https://www.miyakohotels.ne.jp/pressrelease/", "https://www.miyakohotels.ne.jp/"],
        "query": '"近鉄・都ホテルズ" OR "都ホテルズ＆リゾーツ" OR "都ホテル"',
    },
    "knt-ct": {
        "id": "knt-ct", "name": "KNT-CTホールディングス", "top_url": "https://www.kntcthd.co.jp/news/",
        "official_domains": ["kntcthd.co.jp"],
        "urls": [
            "https://www.kntcthd.co.jp/news/",
            "https://www.kntcthd.co.jp/release/",
            "https://www.kntcthd.co.jp/",
        ],
        "query": '"KNT-CTホールディングス" OR "KNT-CT"',
    },
    "knt": {
        "id": "knt", "name": "近畿日本ツーリスト", "top_url": "https://corp.knt.co.jp/",
        "official_domains": ["knt.co.jp"],
        "urls": ["https://corp.knt.co.jp/ja/release/", "https://corp.knt.co.jp/", "https://www.knt.co.jp/"],
        "query": '"近畿日本ツーリスト"',
    },
    # ★ クラブツーリズム（旅行サイト公式ニュースリリース）
    "club-tourism": {
        "id": "club-tourism", "name": "クラブツーリズム", "top_url": "https://www.club-t.com/",
        "official_domains": ["club-t.com", "club-tourism.co.jp"],
        "urls": ["https://www.club-t.com/ct/news/", "https://www.club-tourism.co.jp/jpn/press/"],
        "query": '"クラブツーリズム"',
    },
    "shima-spain-village": {
        "id": "shima-spain-village", "name": "志摩スペイン村", "top_url": "https://parque-net.com/",
        "official_domains": ["parque-net.com"],
        "urls": ["https://www.parque-net.com/press/", "https://www.parque-net.com/blog/?cat=7"],
        "query": '"志摩スペイン村" OR "パルケエスパーニャ"',
    },
    # ★ 近鉄バス（トピックス各タブ巡回）
    "kintetsu-bus": {
        "id": "kintetsu-bus", "name": "近鉄バス", "top_url": "https://www.kintetsu-bus.co.jp/news/",
        "official_domains": ["kintetsu-bus.co.jp"],
        "urls": ["https://www.kintetsu-bus.co.jp/news/", "https://www.kintetsu-bus.co.jp/topics/"],
        "query": '"近鉄バス"',
    },
    "nara-kotsu": {
        "id": "nara-kotsu", "name": "奈良交通", "top_url": "https://www.narakotsu.co.jp/",
        "official_domains": ["narakotsu.co.jp"],
        "urls": ["https://www.narakotsu.co.jp/news/category/press/", "https://www.narakotsu.co.jp/news/"],
        "query": '"奈良交通"',
    },
    "sanco-hd": {
        "id": "sanco-hd", "name": "三交ホールディングス", "top_url": "https://holdings.sanco.co.jp/",
        "official_domains": ["holdings.sanco.co.jp", "sanco.co.jp"],
        "urls": ["https://holdings.sanco.co.jp/news/", "https://holdings.sanco.co.jp/", "https://www.sanco.co.jp/allnews/"],
        "query": '"三交ホールディングス" OR "三重交通グループホールディングス"',
    },
    "sanco": {
        "id": "sanco", "name": "三重交通", "top_url": "https://www.sanco.co.jp/",
        "official_domains": ["sanco.co.jp"],
        "urls": ["https://www.sanco.co.jp/allnews/", "https://www.sanco.co.jp/other/newsrelease/", "https://www.sanco.co.jp/"],
        "query": '"三重交通"',
    },
}

JR_ORDER = ["jr-hokkaido", "jr-east", "jr-central", "jr-west", "jr-shikoku", "jr-kyushu"]

PRIVATE_ORDER = [
    "tobu", "seibu", "keisei", "keio", "odakyu",
    "tokyu", "keikyu", "sotetsu", "meitetsu",
    "kintetsu-ghd", "kintetsu-railway",
    "nankai", "keihan", "hanshin", "hankyu", "hankyu-hanshin-hd", "nishitetsu"
]

KINTETSU_ORDER = [
    "kintetsu-ghd", "kintetsu-railway", "kintetsu-fudosan", "abeno-art-museum",
    "kwe", "kintetsu-dept", "kintetsu-retailing", "kinsho-store", "miyako-hotels",
    "knt-ct", "knt", "club-tourism", "shima-spain-village", "kintetsu-bus",
    "nara-kotsu", "sanco-hd", "sanco"
]

zen_to_han = str.maketrans("０１２３４５６７８９", "0123456789")

# ==========================================
# 2. 自動エンコーディング解析＆日付抽出ユーティリティ
# ==========================================
def decode_html_bytes(raw_bytes, url=""):
    enc_candidates = []
    if any(d in url for d in ["westjr.co.jp", "kintetsu", "nankai.co.jp", "hanshin.co.jp", "hankyu.co.jp", "keihan.co.jp", "jr-central.co.jp", "knt-rt.co.jp", "kinsho", "sanco"]):
        enc_candidates.extend(["cp932", "shift_jis"])

    m = re.search(rb'<meta[^>]+charset=["\']?\s*([a-zA-Z0-9_\-]+)', raw_bytes[:8192], re.IGNORECASE)
    if not m:
        m = re.search(rb'charset\s*=\s*["\']?\s*([a-zA-Z0-9_\-]+)', raw_bytes[:8192], re.IGNORECASE)
    if m:
        detected = m.group(1).decode("ascii", errors="ignore").lower()
        if detected in ["shift_jis", "sjis", "shift-jis", "x-sjis", "ms932", "windows-31j"]:
            enc_candidates.append("cp932")
        elif detected in ["euc-jp", "euc_jp", "x-euc-jp"]:
            enc_candidates.append("euc_jp")
        elif detected in ["utf-8", "utf8"]:
            enc_candidates.append("utf-8")
        else:
            enc_candidates.append(detected)

    for default_enc in ["utf-8", "cp932", "euc_jp", "shift_jis"]:
        if default_enc not in enc_candidates:
            enc_candidates.append(default_enc)

    best_decoded = None
    for enc in enc_candidates:
        try:
            text = raw_bytes.decode(enc)
            mojibake_count = len(re.findall(r'[縺繧繝譬諷]', text))
            if mojibake_count == 0:
                return text
            if best_decoded is None:
                best_decoded = text
        except (UnicodeDecodeError, LookupError):
            continue

    return best_decoded if best_decoded else raw_bytes.decode("utf-8", errors="replace")


def parse_date_text(raw_text, current_year):
    if not raw_text:
        return None

    attr_match = re.search(r'(?:datetime|data-date)=["\']((?:19|20)\d{2}[-/\.][0-9]{1,2}[-/\.][0-9]{1,2})', raw_text, re.IGNORECASE)
    if attr_match:
        try:
            parts = [int(p) for p in re.split(r'[-/\.]', attr_match.group(1))]
            return datetime.date(parts[0], parts[1], parts[2])
        except Exception:
            pass

    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = text.translate(zen_to_han)

    m_seireki = re.search(r"((?:19|20)\d{2})\s*[年\./\-]\s*([0-9]{1,2})\s*[月\./\-]\s*([0-9]{1,2})\s*日?", text)
    if m_seireki:
        try:
            return datetime.date(int(m_seireki.group(1)), int(m_seireki.group(2)), int(m_seireki.group(3)))
        except ValueError:
            pass

    m_reiwa = re.search(r"令和\s*([0-9]+|元)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日", text)
    if m_reiwa:
        y_val = 1 if m_reiwa.group(1) == "元" else int(m_reiwa.group(1))
        try:
            return datetime.date(2018 + y_val, int(m_reiwa.group(2)), int(m_reiwa.group(3)))
        except ValueError:
            pass

    if not re.search(r"(?:19|20)\d{2}", text):
        m_md = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*[月\./\-]\s*(3[01]|[12][0-9]|0?[1-9])\s*日?(?!\d)", text)
        if m_md:
            try:
                return datetime.date(current_year, int(m_md.group(1)), int(m_md.group(2)))
            except ValueError:
                pass

    return None


def clean_title_advanced(raw_title, company_info):
    """タイトルをサニタイズ（日付・ジャンル・残骸・PDFサイズを徹底除去）"""
    t = re.sub(r"<[^>]*>", " ", raw_title)
    t = html.unescape(t)
    t = re.sub(r'\s+', ' ', t).strip()

    cid = company_info.get("id", "")

    # ★ クラブツーリズム専用サニタイズ（「メディア」「国内」「クルーズ」「キャンペーン」等を削除）
    if cid == "club-tourism":
        ct_genres = ["メディア", "国内", "クルーズ", "キャンペーン", "海外", "バス", "ツアー", "お知らせ", "ニュース"]
        for _ in range(3):
            for g in ct_genres:
                t = re.sub(r'^[【\[（\(]' + g + r'[】\]）\)]\s*', '', t)
                t = re.sub(r'^' + g + r'\s+[:：|｜・\s\-]*', '', t)
                t = re.sub(r'^' + g + r'[:：|｜・\-]\s*', '', t)

    # 1. 末尾の [PDF: 1.6MB] や [PDF] などを除去
    t = re.sub(r'[\[［【\(（]\s*(?:PDF\s*[:：]?\s*)?[0-9\.]+\s*(?:[KMG]B|キロバイト|メガバイト)\s*[\]］】\)）]\s*$', '', t, flags=re.I)
    t = re.sub(r'[\[［【\(（]\s*PDF\s*[\]］】\)）]\s*$', '', t, flags=re.I)
    t = re.sub(r'\.pdf\s*$', '', t, flags=re.I)

    # 2. 英語日付の除去
    t = re.sub(r'^(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+(?:19|20)\d{2}\s*[:：|｜・\s\-]*', '', t, flags=re.I)

    # 3. 日本語日付・西暦・元号の除去（タイトル先頭）
    t = re.sub(r'^(?:(?:19|20)\d{2}[年\.\/\-]\s*\d{1,2}[月\.\/\-]\s*\d{1,2}日?)\s*[:：|｜・\s\-]*', '', t)
    t = re.sub(r'^(?:(?:令和|平成)\s*(?:\d+|元)年\s*\d{1,2}月\s*\d{1,2}日)\s*[:：|｜・\s\-]*', '', t)
    t = re.sub(r'^[\[【(](?:(?:19|20)\d{2}[年\.\/\-]\s*\d{1,2}[月\.\/\-]\s*\d{1,2}日?)[\]】)]\s*', '', t)

    # 4. JR九州のようなナビゲーション残骸の除去
    t = re.sub(r'^.*?11月\s*12月\s*(?:(?:19|20)\d{2}年\d{1,2}月\d{1,2}日)?\s*', '', t)
    t = re.sub(r'^(?:新着情報|ニュースリリース|お知らせ|イベント情報|IR情報|プレスリリース)\s*', '', t)

    # 5. ジャンル・特定会社表記の除去
    t = re.sub(r'^流通\s+(?:㈱|株式会社)?京阪流通システムズ\s+', '', t)
    t = re.sub(r'^(?:建設|運輸サービス|運輸|バス|電車|鉄道|流通|不動産|ホテル|レジャー|リテール|グループ|その他)\s*', '', t)

    # 6. 相鉄の欠損年修復
    t = re.sub(r'^026年', '2026年', t)

    # 7. 各社専用クレンジング
    if cid == "kinsho-store":
        t = re.sub(r'(?:NEW|新着|お知らせ|重要|\.pdf|\.PDF)+', '', t).strip()
        t = re.sub(r'^[【\[（\(].*?[】\]）\)]', '', t).strip()
        t = re.sub(r'^[a-zA-Z0-9_\-]+["\']?>', '', t).strip()

    if cid in ["sanco-hd", "sanco"]:
        t = re.sub(r'(?:グループニュース|IRニュース|お知らせ|ニュースリリース)+', '', t).strip()
        t = re.sub(r'#448073;padding:[^;]*;', '', t).strip()

    if cid in ["knt-ct", "knt"]:
        if any(w in t for w in ["特集", "発売中", "旅行代金", "ツアー一覧"]):
            return ""

    t = re.sub(r"\s+", " ", t).strip()

    t_lower = t.lower()
    if t_lower in NAV_EXCLUDE_WORDS or any(w == t for w in NAV_EXCLUDE_WORDS):
        return ""
    if len(t) < 5:
        return ""

    return t


def clean_news_summary(summary, title, company_name):
    clean = re.sub(r"<[^>]+>", " ", summary)
    clean = html.unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    noise_terms = [
        "招待券", "プレゼント", "懸賞", "合唱団", "定期演奏会",
        "【新機能】", "writevideo", "プレスリリース *",
        "tel：", "年中無休", "お問合せ 一般のお客様", "お問い合わせ先", "チケット"
    ]
    if any(ng in clean.lower() for ng in noise_terms):
        return f"{company_name}に関する最新の報道・ニュースです。詳細は掲載ページをご確認ください。"

    clean = re.sub(r'[\d\s\.\»\«\>]+最新のニュース.*', '', clean)
    clean = clean.strip()

    if len(clean) < 15 or clean == title:
        return f"{company_name}に関する最新の報道・ニュースです。詳細は掲載ページをご確認ください。"

    return clean[:140] + ("..." if len(clean) > 140 else "")


# ==========================================
# 2-B. ★ 記事内容の自動分類タグ判定エンジン
# ==========================================
def classify_article_advanced(title, summary=""):
    """記事のタイトルと要約から適切な分類タグを判定"""
    text = (title + " " + summary).lower()

    # 1. 車両・運行 (新型車両、列車事故、ダイヤ、運休など)
    if any(w in text for w in ["新型車両", "新車", "引退", "ラストラン", "ダイヤ", "運行", "運転", "特急", "新幹線", "自動運転", "ato", "運休", "遅延", "事故", "脱線", "見合わせ", "運転見合わせ", "故障", "トラブル", "踏切", "安全確認", "振替", "車両"]):
        return ("車両・運行", "#0284c7", "#e0f2fe", "#7dd3fc")

    # 2. 経済 (会社の業績、赤字路線、決算、セール等)
    if any(w in text for w in ["業績", "決算", "赤字", "赤字路線", "黒字", "増益", "減益", "純利益", "売上", "収支", "存廃", "運賃改定", "値上げ", "セール", "優勝セール", "記念セール", "株価", "投資", "配当", "下方修正", "上方修正", "最高益", "経済", "インバウンド"]):
        return ("経済", "#b45309", "#fef3c7", "#fcd34d")

    # 3. イベント (鉄道まつり、見学会、キャンペーンなど)
    if any(w in text for w in ["鉄道まつり", "見学会", "撮影会", "イベント", "まつり", "フェス", "スタンプラリー", "キャンペーン", "体験", "記念", "ツアー", "グッズ", "限定", "企画", "フェア", "マルシェ", "展示"]):
        return ("イベント", "#be185d", "#fce7f3", "#f472b6")

    # 4. 経営 (子会社、再編、人事、戦略など)
    if any(w in text for w in ["子会社", "再編", "提携", "買収", "事業承継", "人事", "役員", "経営", "戦略", "社長", "就任", "撤退", "設立", "資本業務提携", "グループhd", "ホールディングス"]):
        return ("経営", "#4338ca", "#e0e7ff", "#a5b4fc")

    # 5. 地域 (まちづくり、再開発、新駅など)
    if any(w in text for w in ["まちづくり", "再開発", "新駅", "地域", "自治体", "沿線", "駅前", "商業施設", "協定", "連携", "包括連携", "オープン", "開業", "リニューアル", "新店舗"]):
        return ("地域", "#047857", "#d1fae5", "#6ee7b7")

    # 6. 安全・技術
    if any(w in text for w in ["安全", "訓練", "点検", "防災", "技術", "dx", "ai", "システム", "保守", "実証実験"]):
        return ("安全・技術", "#334155", "#f1f5f9", "#94a3b8")

    return ("一般", "#475569", "#f8fafc", "#cbd5e1")


# ==========================================
# 2-C. ★ 野球チーム除外フィルター（優勝セール等は経済として残す）
# ==========================================
def is_baseball_noise(title, desc=""):
    text = (title + " " + desc).lower()

    baseball_terms = [
        "タイガース", "バファローズ", "南海ホークス", "ホークス", "阪急ブレーブス",
        "プロ野球", "ドラフト", "クライマックスシリーズ", "日本シリーズ", "セ・リーグ", "パ・リーグ",
        "甲子園球場", "打線", "ホームラン", "完封", "サヨナラ勝ち", "先発投手"
    ]
    
    # 商業・経済関連のキーワードがあれば除外しない
    keep_terms = [
        "セール", "優勝セール", "記念セール", "応援セール", "特売", "経済効果", "百貨店", "売上", "消費", "商業"
    ]

    has_baseball = any(term in text for term in baseball_terms)
    if has_baseball:
        has_keep = any(k in text for k in keep_terms)
        if not has_keep:
            return True  # 野球単体の記事なので除外

    return False


# ==========================================
# 3. HTTP通信ユーティリティ
# ==========================================
@st.cache_resource
def get_advanced_http_opener():
    cookie_jar = http.cookiejar.CookieJar()
    ctx = ssl._create_unverified_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar),
        urllib.request.HTTPSHandler(context=ctx)
    )
    return opener

def fetch_url_html(url, referer, headers, ctx):
    try:
        opener = get_advanced_http_opener()
        h = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ja,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        if referer:
            h["Referer"] = referer
        else:
            p = urllib.parse.urlparse(url)
            h["Referer"] = f"{p.scheme}://{p.netloc}/"

        req = urllib.request.Request(url, headers=h)
        with opener.open(req, timeout=9) as res:
            raw_bytes = res.read()
            content_encoding = res.headers.get("Content-Encoding", "").lower()
            final_url = res.geturl()

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

        html_text = decode_html_bytes(raw_bytes, url=final_url)
        return html_text, final_url, "OK"
    except urllib.error.HTTPError as he:
        return "", url, f"HTTP {he.code}"
    except Exception as e:
        return "", url, str(e)


# ==========================================
# 4. ★ PR TIMES専用リリース取得エンジン（JR東日本・近鉄GHD・近鉄・阪急対応）
# ==========================================
def fetch_prtimes_releases(prtimes_url, company_info, cutoff_date, today, current_year):
    """PR TIMESの公式企業リリース一覧から見出し・内容・直リンクを100%確実に取得"""
    results = []
    seen = set()
    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,ja-JP;q=0.9,en;q=0.8",
    }
    try:
        req = urllib.request.Request(prtimes_url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as res:
            raw_bytes = res.read()
            html_text = decode_html_bytes(raw_bytes, url=prtimes_url)

        for block in re.findall(r'<(?:article|div)[^>]*class=["\'][^"\']*(?:item|list-article__item)[^"\']*["\'][^>]*>(.*?)</(?:article|div)>', html_text, re.DOTALL | re.IGNORECASE):
            m_time = re.search(r'datetime=["\']((?:19|20)\d{2}[-/\.][0-9]{1,2}[-/\.][0-9]{1,2})', block)
            d_val = None
            if m_time:
                parts = [int(p) for p in re.split(r'[-/\.]', m_time.group(1))]
                d_val = datetime.date(parts[0], parts[1], parts[2])
            else:
                m_txt = re.search(r'((?:19|20)\d{2})\s*[年\./\-]\s*([0-9]{1,2})\s*[月\./\-]\s*([0-9]{1,2})', block)
                if m_txt:
                    d_val = datetime.date(int(m_txt.group(1)), int(m_txt.group(2)), int(m_txt.group(3)))

            if not d_val or not (cutoff_date <= d_val <= today):
                continue

            m_title_a = re.search(r'<h[2-4][^>]*>\s*<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>\s*</h[2-4]>', block, re.DOTALL | re.IGNORECASE)
            if not m_title_a:
                m_title_a = re.search(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, re.DOTALL | re.IGNORECASE)
            if not m_title_a:
                continue

            href = m_title_a.group(1).strip()
            full_url = urllib.parse.urljoin("https://prtimes.jp", href)
            if full_url in seen:
                continue

            raw_title = m_title_a.group(2)
            title = re.sub(r'<[^>]+>', ' ', raw_title).strip()
            title = html.unescape(title)
            title = re.sub(r'\s+', ' ', title)

            m_desc = re.search(r'<p[^>]*class=["\']?[^"\'>]*(?:description|lead|text)[^"\'>]*["\']?[^>]*>(.*?)</p>', block, re.DOTALL | re.IGNORECASE)
            summary = ""
            if m_desc:
                summary = re.sub(r'<[^>]+>', ' ', m_desc.group(1)).strip()
                summary = html.unescape(summary)
                summary = re.sub(r'\s+', ' ', summary)
            if not summary or len(summary) < 10:
                summary = f"{company_info['name']}の公式プレスリリースです。詳細は掲載ページをご確認ください。"

            clean_t = clean_title_advanced(title, company_info)
            if len(clean_t) >= 5:
                seen.add(full_url)
                tag_info = classify_article_advanced(clean_t, summary)
                results.append({
                    "date": d_val,
                    "type": "公式発表",
                    "title": clean_t[:130],
                    "summary": summary[:140] + ("..." if len(summary) > 140 else ""),
                    "url": full_url,
                    "pdf_url": None,
                    "source": company_info["name"] + " 公式 (PR TIMES)",
                    "is_pdf": False,
                    "tag_info": tag_info,
                })
    except Exception:
        pass
    return results


# ==========================================
# 4-B. 公式発表パーサー（ブロック構造解析エンジン）
# ==========================================
def parse_official_releases_universal(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls):
    results = []
    allowed_domains = company_info.get("official_domains", [])
    cid = company_info["id"]
    is_jr_east = company_info.get("is_jr_east", False)

    # 1. RSS/Atom フィード（最優先解析）
    if "<rss" in html_text or "<feed" in html_text or "<rdf:RDF" in html_text:
        for item_xml in re.findall(r"<(?:item|entry)>(.*?)</(?:item|entry)>", html_text, flags=re.DOTALL):
            t_m = re.search(r"<title>(.*?)</title>", item_xml, flags=re.DOTALL)
            l_m = re.search(r"<link(?:>|\s+[^>]*?href=[\"']([^\"']+)[\"'])", item_xml, flags=re.DOTALL)
            d_m = re.search(r"<(?:pubDate|dc:date|updated)>(.*?)</(?:pubDate|dc:date|updated)>", item_xml, flags=re.DOTALL)
            if t_m and l_m:
                t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t_m.group(1)).strip()
                l = l_m.group(1).strip() if l_m.group(1) else re.search(r"<link>(.*?)</link>", item_xml, flags=re.DOTALL).group(1).strip()
                l = urllib.parse.urljoin(base_url, l)
                d_str = d_m.group(1) if d_m else ""
                item_date = parse_date_text(d_str, current_year)
                if item_date and (cutoff_date <= item_date <= today) and l not in seen_urls:
                    clean_t = clean_title_advanced(t, company_info)
                    if clean_t:
                        seen_urls.add(l)
                        tag_info = classify_article_advanced(clean_t, "")
                        results.append({
                            "date": item_date,
                            "type": "公式発表",
                            "title": clean_t,
                            "url": l,
                            "pdf_url": l if l.lower().split('?')[0].endswith(".pdf") else None,
                            "source": company_info["name"] + " 公式HP",
                            "is_pdf": l.lower().split('?')[0].endswith(".pdf"),
                            "tag_info": tag_info,
                        })
        if results:
            return results

    clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<svg.*?>.*?</svg>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<header.*?>.*?</header>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<footer.*?>.*?</footer>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    if cid == "tokyu":
        clean_html = re.sub(r'<form.*?>.*?</form>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)

    # ブロック構造解析（li, tr, dl, article）
    container_patterns = [
        r'<li[^>]*>(.*?)</li>',
        r'<tr[^>]*>(.*?)</tr>',
        r'<dl[^>]*>(.*?)</dl>',
        r'<article[^>]*>(.*?)</article>',
    ]

    for pat in container_patterns:
        for block in re.findall(pat, clean_html, flags=re.DOTALL | re.IGNORECASE):
            d_val = parse_date_text(block, current_year)
            if not d_val or not (cutoff_date <= d_val <= today):
                continue

            for a_m in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, flags=re.DOTALL | re.IGNORECASE):
                href = a_m.group(1).strip().replace(" ", "")
                if not href or href.startswith(('javascript:', '#', 'mailto:', 'tel:')):
                    continue

                full_url = urllib.parse.urljoin(base_url, href)
                if full_url in seen_urls:
                    continue

                if not is_jr_east:
                    parsed_u = urllib.parse.urlparse(full_url)
                    if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
                        continue

                clean_t = clean_title_advanced(a_m.group(2), company_info)
                if not clean_t or len(clean_t) < 5 or clean_t.lower() in ["pdf", "詳細", "こちら", "詳しくはこちら"]:
                    block_clean = re.sub(r'<[^>]+>', ' ', block)
                    clean_t = clean_title_advanced(block_clean, company_info)

                if clean_t and len(clean_t) >= 5:
                    seen_urls.add(full_url)
                    is_pdf = full_url.lower().split('?')[0].endswith(".pdf")
                    tag_info = classify_article_advanced(clean_t, "")
                    results.append({
                        "date": d_val,
                        "type": "公式発表",
                        "title": clean_t[:130],
                        "url": full_url,
                        "pdf_url": full_url if is_pdf else None,
                        "source": company_info["name"] + " 公式発表",
                        "is_pdf": is_pdf,
                        "tag_info": tag_info,
                    })

    return results


# ==========================================
# 5. 公式発表 取得ディスパッチャー（PR TIMES完全連携）
# ==========================================
def fetch_official_releases(company_info, max_days_back=21):
    results = []
    seen_urls = set()
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)
    current_year = today.year
    cid = company_info["id"]

    ctx = ssl._create_unverified_context()
    log_entry = {
        "tried_urls": [],
        "success_count": 0,
        "status": "INIT"
    }

    # ★ PR TIMES直接取得（JR東日本、近鉄GHD、近鉄、阪急電鉄等）
    if "prtimes_url" in company_info:
        pr_items = fetch_prtimes_releases(company_info["prtimes_url"], company_info, cutoff_date, today, current_year)
        results.extend(pr_items)
        for it in pr_items:
            seen_urls.add(it["url"])
        log_entry["tried_urls"].append(f"PRTIMES: {company_info['prtimes_url']} -> [{len(pr_items)}件取得]")

    # 通常サイト巡回
    has_403 = False
    for url in company_info["urls"]:
        if "prtimes.jp" in url:
            continue
        html_text, final_url, status = fetch_url_html(url, company_info.get("top_url", url), {}, ctx)
        log_entry["tried_urls"].append(f"{url} -> [{status}]")
        if "403" in status:
            has_403 = True

        if html_text:
            items = parse_official_releases_universal(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)
            results.extend(items)
            if results:
                break

    # JR東日本 救済バイパス
    if cid == "jr-east" and (not results or has_403):
        rescue_q = "site:jreast.co.jp/press"
        encoded_q = urllib.parse.quote(rescue_q)
        rescue_rss = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&mkt=ja-JP"
        try:
            req = urllib.request.Request(rescue_rss, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            })
            with urllib.request.urlopen(req, context=ctx, timeout=6) as r_res:
                x_data = r_res.read()
                if x_data[:2] == b"\x1f\x8b":
                    x_data = gzip.decompress(x_data)
                root = ET.fromstring(x_data)
                for item in root.findall(".//item"):
                    t_el = item.find("title")
                    l_el = item.find("link")
                    d_el = item.find("pubDate")
                    if t_el is None or l_el is None:
                        continue
                    l = (l_el.text or "").strip()
                    if "bing.com" in l:
                        u_match = re.search(r'[?&]u=a1([a-zA-Z0-9_\-]+)', l)
                        if u_match:
                            try:
                                b64_str = u_match.group(1) + '=' * (-len(u_match.group(1)) % 4)
                                l = base64.urlsafe_b64decode(b64_str).decode('utf-8', errors='ignore')
                            except Exception:
                                pass

                    if "jreast.co.jp" not in l or l in seen_urls:
                        continue

                    i_date = None
                    if d_el is not None and d_el.text:
                        try:
                            dt = email.utils.parsedate_to_datetime(d_el.text).astimezone(JST)
                            i_date = dt.date()
                        except Exception:
                            pass

                    if i_date and (cutoff_date <= i_date <= today):
                        clean_t = clean_title_advanced(t_el.text or "", company_info)
                        if not clean_t:
                            continue
                        seen_urls.add(l)
                        is_pdf = l.lower().split('?')[0].endswith(".pdf")
                        tag_info = classify_article_advanced(clean_t, "")
                        results.append({
                            "date": i_date,
                            "type": "公式発表",
                            "title": clean_t,
                            "url": l,
                            "pdf_url": l if is_pdf else None,
                            "source": "JR東日本 公式発表",
                            "is_pdf": is_pdf,
                            "tag_info": tag_info,
                        })
            log_entry["tried_urls"].append(f"JR-East Rescue Route: {len(results)}件取得")
        except Exception as e:
            log_entry["tried_urls"].append(f"JR-East Rescue Error: {e}")

    log_entry["success_count"] = len(results)
    log_entry["status"] = "SUCCESS" if results else "ZERO"
    st.session_state.diag_logs[company_info["name"]] = log_entry

    return results


# ==========================================
# 6. 一般ニュース取得エンジン（元サイト直リンク化・有力メディア優先・野球除外）
# ==========================================
def extract_direct_article_url(raw_link):
    """新聞社・メディアの個別記事URLを直接復元（検索窓URLは絶対に作らない）"""
    if not raw_link:
        return ""

    if "bing.com" in raw_link:
        url_match = re.search(r'[?&]url=([^&]+)', raw_link)
        if url_match:
            try:
                decoded = urllib.parse.unquote(url_match.group(1))
                if decoded.startswith("http") and not any(x in decoded for x in ["bing.com", "google.com"]):
                    return decoded
            except Exception:
                pass
        u_match = re.search(r'[?&]u=a1([a-zA-Z0-9_\-]+)', raw_link)
        if u_match:
            try:
                b64_str = u_match.group(1) + '=' * (-len(u_match.group(1)) % 4)
                decoded = base64.urlsafe_b64decode(b64_str).decode('utf-8', errors='ignore')
                if decoded.startswith("http") and not any(x in decoded for x in ["bing.com", "google.com"]):
                    return decoded
            except Exception:
                pass

    if "news.google.com" in raw_link:
        m = re.search(r'(?:articles|read)/([a-zA-Z0-9_\-]+)', raw_link)
        if m:
            try:
                b64_str = m.group(1) + '=' * (-len(m.group(1)) % 4)
                raw = base64.urlsafe_b64decode(b64_str)
                pos = raw.find(b'http')
                if pos != -1:
                    if pos > 0:
                        length = raw[pos - 1]
                        if 10 < length < 250 and (pos + length) <= len(raw):
                            cand = raw[pos : pos + length].decode('utf-8', errors='ignore')
                            if "google.com" not in cand and "." in cand:
                                return cand
                    urls = re.findall(rb'https?://[a-zA-Z0-9_\-\./\?%&=+#~:;@]+', raw)
                    for u in urls:
                        cand = u.decode('utf-8', errors='ignore')
                        cand = re.sub(r'[\x00-\x1f\x7f-\xff]+.*$', '', cand)
                        cand = cand.rstrip('0123456789') if cand.endswith(('0', '1')) and not cand.endswith(('.html', '.htm', '/')) else cand
                        if "google.com" not in cand and "." in cand:
                            return cand
            except Exception:
                pass

    return raw_link


def fetch_general_news(query, company_dict, max_days_back=21):
    """一般ニュース取得（元サイト直リンク・有力メディア優先・野球除外）"""
    results = []
    company_name = company_dict["name"]
    encoded_q = urllib.parse.quote(query)
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)

    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    endpoints = [
        f"https://www.bing.com/news/search?q={encoded_q}&format=rss&mkt=ja-JP",
        f"https://news.google.com/rss/search?q={encoded_q}&hl=ja&gl=JP&ceid=JP:ja"
    ]

    seen_links = set()

    for rss_url in endpoints:
        try:
            req = urllib.request.Request(rss_url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=8) as res:
                xml_data = res.read()
                if xml_data[:2] == b"\x1f\x8b":
                    xml_data = gzip.decompress(xml_data)

            root = ET.fromstring(xml_data)
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el = item.find("link")
                pubdate_el = item.find("pubDate")
                desc_el = item.find("description")

                if title_el is None or link_el is None:
                    continue

                raw_title = title_el.text or ""
                raw_link = (link_el.text or "").strip()
                pubdate_str = pubdate_el.text if pubdate_el is not None else ""
                desc = desc_el.text if desc_el is not None else ""

                if not raw_link:
                    continue

                clean_title = raw_title.strip()
                clean_desc = re.sub(r"<[^>]+>", " ", desc)
                clean_desc = html.unescape(clean_desc)
                clean_desc = re.sub(r"\s+", " ", clean_desc).strip()

                source_name = ""
                source_el = item.find("source")
                if source_el is not None and source_el.text:
                    source_name = source_el.text.strip()

                if not source_name and " - " in clean_title:
                    parts = clean_title.rsplit(" - ", 1)
                    cand = parts[1].strip()
                    clean_title = parts[0].strip()
                    if cand:
                        source_name = cand

                # ★ 個別記事そのもののURLを直接復元（検索窓URLは絶対に作らない）
                real_link = extract_direct_article_url(raw_link)
                if not real_link:
                    real_link = raw_link

                if real_link in seen_links:
                    continue

                item_date = None
                if pubdate_str:
                    try:
                        dt = email.utils.parsedate_to_datetime(pubdate_str)
                        jst = dt.astimezone(JST)
                        item_date = jst.date()
                    except Exception:
                        pass

                if not item_date or not (cutoff_date <= item_date <= today):
                    continue

                combined_text = (clean_title + " " + clean_desc).lower()

                # ノイズ除外
                noise_keywords = [
                    "招待券", "プレゼント", "懸賞", "合唱団", "定期演奏会",
                    "警察weekly", "県警weekly", "現行犯逮捕", "酒酔い運転", "ひき逃げ",
                    "安全運転管理者", "死亡事故", "容疑で逮捕", "書類送検"
                ]
                if any(ng in combined_text for ng in noise_keywords):
                    continue

                # ★ 野球チームの内容を削除（優勝セール・経済効果等は残す）
                if is_baseball_noise(clean_title, clean_desc):
                    continue

                # 厳格指定会社のみタイトルチェック
                strict_companies = ["奈良交通", "近鉄バス", "三重交通", "志摩スペイン村", "あべのハルカス美術館"]
                if company_name in strict_companies:
                    if company_name not in clean_title:
                        continue

                seen_links.add(real_link)
                summary = clean_news_summary(clean_desc, clean_title, company_name)

                parsed_url = urllib.parse.urlparse(real_link)
                domain = parsed_url.netloc.lower().replace("www.", "")

                for domain_key, media_label in MEDIA_NAME_MAP.items():
                    if domain_key in domain:
                        source_name = media_label
                        break

                if not source_name or source_name.lower() in ["bing", "google"]:
                    source_name = domain if domain else "ニュース報道"

                priority = MEDIA_PRIORITY.get(source_name, 10)
                tag_info = classify_article_advanced(clean_title, summary)
                is_direct_article = bool(len(parsed_url.path.strip("/")) > 4 and "google.com" not in parsed_url.netloc)

                results.append({
                    "date": item_date,
                    "type": "ニュース（一般サイト）",
                    "title": clean_title,
                    "summary": summary,
                    "url": real_link,
                    "pdf_url": None,
                    "source": source_name,
                    "is_pdf": False,
                    "priority": priority,
                    "is_direct_article": is_direct_article,
                    "tag_info": tag_info,
                })
        except Exception:
            pass

    # ★【同一見出しの重複排除（より有力で影響力のあるメディアを最優先）】
    deduped_dict = {}
    for item in results:
        norm_key = re.sub(r'[\s\u3000・―\-―：:【】「」『』\(\)\[\]（）]+', '', item['title']).lower()
        norm_key = re.sub(r'^(?:速報|独自|注目|最新)+', '', norm_key)

        if norm_key in deduped_dict:
            existing = deduped_dict[norm_key]
            if item["priority"] > existing["priority"]:
                deduped_dict[norm_key] = item
            elif item["priority"] == existing["priority"] and item.get("is_direct_article") and not existing.get("is_direct_article"):
                deduped_dict[norm_key] = item
        else:
            deduped_dict[norm_key] = item

    return list(deduped_dict.values())


# ==========================================
# 7. 社別キャッシュエンジン
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_single_company_data(company_dict, max_days_back=21, cache_version="v2026_prtimes_realurl_tag_perfect_v1"):
    official = fetch_official_releases(company_dict, max_days_back=max_days_back)
    general = []
    if "query" in company_dict:
        general = fetch_general_news(company_dict["query"], company_dict, max_days_back=max_days_back)

    combined = list(official)
    seen_urls = {item["url"] for item in official}
    for g in general:
        if g["url"] not in seen_urls:
            seen_urls.add(g["url"])
            combined.append(g)

    return combined


# ==========================================
# 8. アプリ全体のボタンスタイル定義（濃紺 #1e3a8a 統一）
# ==========================================
st.markdown(
    """
    <style>
    button[kind="primary"],
    button[data-testid="baseButton-primary"],
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #1e3a8a !important;
        border-color: #1e3a8a !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        box-shadow: 0 1px 3px rgba(30, 58, 138, 0.3) !important;
    }
    button[kind="primary"]:hover,
    button[data-testid="baseButton-primary"]:hover,
    div[data-testid="stButton"] button[kind="primary"]:hover {
        background-color: #172554 !important;
        border-color: #172554 !important;
        color: #ffffff !important;
    }
    button[kind="secondary"],
    button[data-testid="baseButton-secondary"],
    div[data-testid="stButton"] button[kind="secondary"],
    section[data-testid="stSidebar"] button[kind="secondary"] {
        background-color: #f1f5f9 !important;
        color: #64748b !important;
        border: 1px solid #cbd5e1 !important;
        font-weight: 500 !important;
    }
    button[kind="secondary"]:hover,
    button[data-testid="baseButton-secondary"]:hover,
    div[data-testid="stButton"] button[kind="secondary"]:hover,
    section[data-testid="stSidebar"] button[kind="secondary"]:hover {
        background-color: #e2e8f0 !important;
        color: #1e293b !important;
        border-color: #94a3b8 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] button {
        padding: 5px 8px !important;
        font-size: 0.86em !important;
        white-space: nowrap !important;
    }
    input[type="radio"] {
        accent-color: #1e3a8a !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# 9. サイドバー操作パネル（完全排他ボタンスイッチ仕様）
# ==========================================
with st.sidebar:
    st.header("⚙️ 設定")

    # --- 1. 表示モード切り替え（ご指定通りの完全排他スイッチ：初期は公式のみ青色） ---
    st.write("**1. 表示モード切り替え**")
    is_official_mode = (st.session_state.view_mode == "official")
    btn_type_off = "primary" if is_official_mode else "secondary"
    btn_type_news = "secondary" if is_official_mode else "primary"

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        if st.button("📢 公式発表", key="btn_mode_official", type=btn_type_off, use_container_width=True):
            st.session_state.view_mode = "official"
            st.rerun()
    with col_m2:
        if st.button("📰 ニュース", key="btn_mode_news", type=btn_type_news, use_container_width=True):
            st.session_state.view_mode = "news"
            st.rerun()

    st.markdown("---")

    # --- 2. 対象期間（３日間／７日間 ＆ カレンダー入力） ---
    st.write("**2. 対象期間**")
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        type_p3 = "primary" if st.session_state.period_days == 3 else "secondary"
        if st.button("📅 3日間", key="btn_p_3", type=type_p3, use_container_width=True):
            st.session_state.period_days = 3
            st.session_state.custom_date_range = (today - datetime.timedelta(days=2), today)
            st.rerun()
    with p_col2:
        type_p7 = "primary" if st.session_state.period_days == 7 else "secondary"
        if st.button("📅 7日間", key="btn_p_7", type=type_p7, use_container_width=True):
            st.session_state.period_days = 7
            st.session_state.custom_date_range = (today - datetime.timedelta(days=6), today)
            st.rerun()

    date_val = st.date_input(
        "📅 カレンダーで任意指定",
        value=st.session_state.custom_date_range,
        max_value=today,
    )
    if isinstance(date_val, (tuple, list)) and len(date_val) == 2:
        start_date, end_date = date_val
        st.session_state.custom_date_range = (start_date, end_date)
    elif isinstance(date_val, (tuple, list)) and len(date_val) == 1:
        start_date = end_date = date_val[0]
        st.session_state.custom_date_range = (start_date, end_date)
    else:
        start_date = end_date = date_val
        st.session_state.custom_date_range = (start_date, end_date)

    diff_days = (end_date - start_date).days + 1
    st.caption(f"📅 選択中: **{start_date.strftime('%Y/%m/%d')} 〜 {end_date.strftime('%Y/%m/%d')}** ({diff_days}日間)")

    if st.session_state.hidden_companies:
        if st.button("👁️ すべての会社の記事を再表示", use_container_width=True):
            st.session_state.hidden_companies.clear()
            st.rerun()

    st.markdown("---")
    st.write("**3. データ更新**")
    st.caption("※サーバー負荷軽減のため、取得結果は1時間自動記憶されます。")
    if st.button("🔄 キャッシュを破棄して最新取得", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_fetch_time = datetime.datetime.now(JST)
        st.rerun()

    with st.expander("🔍 巡回診断ログ（検証・監視）"):
        if st.session_state.diag_logs:
            for cname, log in st.session_state.diag_logs.items():
                icon = "🟢" if log["status"] == "SUCCESS" else "🔴"
                st.write(f"**{icon} {cname}** - 公式取得: {log['success_count']}件")
                for u in log["tried_urls"]:
                    st.caption(f"・{u}")
        else:
            st.caption("巡回完了後にログが表示されます。")

    st.markdown("---")
    st.caption(
        "**【免責事項】**\n"
        "本サイトは公開情報を自動収集・整理して表示する個人開発ツールです。各鉄道会社および関連企業とは一切関係ありません。情報の完全性・正確性を保証するものではありません。"
    )
    st.caption(
        "**【お問い合わせ】**\n"
        "近鉄グループホールディングス デジタル戦略部 中谷\n"
        "(h5-nakatani@rw.kintetsu.co.jp)"
    )

# ==========================================
# 10. データ巡回・取得実行
# ==========================================
unique_company_keys = list(COMPANY_POOL.keys())
total_comps = len(unique_company_keys)
all_cached_data = {}

progress_placeholder = st.empty()

for i, key in enumerate(unique_company_keys):
    comp = COMPANY_POOL[key]
    percent = int(((i + 1) / total_comps) * 100)
    with progress_placeholder.container():
        st.markdown(
            f"""
            <div style="background-color: rgba(30, 58, 138, 0.08); padding: 10px 16px; border-radius: 8px; border: 1px solid rgba(30, 58, 138, 0.3); margin-bottom: 8px;">
                <div style="font-size: 0.95em; font-weight: 700; color: #1e3a8a; margin-bottom: 4px;">
                    🔄 最新データを巡回確認中: {i+1} / {total_comps} 社 ({percent}%)
                </div>
                <div style="font-size: 0.85em; color: #475569;">
                    現在確認中: <b>🏢 {comp['name']}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress((i + 1) / total_comps)

    items = get_single_company_data(comp, max_days_back=21)
    all_cached_data[comp["name"]] = items

progress_placeholder.empty()

if "last_fetch_time" not in st.session_state:
    st.session_state.last_fetch_time = datetime.datetime.now(JST)

st.caption(f"🕒 最終巡回時刻: {st.session_state.last_fetch_time.strftime('%Y-%m-%d %H:%M:%S')} (日本時間) （1時間ごとに自動再巡回）")

jr_list = [COMPANY_POOL[cid] for cid in JR_ORDER]
private_list = [COMPANY_POOL[cid] for cid in PRIVATE_ORDER]
kintetsu_list = [COMPANY_POOL[cid] for cid in KINTETSU_ORDER]

render_groups = [
    ("jr", "JR", jr_list),
    ("private", "私鉄", private_list),
    ("kintetsu", "近鉄グループ", kintetsu_list),
]

# ==========================================
# 11. 会社選択ナビゲーションフォーム（青色維持）
# ==========================================
st.markdown("<div id='sec-top' style='scroll-margin-top: 10px;'></div>", unsafe_allow_html=True)

st.markdown(
    """
    <style>
    .slim-jump-container {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-top: 6px;
        margin-bottom: 14px;
        padding: 12px 16px;
        background-color: rgba(128, 128, 128, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.18);
        border-radius: 8px;
    }
    .slim-jump-row {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 2px 0;
    }
    .slim-label {
        flex-shrink: 0;
        width: auto !important;
        min-width: 165px;
        white-space: nowrap !important;
        word-break: keep-all !important;
        font-weight: 800;
        font-size: 1.15em;
        line-height: 1.3;
        cursor: pointer !important;
        user-select: none;
        padding: 4px 8px;
        border-radius: 6px;
        transition: all 0.15s ease;
    }
    .slim-label:hover {
        background-color: rgba(30, 58, 138, 0.12);
        transform: translateY(-1px);
    }
    .label-jr { color: #0284c7; }
    .label-private { color: #10b981; }
    .label-kintetsu { color: #f59e0b; }
    .slim-btn-wrapper {
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
        flex-grow: 1;
    }
    .comp-chk {
        display: none !important;
    }
    .comp-label {
        display: inline-block;
        padding: 3px 10px;
        background-color: #ffffff;
        color: #334155;
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.28);
        font-size: 0.78em;
        font-weight: 500;
        line-height: 1.5;
        cursor: pointer;
        user-select: none;
        transition: all 0.15s ease;
    }
    .comp-label:hover {
        background-color: #f1f5f9;
        border-color: #1e3a8a;
        color: #1e3a8a;
    }
    .comp-chk:checked + .comp-label {
        background-color: #1e3a8a !important;
        color: #ffffff !important;
        border-color: #1e3a8a !important;
        font-weight: 700 !important;
        box-shadow: 0 1px 3px rgba(30, 58, 138, 0.35) !important;
    }
    .filter-action-bar {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 4px;
        margin-bottom: 24px;
    }
    .apply-filter-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 8px 22px;
        background-color: #1e3a8a;
        color: #ffffff !important;
        border: none;
        border-radius: 6px;
        font-size: 0.9em;
        font-weight: 700;
        cursor: pointer;
        box-shadow: 0 2px 4px rgba(30, 58, 138, 0.25);
        transition: all 0.15s ease;
    }
    .apply-filter-btn:hover {
        background-color: #172554;
        box-shadow: 0 4px 6px rgba(30, 58, 138, 0.35);
    }
    .clear-filter-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 7px 18px;
        background-color: #ffffff;
        color: #475569 !important;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        font-size: 0.88em;
        font-weight: 600;
        text-decoration: none !important;
        cursor: pointer;
        transition: all 0.15s ease;
    }
    .clear-filter-btn:hover {
        background-color: #f8fafc;
        color: #1e3a8a !important;
        border-color: #1e3a8a;
    }
    .link-action-btn {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-top: 6px;
        padding: 4px 12px;
        background-color: rgba(30, 58, 138, 0.08);
        color: #1e3a8a !important;
        border: 1px solid rgba(30, 58, 138, 0.35);
        border-radius: 6px;
        font-size: 0.82em;
        font-weight: 600;
        text-decoration: none;
        transition: all 0.15s ease;
    }
    .link-action-btn:hover {
        background-color: #1e3a8a;
        color: #ffffff !important;
        border-color: #1e3a8a;
        text-decoration: none;
    }
    @media (max-width: 768px) {
        .slim-jump-row {
            flex-direction: column;
            align-items: flex-start;
            gap: 4px;
        }
        .slim-label {
            width: auto !important;
            min-width: unset;
            white-space: nowrap !important;
        }
        .filter-action-bar {
            flex-direction: column;
            align-items: stretch;
            gap: 8px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

def make_chk_btn_html(comp_list, prefix, selected_set):
    pieces = []
    for c in comp_list:
        cid = c["id"]
        chk_id = f"chk-{prefix}-{cid}"
        checked = "checked" if cid in selected_set else ""
        pieces.append(
            f'<input type="checkbox" name="c" value="{cid}" id="{chk_id}" class="comp-chk" {checked}>'
            f'<label for="{chk_id}" class="comp-label">{c["name"]}</label>'
        )
    return "".join(pieces)

sel_set = st.session_state.selected_filter_companies
has_filter = len(sel_set) > 0

jump_form_html = f"""
<form method="GET" action="" id="company-filter-form">
  <input type="hidden" name="submitted" value="1">
  <div style="margin-top: 10px; margin-bottom: 8px; font-size: 0.9em; font-weight: 600; color: #334155;">
    💡 会社名を押した後に、『選択した会社の記事を表示する』ボタンを押すと、その会社の記事だけを表示することができます。基本は全て表示します。
  </div>
  <div class="slim-jump-container">
    <div class="slim-jump-row">
      <div class="slim-label label-jr" id="toggle-btn-jr" title="クリックでJR各社を一括選択/解除">🚆 JR</div>
      <div class="slim-btn-wrapper">
        {make_chk_btn_html(jr_list, 'jr', sel_set)}
      </div>
    </div>
    <div class="slim-jump-row">
      <div class="slim-label label-private" id="toggle-btn-private" title="クリックで私鉄各社を一括選択/解除">🚇 私鉄</div>
      <div class="slim-btn-wrapper">
        {make_chk_btn_html(private_list, 'private', sel_set)}
      </div>
    </div>
    <div class="slim-jump-row">
      <div class="slim-label label-kintetsu" id="toggle-btn-kintetsu" title="クリックで近鉄グループ各社を一括選択/解除">🏢 近鉄グループ</div>
      <div class="slim-btn-wrapper">
        {make_chk_btn_html(kintetsu_list, 'kintetsu', sel_set)}
      </div>
    </div>
  </div>
  <div class="filter-action-bar">
    <button type="submit" class="apply-filter-btn">選択した会社の記事を表示する</button>
    <a href="?reset=1" class="clear-filter-btn">🔄 選択を解除する</a>
  </div>
</form>
"""

st.markdown(jump_form_html, unsafe_allow_html=True)

components.html(
    """
    <script>
    (function() {
        function setupGroupToggles() {
            const doc = window.parent.document;
            if (!doc) return;

            const groups = [
                { id: 'toggle-btn-jr', prefix: 'chk-jr-' },
                { id: 'toggle-btn-private', prefix: 'chk-private-' },
                { id: 'toggle-btn-kintetsu', prefix: 'chk-kintetsu-' }
            ];

            groups.forEach(function(g) {
                const el = doc.getElementById(g.id);
                if (!el) return;
                if (el.dataset.toggleBound === 'true') return;
                el.dataset.toggleBound = 'true';

                el.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();

                    const inputs = doc.querySelectorAll('input[id^="' + g.prefix + '"]');
                    if (!inputs || inputs.length === 0) return;

                    let allChecked = true;
                    inputs.forEach(function(inp) {
                        if (!inp.checked) allChecked = false;
                    });

                    const newChecked = !allChecked;
                    inputs.forEach(function(inp) {
                        inp.checked = newChecked;
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                    });
                });
            });
        }

        setupGroupToggles();
        let count = 0;
        const timer = setInterval(function() {
            setupGroupToggles();
            count++;
            if (count > 25) clearInterval(timer);
        }, 200);

        try {
            const observer = new MutationObserver(function() {
                setupGroupToggles();
            });
            if (window.parent && window.parent.document && window.parent.document.body) {
                observer.observe(window.parent.document.body, { childList: true, subtree: true });
            }
        } catch(err) {}
    })();
    </script>
    """,
    height=0,
    width=0,
)

# ==========================================
# 12. 結果の描画（完全排他表示・色付き分類タグ表示）
# ==========================================
view_mode = st.session_state.view_mode  # "official" または "news"

for group_prefix, group_title, comp_list in render_groups:
    if has_filter:
        visible_comps = [c for c in comp_list if c["id"] in sel_set and c["id"] not in st.session_state.hidden_companies]
    else:
        visible_comps = [c for c in comp_list if c["id"] not in st.session_state.hidden_companies]

    if not visible_comps:
        continue

    st.write("<br>", unsafe_allow_html=True)
    st.markdown(f"<div id='sec-{group_prefix}' style='scroll-margin-top: 15px;'></div>", unsafe_allow_html=True)
    st.markdown(f"## 【 {group_title} 】")
    st.divider()

    for comp in visible_comps:
        raw_items = all_cached_data.get(comp["name"], [])

        period_items = [
            item for item in raw_items
            if start_date <= item["date"] <= end_date
        ]

        official_items = [i for i in period_items if i["type"] == "公式発表"]
        general_items = [i for i in period_items if i["type"] == "ニュース（一般サイト）"]

        official_items.sort(key=lambda x: x["date"], reverse=True)
        general_items.sort(key=lambda x: x["date"], reverse=True)

        if view_mode == "official":
            display_items = official_items
        else:
            display_items = general_items

        main_url = comp.get("top_url", comp["urls"][0])
        anchor_id = f"{group_prefix}-{comp['id']}"

        h_col1, h_col2 = st.columns([5, 1.3])
        with h_col1:
            st.markdown(
                f"""
                <div id='{anchor_id}' style='margin-top: 18px; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 3px solid #1e3a8a; display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px;'>
                    <span style='font-size: 1.85em; font-weight: 800; color: #1e293b; line-height: 1.2;'>🏢 {comp['name']}</span>
                    <a href='{main_url}' target='_blank' rel='noreferrer noopener' style='font-size: 0.9em; font-weight: 600; color: #1e3a8a; text-decoration: none;'>[公式HP ↗]</a>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with h_col2:
            st.write("<div style='margin-top: 22px;'></div>", unsafe_allow_html=True)
            if st.button("記事を非表示", key=f"btn_hide_{group_prefix}_{comp['id']}", type="secondary", use_container_width=True):
                st.session_state.hidden_companies.add(comp["id"])
                if comp["id"] in st.session_state.selected_filter_companies:
                    st.session_state.selected_filter_companies.remove(comp["id"])
                st.rerun()

        if not display_items:
            mode_str = "公式発表" if view_mode == "official" else "ニュース"
            st.info(f"📅 指定期間内の **{mode_str}** は **なし** です。")
            st.write("")
        else:
            for item in display_items:
                is_official = item["type"] == "公式発表"

                if is_official:
                    type_badge = (
                        "<div style='display:inline-block; padding:3px 10px; background-color:#1e3a8a; "
                        "color:#ffffff; font-size:0.8em; font-weight:700; border-radius:5px; margin-bottom:4px; "
                        "box-shadow: 0 1px 2px rgba(0,0,0,0.15); letter-spacing:0.04em;'>📢 公式発表</div>"
                    )

                    title_link = item["url"]
                    if comp["id"] == "jr-west":
                        if item.get("pdf_url"):
                            action_link = item["pdf_url"]
                            action_caption = "掲載資料（PDF）を開く ↗"
                            file_badge = "🟥 **[PDF資料]**"
                        else:
                            action_link = item["url"]
                            action_caption = "掲載ページを開く ↗"
                            file_badge = "🌐 **[Web発表]**"
                    else:
                        action_link = item.get("pdf_url") or item["url"]
                        action_caption = "掲載資料（PDF）を開く ↗" if item.get("is_pdf") else "掲載ページを開く ↗"
                        file_badge = "🟥 **[PDF資料]**" if item.get("is_pdf") else "🌐 **[Web発表]**"

                else:
                    type_badge = (
                        "<div style='display:inline-block; padding:3px 9px; background-color:#f1f5f9; "
                        "color:#475569; font-size:0.78em; font-weight:600; border-radius:5px; "
                        "border:1px solid #cbd5e1; margin-bottom:4px;'>📰 ニュース（一般）</div>"
                    )
                    title_link = item["url"]
                    action_link = item["url"]
                    action_caption = "記事を表示する ↗"
                    file_badge = "🌐 **[Webニュース]**"

                with st.container(border=True):
                    col_left, col_right = st.columns([1, 4])
                    with col_left:
                        st.write(f"📅 **{item['date']}**")
                        st.markdown(type_badge, unsafe_allow_html=True)
                        st.markdown(file_badge)
                        st.caption(f"情報元: {item['source']}")

                        # ★ 分類タグの表示（「経済」「車両・運行」「イベント」等の色付きボタン風バッジ）
                        tag_name, tag_color, tag_bg, tag_border = item.get(
                            "tag_info", ("一般", "#475569", "#f8fafc", "#cbd5e1")
                        )
                        st.markdown(
                            f"""
                            <div style='margin-top: 4px;'>
                                <span style='display:inline-block; padding: 2px 9px; border-radius: 4px; font-size: 0.76em; font-weight: 700; background-color: {tag_bg}; color: {tag_color}; border: 1px solid {tag_border}; letter-spacing: 0.02em;'>
                                    🏷️ {tag_name}
                                </span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    with col_right:
                        st.markdown(
                            f"##### <a href='{title_link}' target='_blank' rel='noreferrer noopener'>{item['title']}</a>",
                            unsafe_allow_html=True,
                        )

                        if item.get("summary"):
                            st.write(f"**主な内容:** {item['summary']}")

                        st.markdown(
                            f"<a href='{action_link}' target='_blank' rel='noreferrer noopener' class='link-action-btn'>🔗 {action_caption}</a>",
                            unsafe_allow_html=True,
                        )
            st.write("")
