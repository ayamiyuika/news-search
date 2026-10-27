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
# 0. メディア優先度＆ナビゲーション除外ブラックリスト
# ==========================================
MEDIA_PRIORITY = {
    "NHK NEWS": 100,
    "日本経済新聞": 95,
    "読売新聞オンライン": 90,
    "朝日新聞デジタル": 90,
    "共同通信": 85,
    "毎日新聞": 85,
    "産経ニュース": 85,
    "時事通信": 80,
    "Yahoo!ニュース": 75,
    "乗りものニュース": 72,
    "鉄道コム": 70,
    "鉄道ファン (railf.jp)": 70,
    "マイナビニュース": 65,
    "東洋経済オンライン": 65,
    "ITmedia": 60,
    "ダイヤモンド・オンライン": 60,
    "FNNプライムオンライン": 55,
    "テレ朝news": 55,
    "TBS NEWS DIG": 55,
    "日テレNEWS": 55,
    "神戸新聞NEXT": 50,
    "京都新聞": 50,
    "中日新聞": 50,
    "東京新聞": 50,
    "北海道新聞": 50,
    "西日本新聞": 50,
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

# セッションステートの初期化
today = datetime.datetime.now(JST).date()

# ★ 表示モード（"official": 公式発表, "news": ニュース, None: 両方OFF）
if "active_mode" not in st.session_state:
    st.session_state.active_mode = "official"  # デフォルトは公式発表（青色）
if "period_days" not in st.session_state:
    st.session_state.period_days = 3           # デフォルト：3日間
if "custom_date_range" not in st.session_state:
    st.session_state.custom_date_range = (today - datetime.timedelta(days=2), today)
if "hidden_companies" not in st.session_state:
    st.session_state.hidden_companies = set()
if "selected_filter_companies" not in st.session_state:
    st.session_state.selected_filter_companies = set()
if "diag_logs" not in st.session_state:
    st.session_state.diag_logs = {}

# ==========================================
# 0-A. クエリパラメータ（一括選択・解除）の処理
# ==========================================
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
# 1. 会社マスタープール（東京メトロ・大阪メトロ完全削除、海遊館なし）
# ==========================================
COMPANY_POOL = {
    # --- JR各社 ---
    "jr-hokkaido": {
        "id": "jr-hokkaido",
        "name": "JR北海道",
        "top_url": "https://www.jrhokkaido.co.jp/",
        "official_domains": ["jrhokkaido.co.jp"],
        "urls": [
            "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html",
            "https://www.jrhokkaido.co.jp/",
        ],
        "query": "JR北海道 OR 北海道旅客鉄道",
    },
    "jr-east": {
        "id": "jr-east",
        "name": "JR東日本",
        "is_jr_east": True,
        "top_url": "https://www.jreast.co.jp/",
        "official_domains": ["jreast.co.jp"],
        "urls": [
            "https://www.jreast.co.jp/press/",
            "https://www.jreast.co.jp/rss/press.xml",
            "https://www.jreast.co.jp/",
        ],
        "query": "JR東日本 OR 東日本旅客鉄道",
    },
    "jr-central": {
        "id": "jr-central",
        "name": "JR東海",
        "top_url": "https://jr-central.co.jp/",
        "official_domains": ["jr-central.co.jp"],
        "urls": [
            "https://jr-central.co.jp/news/release/",
            "https://jr-central.co.jp/news/",
            "https://jr-central.co.jp/",
        ],
        "query": "JR東海 OR 東海旅客鉄道",
    },
    "jr-west": {
        "id": "jr-west",
        "name": "JR西日本",
        "top_url": "https://www.westjr.co.jp/",
        "official_domains": ["westjr.co.jp"],
        "urls": [
            "https://www.westjr.co.jp/press/article/",
            "https://www.westjr.co.jp/press/",
            "https://www.westjr.co.jp/",
        ],
        "query": "JR西日本 OR 西日本旅客鉄道",
    },
    "jr-shikoku": {
        "id": "jr-shikoku",
        "name": "JR四国",
        "top_url": "https://www.jr-shikoku.co.jp/",
        "official_domains": ["jr-shikoku.co.jp"],
        "urls": [
            "https://www.jr-shikoku.co.jp/03_news/press/",
            "https://www.jr-shikoku.co.jp/",
        ],
        "query": "JR四国 OR 四国旅客鉄道",
    },
    "jr-kyushu": {
        "id": "jr-kyushu",
        "name": "JR九州",
        "top_url": "https://www.jrkyushu.co.jp/",
        "official_domains": ["jrkyushu.co.jp"],
        "urls": [
            "https://www.jrkyushu.co.jp/news/release/index.html",
            "https://www.jrkyushu.co.jp/news/",
        ],
        "query": "JR九州 OR 九州旅客鉄道",
    },
    # --- 私鉄各社 ---
    "tobu": {
        "id": "tobu",
        "name": "東武鉄道",
        "top_url": "https://www.tobu.co.jp/",
        "official_domains": ["tobu.co.jp"],
        "urls": [
            "https://www.tobu.co.jp/newsrelease/",
            "https://www.tobu.co.jp/",
        ],
        "query": "東武鉄道",
    },
    "seibu": {
        "id": "seibu",
        "name": "西武鉄道（西武HD含む）",
        "top_url": "https://www.seiburailway.jp/",
        "official_domains": ["seiburailway.jp", "seibuholdings.co.jp"],
        "urls": [
            "https://www.seiburailway.jp/newsroom/news/",
            "https://www.seibuholdings.co.jp/news/",
            "https://www.seiburailway.jp/",
        ],
        "query": "西武鉄道 OR 西武ホールディングス",
    },
    "keisei": {
        "id": "keisei",
        "name": "京成電鉄",
        "top_url": "https://www.keisei.co.jp/",
        "official_domains": ["keisei.co.jp"],
        "urls": [
            "https://www.keisei.co.jp/",
            "https://www.keisei.co.jp/news/",
        ],
        "query": "京成電鉄",
    },
    "keio": {
        "id": "keio",
        "name": "京王電鉄",
        "top_url": "https://www.keio.co.jp/",
        "official_domains": ["keio.co.jp"],
        "urls": [
            "https://www.keio.co.jp/news/update/news_release/",
            "https://www.keio.co.jp/news/update/index.html",
            "https://www.keio.co.jp/",
        ],
        "query": "京王電鉄",
    },
    "odakyu": {
        "id": "odakyu",
        "name": "小田急電鉄",
        "top_url": "https://www.odakyu.jp/",
        "official_domains": ["odakyu.jp"],
        "urls": [
            "https://www.odakyu.jp/company/about/news/",
            "https://www.odakyu.jp/news/",
            "https://www.odakyu.jp/",
        ],
        "query": "小田急電鉄",
    },
    # ★ 「東急電鉄（東急を含む）」
    "tokyu": {
        "id": "tokyu",
        "name": "東急電鉄（東急を含む）",
        "top_url": "https://www.tokyu.co.jp/",
        "official_domains": ["tokyu.co.jp"],
        "urls": [
            "https://www.tokyu.co.jp/company/news/",
            "https://www.tokyu.co.jp/",
            "https://www.tokyu.co.jp/information/",
        ],
        "query": "東急電鉄 OR 東急",
    },
    "keikyu": {
        "id": "keikyu",
        "name": "京浜急行電鉄",
        "top_url": "https://www.keikyu.co.jp/",
        "official_domains": ["keikyu.co.jp"],
        "urls": [
            "https://www.keikyu.co.jp/",
            "https://www.keikyu.co.jp/company/news/",
            "https://www.keikyu.co.jp/report/",
        ],
        "query": "京浜急行電鉄 OR 京急",
    },
    "sotetsu": {
        "id": "sotetsu",
        "name": "相模鉄道（相鉄HD含む）",
        "top_url": "https://www.sotetsu.co.jp/",
        "official_domains": ["sotetsu.co.jp"],
        "urls": [
            "https://www.sotetsu.co.jp/",
            "https://www.sotetsu.co.jp/pressrelease/",
            "https://www.sotetsu.co.jp/news/",
        ],
        "query": "相模鉄道 OR 相鉄ホールディングス",
    },
    "meitetsu": {
        "id": "meitetsu",
        "name": "名古屋鉄道",
        "top_url": "https://www.meitetsu.co.jp/",
        "official_domains": ["meitetsu.co.jp"],
        "urls": [
            "https://www.meitetsu.co.jp/profile/news/",
            "https://www.meitetsu.co.jp/",
        ],
        "query": "名古屋鉄道 OR 名鉄",
    },
    "nankai": {
        "id": "nankai",
        "name": "南海電気鉄道",
        "top_url": "https://www.nankai.co.jp/",
        "official_domains": ["nankai.co.jp"],
        "urls": [
            "https://www.nankai.co.jp/news.html",
            "https://www.nankai.co.jp/company/news/",
            "https://www.nankai.co.jp/news/",
            "https://www.nankai.co.jp/",
        ],
        "query": "南海電気鉄道 OR 南海電鉄",
    },
    "keihan": {
        "id": "keihan",
        "name": "京阪電気鉄道（京阪HD含む）",
        "top_url": "https://www.keihan.co.jp/",
        "official_domains": ["keihan.co.jp", "keihan-holdings.co.jp"],
        "urls": [
            "https://www.keihan.co.jp/corporate/release/",
            "https://www.keihan-holdings.co.jp/news/",
            "https://www.keihan.co.jp/",
        ],
        "query": "京阪電気鉄道 OR 京阪ホールディングス",
    },
    "hanshin": {
        "id": "hanshin",
        "name": "阪神電気鉄道",
        "top_url": "https://www.hanshin.co.jp/",
        "official_domains": ["hanshin.co.jp", "hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hanshin.co.jp/press/",
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hanshin.co.jp/",
        ],
        "query": "阪神電気鉄道 OR 阪神電車",
    },
    # ★ 阪急電鉄
    "hankyu": {
        "id": "hankyu",
        "name": "阪急電鉄",
        "top_url": "https://www.hankyu.co.jp/",
        "official_domains": ["hankyu.co.jp", "hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hankyu.co.jp/company/news/index.html",
            "https://www.hankyu.co.jp/company/news/",
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hankyu.co.jp/",
        ],
        "query": "阪急電鉄 OR 阪急電車",
    },
    # ★ 阪急阪神HD
    "hankyu-hanshin-hd": {
        "id": "hankyu-hanshin-hd",
        "name": "阪急阪神ホールディングス",
        "top_url": "https://www.hankyu-hanshin.co.jp/",
        "official_domains": ["hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hankyu-hanshin.co.jp/",
        ],
        "query": "阪急阪神ホールディングス OR \"阪急阪神HD\"",
    },
    "nishitetsu": {
        "id": "nishitetsu",
        "name": "西日本鉄道",
        "top_url": "https://www.nishitetsu.co.jp/",
        "official_domains": ["nishitetsu.co.jp"],
        "urls": [
            "https://www.nishitetsu.co.jp/ja/news.html",
            "https://www.nishitetsu.co.jp/release/",
            "https://www.nishitetsu.co.jp/",
        ],
        "query": "西日本鉄道 OR 西鉄",
    },
    # --- 近鉄グループ（17社・海遊館なし） ---
    "kintetsu-ghd": {
        "id": "kintetsu-ghd",
        "name": "近鉄GHD",
        "top_url": "https://www.kintetsu-g-hd.co.jp/",
        "official_domains": ["kintetsu-g-hd.co.jp"],
        "urls": [
            "https://www.kintetsu-g-hd.co.jp/news-hd/",
            "https://www.kintetsu-g-hd.co.jp/news-kg/",
            "https://www.kintetsu-g-hd.co.jp/",
        ],
        "query": "近鉄グループホールディングス OR 近鉄GHD OR 近鉄グループ",
    },
    "kintetsu-railway": {
        "id": "kintetsu-railway",
        "name": "近畿日本鉄道",
        "top_url": "https://www.kintetsu.co.jp/",
        "official_domains": ["kintetsu.co.jp"],
        "urls": [
            "https://www.kintetsu.co.jp/all_news/whatsnew.html",
            "https://www.kintetsu.co.jp/all_info/whatsnew.html",
            "https://www.kintetsu.co.jp/all_news/",
            "https://www.kintetsu.co.jp/",
        ],
        "query": "近畿日本鉄道 OR 近鉄電車 OR 近鉄特急",
    },
    "kintetsu-fudosan": {
        "id": "kintetsu-fudosan",
        "name": "近鉄不動産",
        "top_url": "https://www.kintetsu-re.co.jp/",
        "official_domains": ["kintetsu-re.co.jp"],
        "urls": [
            "https://www.kintetsu-re.co.jp/news/",
            "https://www.kintetsu-re.co.jp/corporate/news/",
            "https://www.kintetsu-re.co.jp/corporate/",
        ],
        "query": "近鉄不動産",
    },
    "abeno-art-museum": {
        "id": "abeno-art-museum",
        "name": "あべのハルカス美術館",
        "top_url": "https://www.aham.jp/",
        "official_domains": ["aham.jp"],
        "urls": [
            "https://www.aham.jp/news/",
            "https://www.aham.jp/information/",
            "https://www.aham.jp/",
        ],
        "query": '"あべのハルカス美術館"',
    },
    "kwe": {
        "id": "kwe",
        "name": "近鉄エクスプレス",
        "top_url": "https://www.kwe.co.jp/",
        "official_domains": ["kwe.co.jp", "kwe.com"],
        "urls": [
            "https://www.kwe.co.jp/news/",
            "https://www.kwe.co.jp/",
        ],
        "query": '"近鉄エクスプレス"',
    },
    "kintetsu-dept": {
        "id": "kintetsu-dept",
        "name": "近鉄百貨店",
        "top_url": "https://www.d-kintetsu.co.jp/",
        "official_domains": ["d-kintetsu.co.jp"],
        "urls": [
            "https://www.d-kintetsu.co.jp/",
            "https://www.d-kintetsu.co.jp/corporate/ir/whatsnew.html",
            "https://www.d-kintetsu.co.jp/corporate/",
        ],
        "query": '"近鉄百貨店"',
    },
    "kintetsu-retailing": {
        "id": "kintetsu-retailing",
        "name": "近鉄リテーリング",
        "top_url": "https://knt-rt.co.jp/",
        "official_domains": ["knt-rt.co.jp"],
        "urls": [
            "https://knt-rt.co.jp/",
            "https://knt-rt.co.jp/news/",
        ],
        "query": '"近鉄リテーリング"',
    },
    "kinsho-store": {
        "id": "kinsho-store",
        "name": "近商ストア",
        "top_url": "https://www.kinshostore.co.jp/",
        "official_domains": ["kinsho-store.co.jp", "kinshostore.co.jp"],
        "urls": [
            "https://www.kinshostore.co.jp/html/news.php",
            "https://www.kinsho-store.co.jp/html/news.php",
            "https://www.kinshostore.co.jp/",
        ],
        "query": '"近商ストア"',
    },
    "miyako-hotels": {
        "id": "miyako-hotels",
        "name": "近鉄・都ホテルズ",
        "top_url": "https://www.miyakohotels.ne.jp/",
        "official_domains": ["miyakohotels.ne.jp"],
        "urls": [
            "https://www.miyakohotels.ne.jp/",
            "https://www.miyakohotels.ne.jp/newsrelease/",
        ],
        "query": '"近鉄・都ホテルズ" OR "都ホテルズ＆リゾーツ" OR "都ホテル"',
    },
    "knt-ct": {
        "id": "knt-ct",
        "name": "KNT-CTホールディングス",
        "top_url": "https://www.kntcthd.co.jp/",
        "official_domains": ["kntcthd.co.jp"],
        "urls": [
            "https://www.kntcthd.co.jp/release/",
            "https://www.kntcthd.co.jp/news/",
            "https://www.kntcthd.co.jp/",
        ],
        "query": '"KNT-CTホールディングス" OR "KNT-CT"',
    },
    "knt": {
        "id": "knt",
        "name": "近畿日本ツーリスト",
        "top_url": "https://corp.knt.co.jp/",
        "official_domains": ["knt.co.jp"],
        "urls": [
            "https://corp.knt.co.jp/ja/release/",
            "https://corp.knt.co.jp/",
            "https://www.knt.co.jp/",
        ],
        "query": '"近畿日本ツーリスト"',
    },
    "club-tourism": {
        "id": "club-tourism",
        "name": "クラブツーリズム",
        "top_url": "https://www.club-t.com/",
        "official_domains": ["club-t.com", "club-tourism.co.jp"],
        "urls": [
            "https://www.club-t.com/ct/news/",
            "https://www.club-tourism.co.jp/jpn/press/",
            "https://www.club-tourism.co.jp/jpn/",
        ],
        "query": '"クラブツーリズム"',
    },
    "shima-spain-village": {
        "id": "shima-spain-village",
        "name": "志摩スペイン村",
        "top_url": "https://parque-net.com/",
        "official_domains": ["parque-net.com"],
        "urls": [
            "https://www.parque-net.com/press/",
            "https://www.parque-net.com/blog/?cat=7",
        ],
        "query": '"志摩スペイン村" OR "パルケエスパーニャ"',
    },
    "kintetsu-bus": {
        "id": "kintetsu-bus",
        "name": "近鉄バス",
        "top_url": "https://www.kintetsu-bus.co.jp/",
        "official_domains": ["kintetsu-bus.co.jp"],
        "urls": [
            "https://www.kintetsu-bus.co.jp/news/",
            "https://www.kintetsu-bus.co.jp/",
        ],
        "query": '"近鉄バス"',
    },
    "nara-kotsu": {
        "id": "nara-kotsu",
        "name": "奈良交通",
        "top_url": "https://www.narakotsu.co.jp/",
        "official_domains": ["narakotsu.co.jp"],
        "urls": [
            "https://www.narakotsu.co.jp/news/category/press/",
            "https://www.narakotsu.co.jp/news/",
        ],
        "query": '"奈良交通"',
    },
    "sanco-hd": {
        "id": "sanco-hd",
        "name": "三交ホールディングス",
        "top_url": "https://holdings.sanco.co.jp/",
        "official_domains": ["holdings.sanco.co.jp", "sanco.co.jp"],
        "urls": [
            "https://holdings.sanco.co.jp/news/",
            "https://holdings.sanco.co.jp/",
            "https://www.sanco.co.jp/allnews/",
        ],
        "query": '"三交ホールディングス" OR "三重交通グループホールディングス"',
    },
    "sanco": {
        "id": "sanco",
        "name": "三重交通",
        "top_url": "https://www.sanco.co.jp/",
        "official_domains": ["sanco.co.jp"],
        "urls": [
            "https://www.sanco.co.jp/allnews/",
            "https://www.sanco.co.jp/other/newsrelease/",
            "https://www.sanco.co.jp/",
        ],
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
    "kintetsu-ghd",
    "kintetsu-railway",
    "kintetsu-fudosan",
    "abeno-art-museum",
    "kwe",
    "kintetsu-dept",
    "kintetsu-retailing",
    "kinsho-store",
    "miyako-hotels",
    "knt-ct",
    "knt",
    "club-tourism",
    "shima-spain-village",
    "kintetsu-bus",
    "nara-kotsu",
    "sanco-hd",
    "sanco"
]

MEDIA_NAME_MAP = {
    "asahi.com": "朝日新聞デジタル",
    "nikkei.com": "日本経済新聞",
    "yomiuri.co.jp": "読売新聞オンライン",
    "mainichi.jp": "毎日新聞",
    "sankei.com": "産経ニュース",
    "yahoo.co.jp": "Yahoo!ニュース",
    "trafficnews.jp": "乗りものニュース",
    "tetsudo.com": "鉄道コム",
    "railf.jp": "鉄道ファン (railf.jp)",
    "news.mynavi.jp": "マイナビニュース",
    "itmedia.co.jp": "ITmedia",
    "toyokeizai.net": "東洋経済オンライン",
    "diamond.jp": "ダイヤモンド・オンライン",
    "kyodo.co.jp": "共同通信",
    "nordot.app": "ノードット (共同通信系)",
    "jiji.com": "時事通信",
    "nhk.or.jp": "NHK NEWS",
    "kobe-np.co.jp": "神戸新聞NEXT",
    "kyoto-np.co.jp": "京都新聞",
    "chunichi.co.jp": "中日新聞",
    "tokyo-np.co.jp": "東京新聞",
    "hokkaido-np.co.jp": "北海道新聞",
    "nishinippon.co.jp": "西日本新聞",
    "reuters.com": "ロイター",
    "bloomberg.co.jp": "ブルームバーグ",
    "fnn.jp": "FNNプライムオンライン",
    "tv-asahi.co.jp": "テレ朝news",
    "tbs.co.jp": "TBS NEWS DIG",
    "ntv.co.jp": "日テレNEWS",
}

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

    # datetime属性の検出
    attr_match = re.search(r'(?:datetime|data-date)=["\']((?:19|20)\d{2}[-/\.][0-9]{1,2}[-/\.][0-9]{1,2})', raw_text, re.IGNORECASE)
    if attr_match:
        try:
            parts = [int(p) for p in re.split(r'[-/\.]', attr_match.group(1))]
            return datetime.date(parts[0], parts[1], parts[2])
        except Exception:
            pass

    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = text.translate(zen_to_han)

    # 1. 令和表記
    m_reiwa = re.search(r"令和\s*([0-9]+|元)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日", text)
    if m_reiwa:
        y_val = 1 if m_reiwa.group(1) == "元" else int(m_reiwa.group(1))
        try:
            return datetime.date(2018 + y_val, int(m_reiwa.group(2)), int(m_reiwa.group(3)))
        except ValueError:
            pass

    # 2. 西暦表記（2026/10/22, 2026.10.22, 2026-10-22, 2026年10月22日）
    m_seireki = re.search(r"((?:19|20)\d{2})\s*[年\./\-]\s*([0-9]{1,2})\s*[月\./\-]\s*([0-9]{1,2})\s*日?", text)
    if m_seireki:
        try:
            return datetime.date(int(m_seireki.group(1)), int(m_seireki.group(2)), int(m_seireki.group(3)))
        except ValueError:
            pass

    # 3. 月日のみ表記
    if not re.search(r"(?:19|20)\d{2}", text):
        m_md = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*[月\./\-]\s*(3[01]|[12][0-9]|0?[1-9])\s*日?(?!\d)", text)
        if m_md:
            try:
                return datetime.date(current_year, int(m_md.group(1)), int(m_md.group(2)))
            except ValueError:
                pass

    return None


def remove_leading_date(text):
    """タイトル冒頭の日付表記を除去する"""
    text = re.sub(r'^(?:(?:19|20)\d{2}[年\.\/\-]\s*\d{1,2}[月\.\/\-]\s*\d{1,2}日?)\s*[:：|｜・\s\-]*', '', text)
    text = re.sub(r'^(?:(?:令和|平成)\s*(?:\d+|元)年\s*\d{1,2}月\s*\d{1,2}日)\s*[:：|｜・\s\-]*', '', text)
    text = re.sub(r'^[\[【(](?:(?:19\vert{}20)\d{2}[年\.\/\-]\s*\d{1,2}[月\.\/\-]\s*\d{1,2}日?)[\]】)]\s*', '', text)
    return text.strip()


def clean_extracted_title(raw_title, company_info):
    """タイトルをサニタイズ（HTMLタグ除去後に不要テキストや属性残骸を排除）"""
    t = re.sub(r"<[^>]*>", " ", raw_title)
    t = html.unescape(t)
    t = remove_leading_date(t)

    # 定型会社名や接頭辞の除去
    t = re.sub(r"^(?:東急電鉄|京急電鉄|近畿日本鉄道|プレスリリース|ニュースリリース|お知らせ|PRESS\s*RELEASE|NEWS|重要|電鉄|グループ)\s*", "", t.strip(), flags=re.IGNORECASE)
    t = remove_leading_date(t)

    # 近商ストア専用クレンジング
    if company_info["id"] == "kinsho-store":
        t = re.sub(r'(?:NEW|新着|お知らせ|重要|\.pdf|\.PDF)+', '', t).strip()
        t = re.sub(r'^[【\[（\(].*?[】\]）\)]', '', t).strip()
        t = re.sub(r'^[a-zA-Z0-9_\-]+["\']?>', '', t).strip()

    # 三交ホールディングス・三重交通
    if company_info["id"] in ["sanco-hd", "sanco"]:
        t = re.sub(r'(?:グループニュース|IRニュース|お知らせ|ニュースリリース)+', '', t).strip()
        t = re.sub(r'#448073;padding:[^;]*;', '', t).strip()

    # KNT-CT：特集・発売中バナーの排除
    if company_info["id"] in ["knt-ct", "knt"]:
        if any(w in t for w in ["特集", "発売中", "旅行代金", "ツアー一覧"]):
            return ""

    t = re.sub(r"\s+", " ", t).strip()

    # ナビゲーション固定メニューや短文単語の完全除外
    t_lower = t.lower()
    if t_lower in NAV_EXCLUDE_WORDS or any(w == t for w in NAV_EXCLUDE_WORDS):
        return ""
    if len(t) < 8:  # 8文字未満の短い単語リンクは公式発表の見出しではないため除外
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
# 3. HTTP通信ユーティリティ（最新WAF完全回避セッション）
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
# 4. 厳格ペアリング公式発表抽出エンジン（巨大コンテナ巻き込み完全防止）
# ==========================================
def parse_official_releases_strict(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls):
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
                    clean_t = clean_extracted_title(t, company_info)
                    if clean_t:
                        seen_urls.add(l)
                        results.append({
                            "date": item_date,
                            "type": "公式発表",
                            "title": clean_t,
                            "url": l,
                            "pdf_url": l if l.lower().split('?')[0].endswith(".pdf") else None,
                            "source": company_info["name"] + " 公式HP",
                            "is_pdf": l.lower().split('?')[0].endswith(".pdf"),
                        })
        if results:
            return results

    # 2. スクリプト・スタイルの事前クレンジング
    clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<svg.*?>.*?</svg>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    # ★ パターン1: 構造ブロック単位（行 <tr>、リスト <li>、カード <article>）
    # ※ <div> は月別ナビゲーションやコンテナ全体を巻き込むため、ブロック単位としては使用しない
    block_patterns = [
        r'(<tr[^>]*>.*?</tr>)',
        r'(<li[^>]*>.*?</li>)',
        r'(<article[^>]*>.*?</article>)',
    ]

    for b_pat in block_patterns:
        for block in re.findall(b_pat, clean_html, flags=re.DOTALL | re.IGNORECASE):
            d_val = parse_date_text(block, current_year)
            if not d_val or not (cutoff_date <= d_val <= today):
                continue

            for a_m in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, flags=re.DOTALL | re.IGNORECASE):
                href = a_m.group(1).strip().replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
                if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                    continue

                full_url = urllib.parse.urljoin(base_url, href)
                if full_url in seen_urls:
                    continue

                if not is_jr_east:
                    parsed_u = urllib.parse.urlparse(full_url)
                    if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
                        continue

                # タイトルは絶対にブロック全体ではなく <a> タグ内のテキストから取得
                clean_t = clean_extracted_title(a_m.group(2), company_info)
                if not clean_t:
                    clean_block_txt = re.sub(r"<[^>]+>", " ", block)
                    clean_t = clean_extracted_title(clean_block_txt, company_info)

                if not clean_t:
                    continue

                seen_urls.add(full_url)
                is_pdf = full_url.lower().split('?')[0].endswith(".pdf")
                results.append({
                    "date": d_val,
                    "type": "公式発表",
                    "title": clean_t[:130],
                    "url": full_url,
                    "pdf_url": full_url if is_pdf else None,
                    "source": company_info["name"] + " 公式発表",
                    "is_pdf": is_pdf,
                })

    # ★ パターン2: 近鉄各社などの <dt>日付</dt><dd>リンク</dd> 定義リスト直結構造
    dt_dd_pattern = r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>'
    for m in re.finditer(dt_dd_pattern, clean_html, flags=re.DOTALL | re.IGNORECASE):
        dt_txt = m.group(1)
        dd_txt = m.group(2)
        d_val = parse_date_text(dt_txt, current_year)
        if not d_val or not (cutoff_date <= d_val <= today):
            continue

        for a_m in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', dd_txt, flags=re.DOTALL | re.IGNORECASE):
            href = a_m.group(1).strip().replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
            if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                continue

            full_url = urllib.parse.urljoin(base_url, href)
            if full_url in seen_urls:
                continue

            clean_t = clean_extracted_title(a_m.group(2), company_info)
            if not clean_t:
                continue

            seen_urls.add(full_url)
            is_pdf = full_url.lower().split('?')[0].endswith(".pdf")
            results.append({
                "date": d_val,
                "type": "公式発表",
                "title": clean_t[:130],
                "url": full_url,
                "pdf_url": full_url if is_pdf else None,
                "source": company_info["name"] + " 公式発表",
                "is_pdf": is_pdf,
            })

    # ★ パターン3: カード型リンク内包日付（東急、京急等）
    p_inside = r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>'
    for m in re.finditer(p_inside, clean_html, re.IGNORECASE):
        href = m.group(1).strip().replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        body = m.group(2)
        d_val = parse_date_text(body, current_year)
        if not d_val or not (cutoff_date <= d_val <= today):
            continue

        full_url = urllib.parse.urljoin(base_url, href)
        if full_url in seen_urls:
            continue

        if not is_jr_east:
            parsed_u = urllib.parse.urlparse(full_url)
            if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
                continue

        clean_t = clean_extracted_title(body, company_info)
        if not clean_t:
            continue

        seen_urls.add(full_url)
        is_pdf = full_url.lower().split('?')[0].endswith(".pdf")
        results.append({
            "date": d_val,
            "type": "公式発表",
            "title": clean_t[:130],
            "url": full_url,
            "pdf_url": full_url if is_pdf else None,
            "source": company_info["name"] + " 公式発表",
            "is_pdf": is_pdf,
        })

    return results


# ==========================================
# 5. 公式発表 取得ディスパッチャー（JR東日本救済ルート搭載）
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

    # 1. 登録URLの直接巡回
    has_403 = False
    for url in company_info["urls"]:
        html_text, final_url, status = fetch_url_html(url, company_info.get("top_url", url), {}, ctx)
        log_entry["tried_urls"].append(f"{url} -> [{status}]")
        if "403" in status:
            has_403 = True

        if html_text:
            items = parse_official_releases_strict(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)
            results.extend(items)
            if results:
                break

    # 2. トップページの再探索（未取得時）
    if not results and company_info.get("top_url") and not has_403:
        top_html, final_top_url, status = fetch_url_html(company_info["top_url"], "", {}, ctx)
        log_entry["tried_urls"].append(f"TOP: {company_info['top_url']} -> [{status}]")
        if top_html:
            items = parse_official_releases_strict(top_html, final_top_url, company_info, cutoff_date, today, current_year, seen_urls)
            results.extend(items)

    # 3. ★ JR東日本公式発表 救済エンジン（WAF 403遮断・社内制限を完全突破）
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
                                b64_str = u_match.group(1) + '=' * (-len(u_match.group(1)) %
