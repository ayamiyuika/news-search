import base64
import datetime
import email.utils
import gzip
import html
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
    page_title="全国大手鉄道会社  広報発表・ニュース 概要",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 全国大手鉄道会社  広報発表・ニュース 概要")
st.caption("JR・大手私鉄・近鉄グループ各社の公式発表・最新ニュースを一覧表示します。")

# セッションステートの初期化
if "hidden_companies" not in st.session_state:
    st.session_state.hidden_companies = set()
if "selected_filter_companies" not in st.session_state:
    st.session_state.selected_filter_companies = set()
if "show_official" not in st.session_state:
    st.session_state.show_official = True
if "show_news" not in st.session_state:
    st.session_state.show_news = True

# ==========================================
# 0. クエリパラメータ（一括選択・解除）の処理
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
# 1. 鉄道会社・持株会社・グループ各社のマスタープール
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
        "query": "JR北海道",
    },
    "jr-east": {
        "id": "jr-east",
        "name": "JR東日本",
        "top_url": "https://www.jreast.co.jp/",
        "official_domains": ["jreast.co.jp", "prtimes.jp"],
        "urls": [
            "https://www.jreast.co.jp/press/",
            "https://prtimes.jp/main/html/searchrlp/company_id/17557",
            "https://www.jreast.co.jp/",
        ],
        "query": "JR東日本",
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
        "query": "JR西日本",
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
        "query": "JR四国",
    },
    "jr-kyushu": {
        "id": "jr-kyushu",
        "name": "JR九州",
        "top_url": "https://www.jrkyushu.co.jp/",
        "official_domains": ["jrkyushu.co.jp"],
        "urls": [
            "https://www.jrkyushu.co.jp/news/release/index.html",
            "https://www.jrkyushu.co.jp/news/",
            "https://www.jrkyushu.co.jp/",
        ],
        "query": "JR九州",
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
    # ★ 京成電鉄：最新の正規リリースページURLに完全修正
    "keisei": {
        "id": "keisei",
        "name": "京成電鉄",
        "top_url": "https://www.keisei.co.jp/",
        "official_domains": ["keisei.co.jp"],
        "urls": [
            "https://www.keisei.co.jp/news/",
            "https://www.keisei.co.jp/",
        ],
        "query": "京成電鉄",
    },
    "tokyo-metro": {
        "id": "tokyo-metro",
        "name": "東京メトロ",
        "top_url": "https://www.tokyometro.jp/",
        "official_domains": ["tokyometro.jp"],
        "urls": [
            "https://www.tokyometro.jp/news/index.html",
            "https://www.tokyometro.jp/news/rss/news.xml",
            "https://www.tokyometro.jp/",
        ],
        "query": "東京メトロ OR 東京地下鉄",
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
            "https://www.odakyu.jp/",
        ],
        "query": "小田急電鉄",
    },
    "tokyu": {
        "id": "tokyu",
        "name": "東急電鉄（東急HD含む）",
        "top_url": "https://www.tokyu.co.jp/",
        "official_domains": ["tokyu.co.jp"],
        "urls": [
            "https://www.tokyu.co.jp/company/news/",
            "https://www.tokyu.co.jp/information/",
            "https://www.tokyu.co.jp/",
        ],
        "query": "東急電鉄 OR 東急",
    },
    "keikyu": {
        "id": "keikyu",
        "name": "京浜急行電鉄",
        "top_url": "https://www.keikyu.co.jp/",
        "official_domains": ["keikyu.co.jp"],
        "urls": [
            "https://www.keikyu.co.jp/company/news/",
            "https://www.keikyu.co.jp/report/",
            "https://www.keikyu.co.jp/",
        ],
        "query": "京浜急行電鉄 OR 京急",
    },
    "sotetsu": {
        "id": "sotetsu",
        "name": "相模鉄道（相鉄HD含む）",
        "top_url": "https://www.sotetsu.co.jp/",
        "official_domains": ["sotetsu.co.jp"],
        "urls": [
            "https://www.sotetsu.co.jp/pressrelease/",
            "https://www.sotetsu.co.jp/news/",
            "https://www.sotetsu.co.jp/",
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
    "osaka-metro": {
        "id": "osaka-metro",
        "name": "大阪メトロ (Osaka Metro)",
        "top_url": "https://subway.osakametro.co.jp/",
        "official_domains": ["osakametro.co.jp"],
        "urls": [
            "https://subway.osakametro.co.jp/news/news_release/",
            "https://subway.osakametro.co.jp/news/",
            "https://subway.osakametro.co.jp/",
        ],
        "query": "大阪メトロ OR \"Osaka Metro\"",
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
    "hankyu": {
        "id": "hankyu",
        "name": "阪急電鉄",
        "top_url": "https://www.hankyu.co.jp/",
        "official_domains": ["hankyu.co.jp", "hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hankyu.co.jp/company/news/index.html",
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hankyu.co.jp/",
        ],
        "query": "阪急電鉄 OR 阪急電車",
    },
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
    # --- 近鉄グループ（18社：完全指定順） ---
    "kintetsu-ghd": {
        "id": "kintetsu-ghd",
        "name": "近鉄GHD",
        "top_url": "https://www.kintetsu-g-hd.co.jp/",
        "official_domains": ["kintetsu-g-hd.co.jp"],
        "urls": [
            "https://www.kintetsu-g-hd.co.jp/news-kg/",
            "https://www.kintetsu-g-hd.co.jp/news-hd/",
            "https://www.kintetsu-g-hd.co.jp/",
        ],
        "query": "近鉄グループホールディングス OR 近鉄GHD",
    },
    "kintetsu-railway": {
        "id": "kintetsu-railway",
        "name": "近畿日本鉄道",
        "top_url": "https://www.kintetsu.co.jp/",
        "official_domains": ["kintetsu.co.jp"],
        "urls": [
            "https://www.kintetsu.co.jp/all_news/whatsnew.html",
            "https://www.kintetsu.co.jp/all_info/whatsnew.html",
            "https://www.kintetsu.co.jp/",
        ],
        "query": "近畿日本鉄道 OR 近鉄電車",
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
            "https://www.d-kintetsu.co.jp/corporate/ir/whatsnew.html",
            "https://www.d-kintetsu.co.jp/corporate/",
            "https://www.d-kintetsu.co.jp/",
        ],
        "query": '"近鉄百貨店"',
    },
    "kintetsu-retailing": {
        "id": "kintetsu-retailing",
        "name": "近鉄リテーリング",
        "top_url": "https://knt-rt.co.jp/",
        "official_domains": ["knt-rt.co.jp"],
        "urls": [
            "https://knt-rt.co.jp/news/",
            "https://knt-rt.co.jp/",
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
            "https://www.kinsho-store.co.jp/",
        ],
        "query": '"近商ストア"',
    },
    # ★ 近鉄・都ホテルズ：「PRESS RELEASE」と「NEWS / お知らせ」の両方を確実に巡回
    "miyako-hotels": {
        "id": "miyako-hotels",
        "name": "近鉄・都ホテルズ",
        "top_url": "https://www.miyakohotels.ne.jp/",
        "official_domains": ["miyakohotels.ne.jp"],
        "urls": [
            "https://www.miyakohotels.ne.jp/newsrelease/",
            "https://www.miyakohotels.ne.jp/information/",
            "https://www.miyakohotels.ne.jp/",
        ],
        "query": '"近鉄・都ホテルズ" OR "都ホテルズ＆リゾーツ" OR "都ホテル"',
    },
    "knt-ct": {
        "id": "knt-ct",
        "name": "KNT-CTホールディングス",
        "top_url": "https://www.kntcthd.co.jp/",
        "official_domains": ["kntcthd.co.jp"],
        "urls": [
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
        "top_url": "https://www.club-tourism.co.jp/",
        "official_domains": ["club-tourism.co.jp", "club-t.com"],
        "urls": [
            "https://www.club-tourism.co.jp/jpn/press/",
            "https://www.club-tourism.co.jp/jpn/",
            "https://www.club-t.com/ct/news/",
        ],
        "query": '"クラブツーリズム"',
    },
    "kaiyukan": {
        "id": "kaiyukan",
        "name": "海遊館",
        "top_url": "https://www.kaiyukan.com/",
        "official_domains": ["kaiyukan.com"],
        "urls": [
            "https://www.kaiyukan.com/topics/",
            "https://www.kaiyukan.com/",
        ],
        "query": '"海遊館"',
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
            "https://www.sanco.co.jp/allnews/",
            "https://www.sanco.co.jp/other/newsrelease/",
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
    "tobu", "seibu", "keisei", "tokyo-metro", "keio", "odakyu",
    "tokyu", "keikyu", "sotetsu", "meitetsu",
    "kintetsu-ghd", "kintetsu-railway",
    "nankai", "keihan", "osaka-metro", "hanshin", "hankyu", "hankyu-hanshin-hd", "nishitetsu"
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
    "kaiyukan",
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
    "prtimes.jp": "PR TIMES",
    "atpress.ne.jp": "@Press",
    "reuters.com": "ロイター",
    "bloomberg.co.jp": "ブルームバーグ",
    "fnn.jp": "FNNプライムオンライン",
    "tv-asahi.co.jp": "テレ朝news",
    "tbs.co.jp": "TBS NEWS DIG",
    "ntv.co.jp": "日テレNEWS",
}

GENERIC_LINK_TEXTS = {
    "一覧を見る", "ニュース一覧を見る", "お知らせ一覧を見る", "過去の一覧を見る",
    "リリース一覧を見る", "一覧はこちら", "一覧へ", "一覧", "詳しく見る",
    "詳しくはこちら", "詳細を見る", "詳細はこちら", "詳細", "こちら", "もっと見る",
    "記事を読む", "続きを読む", "pdfを見る", "pdfを開く", "pdfダウンロード",
    "pdf", "ダウンロード", "リンク", "次へ", "前へ", "トップへ戻る", "ホーム",
    "企業情報", "サイトマップ", "ニュースリリース", "お知らせ", "新着情報",
    "営業時間", "営業カレンダー", "本日のパーク情報", "本日の営業時間",
    "最新のニュース", "最新ニュース", "新着ニュース", "プレスリリース", "新着情報一覧"
}

zen_to_han = str.maketrans("０１２３４５６７８９", "0123456789")


# ==========================================
# 2. 自動エンコーディング解析＆全範囲日付抽出
# ==========================================
def decode_html_bytes(raw_bytes, url=""):
    enc_candidates = []
    if any(d in url for d in ["westjr.co.jp", "kintetsu", "nankai.co.jp", "hanshin.co.jp", "hankyu.co.jp", "keihan.co.jp", "jr-central.co.jp"]):
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


def parse_date_text(raw_text, current_year, prefer_first=False):
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = html.unescape(text).translate(zen_to_han)

    # 1. 令和表記
    m_reiwa = list(re.finditer(r"令和\s*([0-9]+|元)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日", text))
    if m_reiwa:
        match_item = m_reiwa[0] if prefer_first else m_reiwa[-1]
        y_val = 1 if match_item.group(1) == "元" else int(match_item.group(1))
        try:
            return datetime.date(2018 + y_val, int(match_item.group(2)), int(match_item.group(3)))
        except ValueError:
            pass

    # 2. 平成表記
    m_heisei = list(re.finditer(r"平成\s*([0-9]+|元)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日", text))
    if m_heisei:
        match_item = m_heisei[0] if prefer_first else m_heisei[-1]
        y_val = 1 if match_item.group(1) == "元" else int(match_item.group(1))
        try:
            return datetime.date(1988 + y_val, int(match_item.group(2)), int(match_item.group(3)))
        except ValueError:
            pass

    # 3. 西暦表記（2026/10/22, 2026.10.22, 2026-10-22, 2026年10月22日）
    m_seireki = list(re.finditer(r"((?:19|20)\d{2})\s*[年\./\-]\s*([0-9]{1,2})\s*[月\./\-]\s*([0-9]{1,2})\s*日?", text))
    if m_seireki:
        match_item = m_seireki[0] if prefer_first else m_seireki[-1]
        try:
            return datetime.date(int(match_item.group(1)), int(match_item.group(2)), int(match_item.group(3)))
        except ValueError:
            pass

    # 4. 月日のみ
    if re.search(r"(?:19|20)\d{2}", text):
        return None

    m_md = list(re.finditer(r"(?<!\d)(1[0-2]|0?[1-9])\s*[月\./\-]\s*(3[01]|[12][0-9]|0?[1-9])\s*日?(?!\d)", text))
    if m_md:
        match_item = m_md[0] if prefer_first else m_md[-1]
        try:
            return datetime.date(current_year, int(match_item.group(1)), int(match_item.group(2)))
        except ValueError:
            pass

    return None


def clean_leading_date(title):
    if re.match(r"^(?:202\d|令和\s*(?:\d+|元))年度", title):
        return title
    title = re.sub(r"^(?:(?:19|20)\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2})\s*[:：|｜・\s]*", "", title)
    title = re.sub(r"^(?:(?:19|20)\d{2}年\d{1,2}月\d{1,2}日|令和\s*(?:\d+|元)年\d{1,2}月\d{1,2}日)\s*[:：|｜・\s]+", "", title)
    return title.strip()


def clean_extracted_title(raw_title, company_info):
    t = re.sub(r"<[^>]+>", " ", raw_title)
    t = html.unescape(t)
    t = clean_leading_date(t)
    t = re.sub(r"^(?:東急電鉄|東京メトロ|京急電鉄|近畿日本鉄道|プレスリリース|ニュースリリース|お知らせ|PRESS\s*RELEASE|NEWS|重要|電鉄|グループ)\s*", "", t.strip(), flags=re.IGNORECASE)
    t = clean_leading_date(t)
    if company_info["id"] == "nara-kotsu":
        t = re.sub(r'^(?:総合路線バス|路線バス|臨時バス|高速バス|貸切バス|観光バス)+', '', t).strip()
    return re.sub(r"\s+", " ", t).strip()


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
# 3. 実証済み高精度スクレイピング（自動再探索リカバリー付き）
# ==========================================
def fetch_url_html(url, referer, headers, ctx):
    try:
        h = dict(headers)
        if referer:
            h["Referer"] = referer
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as res:
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
        return html_text, final_url
    except Exception:
        return "", url


def parse_releases_from_html(html_text, final_base_url, company_info, cutoff_date, today, current_year, seen_urls):
    """
    以前の安定バージョンで全社が正常に拾えていた全走査方式を完全復元。
    東急などの「リンク内包型」も同時にキャッチできるよう安全に拡張。
    """
    results = []
    allowed_domains = company_info.get("official_domains", [])

    # RSS/Feed対応
    if "<rss" in html_text or "<feed" in html_text or "<rdf:RDF" in html_text:
        for item_xml in re.findall(r"<(?:item|entry)>(.*?)</(?:item|entry)>", html_text, flags=re.DOTALL):
            t_m = re.search(r"<title>(.*?)</title>", item_xml, flags=re.DOTALL)
            l_m = re.search(r"<link(?:>|\s+[^>]*?href=[\"']([^\"']+)[\"'])", item_xml, flags=re.DOTALL)
            d_m = re.search(r"<(?:pubDate|dc:date|updated)>(.*?)</(?:pubDate|dc:date|updated)>", item_xml, flags=re.DOTALL)
            
            if t_m:
                t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t_m.group(1)).strip()
                l = ""
                if l_m:
                    l = l_m.group(1).strip() if l_m.group(1) else re.search(r"<link>(.*?)</link>", item_xml, flags=re.DOTALL).group(1).strip()
                if not l:
                    continue
                l = urllib.parse.urljoin(final_base_url, l)

                d_str = d_m.group(1) if d_m else ""
                item_date = parse_date_text(d_str, current_year)
                if item_date and (cutoff_date <= item_date <= today) and l not in seen_urls:
                    clean_t = clean_extracted_title(t, company_info)
                    if any(ng in clean_t for ng in ["営業時間", "営業カレンダー", "最新のニュース"]):
                        continue
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
        return results

    clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    # 以前のバージョンと同じ全体走査方式
    a_matches = list(
        re.finditer(
            r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            clean_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )

    for m in a_matches:
        raw_href = m.group(1).strip().strip("'\"").replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
        if not raw_href or raw_href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue

        full_url = urllib.parse.urljoin(final_base_url, raw_href)
        if full_url in seen_urls:
            continue

        if re.search(r'/(?:20[01]\d|202[0-3])/', full_url):
            continue

        parsed_u = urllib.parse.urlparse(full_url)
        if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
            continue

        if company_info["id"] == "hanshin" and "hankyu-hanshin.co.jp" in parsed_u.netloc.lower():
            surrounding_check = clean_html[max(0, m.start() - 200) : min(len(clean_html), m.end() + 200)]
            if "阪急" in surrounding_check and "阪神" not in surrounding_check:
                continue

        inside_html = m.group(2)
        start_pos, end_pos = m.start(), m.end()

        # ★ 日付判定（他社を壊さず東急も拾える安全な2段階判定）：
        # 1. リンク内包日付（東急などの構造）
        found_date = parse_date_text(inside_html, current_year)
        # 2. リンク手前（メトロ、近鉄、南海、JR東海等のdt/dd、tr/td構造）
        if not found_date:
            before_html = clean_html[max(0, start_pos - 450) : start_pos]
            found_date = parse_date_text(before_html, current_year, prefer_first=False)
        # 3. リンク直後
        if not found_date:
            after_html = clean_html[end_pos : min(len(clean_html), end_pos + 300)]
            found_date = parse_date_text(after_html, current_year, prefer_first=True)

        if not found_date or not (cutoff_date <= found_date <= today):
            continue

        surrounding = clean_html[max(0, start_pos - 400) : min(len(clean_html), end_pos + 300)]
        clean_t = clean_extracted_title(inside_html, company_info)

        if clean_t in GENERIC_LINK_TEXTS or len(clean_t) < 5 or clean_t == "最新のニュース":
            h_m = re.findall(r"<h[1-5][^>]*>(.*?)</h[1-5]>", surrounding, flags=re.DOTALL | re.IGNORECASE)
            if h_m:
                clean_t = clean_extracted_title(h_m[-1], company_info)
            else:
                comb = re.sub(r"<[^>]+>", " ", surrounding)
                comb = html.unescape(comb)
                lines = [line.strip() for line in comb.split() if len(line.strip()) > 6 and line.strip() not in GENERIC_LINK_TEXTS and line.strip() != "最新のニュース"]
                if lines:
                    clean_t = clean_extracted_title(lines[0], company_info)
                else:
                    continue

        if clean_t in GENERIC_LINK_TEXTS or len(clean_t) < 5 or clean_t == "最新のニュース":
            continue

        if any(bad in clean_t for bad in ['="', "='", "class=", "id=", "style=", "headerMenu", "<", ">"]):
            continue

        if any(ng in clean_t for ng in ["営業時間", "営業カレンダー", "本日の営業時間"]):
            continue

        pdf_m = re.search(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', surrounding, re.IGNORECASE)
        detected_pdf = urllib.parse.urljoin(final_base_url, pdf_m.group(1).strip()) if pdf_m else None

        page_url = full_url
        pdf_url = detected_pdf

        if full_url.lower().split('?')[0].endswith(".pdf"):
            pdf_url = full_url
            page_m = re.search(r'href=["\']([^"\']*(?:page_|article/|detail/)[^"\']*\.html)["\']', surrounding, re.IGNORECASE)
            if page_m:
                page_url = urllib.parse.urljoin(final_base_url, page_m.group(1).strip())

        if company_info["id"] == "jr-west" and not pdf_url and page_url.endswith(".html"):
            try:
                sub_req = urllib.request.Request(page_url, headers=headers)
                with urllib.request.urlopen(sub_req, context=ctx, timeout=3) as sub_res:
                    sub_b = sub_res.read()
                    sub_h = decode_html_bytes(sub_b, url=page_url)
                    inner_pdf_m = re.search(r'href=["\']([^"\']+\.pdf)["\']', sub_h, re.IGNORECASE)
                    if inner_pdf_m:
                        pdf_url = urllib.parse.urljoin(page_url, inner_pdf_m.group(1).strip())
            except Exception:
                pass

        seen_urls.add(full_url)
        is_pdf = bool(pdf_url or full_url.lower().split('?')[0].endswith(".pdf"))

        results.append({
            "date": found_date,
            "type": "公式発表",
            "title": clean_t[:130],
            "url": page_url,
            "pdf_url": pdf_url,
            "source": company_info["name"] + " 公式HP",
            "is_pdf": is_pdf,
        })

    return results


def fetch_official_releases(company_info, max_days_back=21):
    """
    公式発表を取得。
    「なし」となった場合は自律修復機能が自動発動し、トップページや
    サイト内インデックスから最新リリースを再探索して取得
    """
    results = []
    seen_urls = set()
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)
    current_year = today.year

    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ja,ja-JP;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Upgrade-Insecure-Requests": "1",
    }

    # 1. 登録済みURLを巡回
    for url in company_info["urls"]:
        html_text, final_url = fetch_url_html(url, company_info.get("top_url", url), headers, ctx)
        if html_text:
            items = parse_releases_from_html(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)
            results.extend(items)

    # ★ 2. 自動修復機能（ステップ1）：結果が0件の場合、トップページから生リンクを自動再確認
    if not results and company_info.get("top_url"):
        top_html, final_top_url = fetch_url_html(company_info["top_url"], "", headers, ctx)
        if top_html:
            direct_items = parse_releases_from_html(top_html, final_top_url, company_info, cutoff_date, today, current_year, seen_urls)
            results.extend(direct_items)

            if not results:
                pat = r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(?:.*?)(?:ニュースリリース|プレスリリース|広報発表|新着情報|NEWS|PRESS\s*RELEASE)(?:.*?)</a>'
                cand_urls = []
                for m in re.finditer(pat, top_html, flags=re.IGNORECASE | re.DOTALL):
                    cand_href = m.group(1).strip()
                    if cand_href and not cand_href.startswith(("javascript:", "#")):
                        cand_full = urllib.parse.urljoin(final_top_url, cand_href)
                        if cand_full not in company_info["urls"] and cand_full not in cand_urls:
                            cand_urls.append(cand_full)

                for target_url in cand_urls[:3]:
                    sub_html, sub_final = fetch_url_html(target_url, final_top_url, headers, ctx)
                    if sub_html:
                        sub_items = parse_releases_from_html(sub_html, sub_final, company_info, cutoff_date, today, current_year, seen_urls)
                        results.extend(sub_items)

    # ★ 3. 自動修復機能（ステップ2）：WAF制限等で依然0件の場合、公式ドメインインデックスから救済取得
    if not results:
        main_domain = company_info["official_domains"][0]
        rescue_query = f"site:{main_domain} {company_info['name']}"
        encoded_q = urllib.parse.quote(rescue_query)
        rescue_rss = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&mkt=ja-JP"
        try:
            req = urllib.request.Request(rescue_rss, headers=headers)
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
                    if main_domain not in l or l in seen_urls:
                        continue
                    i_date = None
                    if d_el is not None and d_el.text:
                        try:
                            dt = email.utils.parsedate_to_datetime(d_el.text).astimezone(JST)
                            i_date = dt.date()
                        except Exception:
                            pass
                    if i_date and (cutoff_date <= i_date <= today):
                        clean_t = clean_extracted_title(t_el.text or "", company_info)
                        seen_urls.add(l)
                        results.append({
                            "date": i_date,
                            "type": "公式発表",
                            "title": clean_t,
                            "url": l,
                            "pdf_url": l if l.lower().split('?')[0].endswith(".pdf") else None,
                            "source": company_info["name"] + " 公式発表",
                            "is_pdf": l.lower().split('?')[0].endswith(".pdf"),
                        })
        except Exception:
            pass

    return results


def fetch_general_news(query, company_name, max_days_back=21):
    results = []
    encoded_q = urllib.parse.quote(query)
    rss_url = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&mkt=ja-JP"
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)

    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

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
            link = (link_el.text or "").strip()
            pubdate_str = pubdate_el.text if pubdate_el is not None else ""
            desc = desc_el.text or ""

            if not link or "news.google.com" in link:
                continue

            if "bing.com" in link:
                u_match = re.search(r'[?&]u=a1([a-zA-Z0-9_\-]+)', link)
                if u_match:
                    try:
                        b64_str = u_match.group(1)
                        b64_str += '=' * (-len(b64_str) % 4)
                        decoded_bytes = base64.urlsafe_b64decode(b64_str)
                        real_url = decoded_bytes.decode('utf-8', errors='ignore')
                        if real_url.startswith("http"):
                            link = real_url
                    except Exception:
                        pass

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

            clean_title = raw_title.strip()
            clean_desc = re.sub(r"<[^>]+>", " ", desc)
            clean_desc = html.unescape(clean_desc)
            clean_desc = re.sub(r"\s+", " ", clean_desc).strip()

            combined_text = (clean_title + " " + clean_desc).lower()

            noise_keywords = [
                "招待券", "プレゼント", "懸賞", "合唱団", "定期演奏会",
                "警察weekly", "県警weekly", "現行犯逮捕", "酒酔い運転", "ひき逃げ",
                "安全運転管理者", "死亡事故", "容疑で逮捕", "書類送検"
            ]
            if any(ng in combined_text for ng in noise_keywords):
                continue

            strict_companies = ["奈良交通", "近鉄バス", "三重交通", "海遊館", "志摩スペイン村", "あべのハルカス美術館"]
            if company_name in strict_companies:
                if company_name not in clean_title:
                    continue
            else:
                clean_comp = company_name.replace("（", "").replace("）", "")
                comp_keywords = [clean_comp]
                if "・" in clean_comp:
                    comp_keywords.extend(clean_comp.split("・"))
                if not any(kw.lower() in combined_text for kw in comp_keywords):
                    continue

            summary = clean_news_summary(clean_desc, clean_title, company_name)

            source_name = ""
            for child in item:
                tag_name = child.tag.split("}")[-1].lower()
                if "source" in tag_name:
                    txt = (child.text or "").strip()
                    if txt and txt.lower() not in ["bing", "bing.com"]:
                        source_name = txt
                        break

            if not source_name or source_name.lower() in ["bing", "bing.com"]:
                if " - " in clean_title:
                    parts = clean_title.rsplit(" - ", 1)
                    cand = parts[1].strip()
                    clean_title = parts[0].strip()
                    if cand and cand.lower() not in ["bing", "bing.com"]:
                        source_name = cand

            parsed_url = urllib.parse.urlparse(link)
            domain = parsed_url.netloc.lower().replace("www.", "")

            for domain_key, media_label in MEDIA_NAME_MAP.items():
                if domain_key in domain:
                    source_name = media_label
                    break

            if not source_name or source_name.lower() in ["bing", "bing.com"]:
                source_name = domain if "bing" not in domain else "ニュース報道"

            results.append({
                "date": item_date,
                "type": "ニュース（一般サイト）",
                "title": clean_title,
                "summary": summary,
                "url": link,
                "pdf_url": None,
                "source": source_name,
                "is_pdf": False,
            })
    except Exception:
        pass

    return results


# ==========================================
# 4. 社別データキャッシュエンジン（キャッシュ完全リセット）
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_single_company_data(company_dict, max_days_back=21, cache_version="v2026_keisei_fixed_rock_solid_v2"):
    official = fetch_official_releases(company_dict, max_days_back=max_days_back)
    general = []
    if "query" in company_dict:
        general = fetch_general_news(company_dict["query"], company_dict["name"], max_days_back=max_days_back)

    combined = list(official)
    seen_urls = {item["url"] for item in official}
    for g in general:
        if g["url"] not in seen_urls:
            seen_urls.add(g["url"])
            combined.append(g)

    return combined


# ==========================================
# 5. アプリ全体のボタンスタイル定義（濃紺 #1e3a8a 統一）
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
# 6. サイドバー操作パネル
# ==========================================
today = datetime.datetime.now(JST).date()

if "date_range" not in st.session_state:
    st.session_state.date_range = (today - datetime.timedelta(days=2), today)
if "selected_period_days" not in st.session_state:
    st.session_state.selected_period_days = 3

with st.sidebar:
    st.header("⚙️ 設定")

    st.write("**1. 対象期間**")

    is_3days = st.session_state.selected_period_days == 3
    type_3 = "primary" if is_3days else "secondary"
    type_7 = "secondary" if is_3days else "primary"

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("📅 3日間", key="btn_period_3", type=type_3, use_container_width=True):
            st.session_state.selected_period_days = 3
            st.session_state.date_range = (today - datetime.timedelta(days=2), today)
            st.rerun()
    with btn_col2:
        if st.button("📅 7日間", key="btn_period_7", type=type_7, use_container_width=True):
            st.session_state.selected_period_days = 7
            st.session_state.date_range = (today - datetime.timedelta(days=6), today)
            st.rerun()

    date_range = st.date_input(
        "対象期間を選択",
        value=st.session_state.date_range,
        max_value=today,
        label_visibility="collapsed",
    )
    if len(date_range) == 2:
        start_date, end_date = date_range
        st.session_state.date_range = (start_date, end_date)
        diff = (end_date - start_date).days + 1
        if diff == 3 and end_date == today:
            st.session_state.selected_period_days = 3
        elif diff == 7 and end_date == today:
            st.session_state.selected_period_days = 7
    else:
        start_date = end_date = date_range[0]

    if st.session_state.hidden_companies:
        if st.button("👁️ すべての会社の記事を再表示", use_container_width=True):
            st.session_state.hidden_companies.clear()
            st.rerun()

    st.markdown("---")
    st.write("**2. 公式発表・ニュース**")

    btn_type_off = "primary" if st.session_state.show_official else "secondary"
    btn_type_news = "primary" if st.session_state.show_news else "secondary"

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        if st.button("公式発表", key="btn_toggle_official", type=btn_type_off, use_container_width=True):
            st.session_state.show_official = not st.session_state.show_official
            if not st.session_state.show_official and not st.session_state.show_
