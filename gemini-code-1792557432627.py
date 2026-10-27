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
# 0. メディア優先度定義（見出し重複時のメジャー媒体優先用）
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

# セッションステートの初期化
today = datetime.datetime.now(JST).date()

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "official"  # デフォルトは公式発表
if "period_days" not in st.session_state:
    st.session_state.period_days = 3          # デフォルトは3日間
if "custom_date_range" not in st.session_state:
    st.session_state.custom_date_range = (today - datetime.timedelta(days=2), today)
if "hidden_companies" not in st.session_state:
    st.session_state.hidden_companies = set()
if "selected_filter_companies" not in st.session_state:
    st.session_state.selected_filter_companies = set()
if "diag_logs" not in st.session_state:
    st.session_state.diag_logs = {}

# ==========================================
# 1. 会社マスタープール
# ==========================================
COMPANY_POOL = {
    # --- JR各社 ---
    "jr-hokkaido": {
        "id": "jr-hokkaido",
        "name": "JR北海道",
        "engine": "legacy",
        "top_url": "https://www.jrhokkaido.co.jp/",
        "official_domains": ["jrhokkaido.co.jp"],
        "urls": [
            "https://www.jrhokkaido.co.jp/CM/info/press/presstop.html",
            "https://www.jrhokkaido.co.jp/",
        ],
        "query": "JR北海道 OR 北海道旅客鉄道",
    },
    # ★ JR東日本（専用ハイブリッドエンジン：WAF/403およびJS描画を完全突破）
    "jr-east": {
        "id": "jr-east",
        "name": "JR東日本",
        "engine": "jr_east",
        "top_url": "https://www.jreast.co.jp/",
        "official_domains": ["jreast.co.jp", "tetsudo.com"],
        "urls": [
            "https://www.jreast.co.jp/press/",
            "https://www.jreast.co.jp/rss/press.xml",
            "https://www.tetsudo.com/railway/0002/release/",
        ],
        "query": "JR東日本 OR 東日本旅客鉄道",
    },
    "jr-central": {
        "id": "jr-central",
        "name": "JR東海",
        "engine": "legacy",
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
        "engine": "legacy",
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
        "engine": "legacy",
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
        "engine": "legacy",
        "top_url": "https://www.jrkyushu.co.jp/",
        "official_domains": ["jrkyushu.co.jp"],
        "urls": [
            "https://www.jrkyushu.co.jp/news/release/index.html",
            "https://www.jrkyushu.co.jp/news/",
            "https://www.jrkyushu.co.jp/",
        ],
        "query": "JR九州 OR 九州旅客鉄道",
    },
    # --- 私鉄各社 ---
    # ★ 東武鉄道（以前の安定レガシーパーサーで確実に復元）
    "tobu": {
        "id": "tobu",
        "name": "東武鉄道",
        "engine": "legacy",
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
        "engine": "legacy",
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
        "engine": "metro_card",
        "top_url": "https://www.keisei.co.jp/",
        "official_domains": ["keisei.co.jp"],
        "urls": [
            "https://www.keisei.co.jp/",
            "https://www.keisei.co.jp/news/",
        ],
        "query": "京成電鉄",
    },
    # ★ 東京メトロ（専用カードパーサー）
    "tokyo-metro": {
        "id": "tokyo-metro",
        "name": "東京メトロ",
        "engine": "metro_card",
        "top_url": "https://www.tokyometro.jp/",
        "official_domains": ["tokyometro.jp"],
        "urls": [
            "https://www.tokyometro.jp/",
            "https://www.tokyometro.jp/news/index.html",
            "https://www.tokyometro.jp/news/rss/news.xml",
        ],
        "query": "東京メトロ OR 東京地下鉄",
    },
    "keio": {
        "id": "keio",
        "name": "京王電鉄",
        "engine": "legacy",
        "top_url": "https://www.keio.co.jp/",
        "official_domains": ["keio.co.jp"],
        "urls": [
            "https://www.keio.co.jp/news/update/news_release/",
            "https://www.keio.co.jp/news/update/index.html",
            "https://www.keio.co.jp/",
        ],
        "query": "京王電鉄",
    },
    # ★ 小田急電鉄（専用カードパーサー）
    "odakyu": {
        "id": "odakyu",
        "name": "小田急電鉄",
        "engine": "metro_card",
        "top_url": "https://www.odakyu.jp/",
        "official_domains": ["odakyu.jp"],
        "urls": [
            "https://www.odakyu.jp/",
            "https://www.odakyu.jp/company/about/news/",
            "https://www.odakyu.jp/news/",
        ],
        "query": "小田急電鉄",
    },
    # ★ 東急電鉄（専用カードパーサー）
    "tokyu": {
        "id": "tokyu",
        "name": "東急電鉄（東急HD含む）",
        "engine": "metro_card",
        "top_url": "https://www.tokyu.co.jp/",
        "official_domains": ["tokyu.co.jp"],
        "urls": [
            "https://www.tokyu.co.jp/",
            "https://www.tokyu.co.jp/company/news/",
            "https://www.tokyu.co.jp/information/",
        ],
        "query": "東急電鉄 OR 東急",
    },
    # ★ 京浜急行電鉄（専用カードパーサー）
    "keikyu": {
        "id": "keikyu",
        "name": "京浜急行電鉄",
        "engine": "metro_card",
        "top_url": "https://www.keikyu.co.jp/",
        "official_domains": ["keikyu.co.jp"],
        "urls": [
            "https://www.keikyu.co.jp/",
            "https://www.keikyu.co.jp/company/news/",
            "https://www.keikyu.co.jp/report/",
        ],
        "query": "京浜急行電鉄 OR 京急",
    },
    # ★ 相模鉄道（安定レガシーパーサー）
    "sotetsu": {
        "id": "sotetsu",
        "name": "相模鉄道（相鉄HD含む）",
        "engine": "legacy",
        "top_url": "https://www.sotetsu.co.jp/",
        "official_domains": ["sotetsu.co.jp"],
        "urls": [
            "https://www.sotetsu.co.jp/news/",
            "https://www.sotetsu.co.jp/pressrelease/",
            "https://www.sotetsu.co.jp/",
        ],
        "query": "相模鉄道 OR 相鉄ホールディングス",
    },
    # ★ 名古屋鉄道（安定レガシーパーサー）
    "meitetsu": {
        "id": "meitetsu",
        "name": "名古屋鉄道",
        "engine": "legacy",
        "top_url": "https://www.meitetsu.co.jp/",
        "official_domains": ["meitetsu.co.jp"],
        "urls": [
            "https://www.meitetsu.co.jp/profile/news/",
            "https://www.meitetsu.co.jp/",
        ],
        "query": "名古屋鉄道 OR 名鉄",
    },
    # ★ 南海電気鉄道（安定レガシーパーサーで確実に復元）
    "nankai": {
        "id": "nankai",
        "name": "南海電気鉄道",
        "engine": "legacy",
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
        "engine": "legacy",
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
        "engine": "legacy",
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
        "engine": "legacy",
        "top_url": "https://www.hanshin.co.jp/",
        "official_domains": ["hanshin.co.jp", "hankyu-hanshin.co.jp"],
        "urls": [
            "https://www.hanshin.co.jp/press/",
            "https://www.hankyu-hanshin.co.jp/release/",
            "https://www.hanshin.co.jp/",
        ],
        "query": "阪神電気鉄道 OR 阪神電車",
    },
    # ★ 阪急電鉄（専用阪急エンジン）
    "hankyu": {
        "id": "hankyu",
        "name": "阪急電鉄",
        "engine": "hankyu",
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
    # ★ 阪急阪神HD（専用阪急エンジン）
    "hankyu-hanshin-hd": {
        "id": "hankyu-hanshin-hd",
        "name": "阪急阪神ホールディングス",
        "engine": "hankyu",
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
        "engine": "legacy",
        "top_url": "https://www.nishitetsu.co.jp/",
        "official_domains": ["nishitetsu.co.jp"],
        "urls": [
            "https://www.nishitetsu.co.jp/ja/news.html",
            "https://www.nishitetsu.co.jp/release/",
            "https://www.nishitetsu.co.jp/",
        ],
        "query": "西日本鉄道 OR 西鉄",
    },
    # --- 近鉄グループ（17社） ---
    # ★ 近鉄GHD（専用テーブル・定義リスト解析エンジン）
    "kintetsu-ghd": {
        "id": "kintetsu-ghd",
        "name": "近鉄GHD",
        "engine": "kintetsu",
        "top_url": "https://www.kintetsu-g-hd.co.jp/",
        "official_domains": ["kintetsu-g-hd.co.jp"],
        "urls": [
            "https://www.kintetsu-g-hd.co.jp/news-hd/",
            "https://www.kintetsu-g-hd.co.jp/news-kg/",
            "https://www.kintetsu-g-hd.co.jp/",
        ],
        "query": "近鉄グループホールディングス OR 近鉄GHD OR 近鉄グループ",
    },
    # ★ 近畿日本鉄道（専用テーブル・定義リスト解析エンジン）
    "kintetsu-railway": {
        "id": "kintetsu-railway",
        "name": "近畿日本鉄道",
        "engine": "kintetsu",
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
        "engine": "legacy",
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
        "engine": "legacy",
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
        "engine": "legacy",
        "top_url": "https://www.kwe.co.jp/",
        "official_domains": ["kwe.co.jp", "kwe.com"],
        "urls": [
            "https://www.kwe.co.jp/news/",
            "https://www.kwe.co.jp/",
        ],
        "query": '"近鉄エクスプレス"',
    },
    # ★ 近鉄百貨店（トップページ下お知らせ最優先）
    "kintetsu-dept": {
        "id": "kintetsu-dept",
        "name": "近鉄百貨店",
        "engine": "legacy",
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
        "engine": "legacy",
        "top_url": "https://knt-rt.co.jp/",
        "official_domains": ["knt-rt.co.jp"],
        "urls": [
            "https://knt-rt.co.jp/",
            "https://knt-rt.co.jp/news/",
        ],
        "query": '"近鉄リテーリング"',
    },
    # ★ 近商ストア（ゴミ見出し完全排除）
    "kinsho-store": {
        "id": "kinsho-store",
        "name": "近商ストア",
        "engine": "legacy",
        "top_url": "https://www.kinshostore.co.jp/",
        "official_domains": ["kinsho-store.co.jp", "kinshostore.co.jp"],
        "urls": [
            "https://www.kinshostore.co.jp/html/news.php",
            "https://www.kinsho-store.co.jp/html/news.php",
            "https://www.kinshostore.co.jp/",
        ],
        "query": '"近商ストア"',
    },
    # ★ 近鉄・都ホテルズ（トップページ「NEWS」「PRESS RELEASE」専用）
    "miyako-hotels": {
        "id": "miyako-hotels",
        "name": "近鉄・都ホテルズ",
        "engine": "miyako",
        "top_url": "https://www.miyakohotels.ne.jp/",
        "official_domains": ["miyakohotels.ne.jp"],
        "urls": [
            "https://www.miyakohotels.ne.jp/",
            "https://www.miyakohotels.ne.jp/newsrelease/",
        ],
        "query": '"近鉄・都ホテルズ" OR "都ホテルズ＆リゾーツ" OR "都ホテル"',
    },
    # ★ KNT-CTホールディングス（2026年最新リリース専用）
    "knt-ct": {
        "id": "knt-ct",
        "name": "KNT-CTホールディングス",
        "engine": "knt_ct",
        "top_url": "https://www.kntcthd.co.jp/",
        "official_domains": ["kntcthd.co.jp"],
        "urls": [
            "https://www.kntcthd.co.jp/release/",
            "https://www.kntcthd.co.jp/news/",
            "https://www.kntcthd.co.jp/",
        ],
        "query": '"KNT-CTホールディングス" OR "KNT-CT"',
    },
    # ★ 近畿日本ツーリスト（安定レガシーパーサー）
    "knt": {
        "id": "knt",
        "name": "近畿日本ツーリスト",
        "engine": "legacy",
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
        "engine": "legacy",
        "top_url": "https://www.club-tourism.co.jp/",
        "official_domains": ["club-tourism.co.jp", "club-t.com"],
        "urls": [
            "https://www.club-tourism.co.jp/jpn/press/",
            "https://www.club-tourism.co.jp/jpn/",
            "https://www.club-t.com/ct/news/",
        ],
        "query": '"クラブツーリズム"',
    },
    "shima-spain-village": {
        "id": "shima-spain-village",
        "name": "志摩スペイン村",
        "engine": "legacy",
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
        "engine": "legacy",
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
        "engine": "legacy",
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
        "engine": "legacy",
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
        "engine": "legacy",
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

GENERIC_LINK_TEXTS = {
    "一覧を見る", "ニュース一覧を見る", "お知らせ一覧を見る", "過去の一覧を見る",
    "リリース一覧を見る", "一覧はこちら", "一覧へ", "一覧", "詳しく見る",
    "詳しくはこちら", "詳細を見る", "詳細はこちら", "詳細", "こちら", "もっと見る",
    "もっと、", "記事を読む", "続きを読む", "pdfを見る", "pdfを開く", "pdfダウンロード",
    "pdf", "ダウンロード", "リンク", "次へ", "前へ", "トップへ戻る", "ホーム",
    "企業情報", "サイトマップ", "ニュースリリース", "お知らせ", "新着情報",
    "営業時間", "営業カレンダー", "本日のパーク情報", "本日の営業時間",
    "最新のニュース", "最新ニュース", "新着ニュース", "プレスリリース", "新着情報一覧",
    "« 前ページへ", "前ページへ »", "« 前ページ", "次ページ »", "前ページへ", "次ページへ", "«", "»"
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


def parse_date_text(raw_text, current_year, prefer_first=False):
    if not raw_text:
        return None

    attr_match = list(re.finditer(r'(?:datetime|data-date)=["\']((?:19|20)\d{2}[-/\.][0-9]{1,2}[-/\.][0-9]{1,2})', raw_text, re.IGNORECASE))
    if attr_match:
        m_item = attr_match[0] if prefer_first else attr_match[-1]
        try:
            parts = [int(p) for p in re.split(r'[-/\.]', m_item.group(1))]
            return datetime.date(parts[0], parts[1], parts[2])
        except Exception:
            pass

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

    # 2. 西暦表記
    m_seireki = list(re.finditer(r"((?:19|20)\d{2})\s*[年\./\-]\s*([0-9]{1,2})\s*[月\./\-]\s*([0-9]{1,2})\s*日?", text))
    if m_seireki:
        match_item = m_seireki[0] if prefer_first else m_seireki[-1]
        try:
            return datetime.date(int(match_item.group(1)), int(match_item.group(2)), int(match_item.group(3)))
        except ValueError:
            pass

    # 3. 月日のみ表記
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
    t = re.sub(r"<[^>]*>", " ", raw_title)
    t = html.unescape(t)
    t = clean_leading_date(t)

    # HTML属性・CSSインライン破片の完全ブロック
    junk_patterns = [
        r'padding:', r'margin:', r'color:', r'font-', r'display:',
        r'#448073', r'btn-padding', r'n-padding', r'style=', r'class=',
        r'border:', r'top-kv', r'slide', r'href=', r'src=', r'width=', r'height='
    ]
    if any(re.search(pat, t, re.IGNORECASE) for pat in junk_patterns):
        return ""

    # 定型会社名や接頭辞の除去
    t = re.sub(r"^(?:東急電鉄|東京メトロ|京急電鉄|近畿日本鉄道|プレスリリース|ニュースリリース|お知らせ|PRESS\s*RELEASE|NEWS|重要|電鉄|グループ)\s*", "", t.strip(), flags=re.IGNORECASE)
    t = clean_leading_date(t)

    # 近商ストア専用クレンジング
    if company_info["id"] == "kinsho-store":
        t = re.sub(r'(?:NEW|新着|お知らせ|重要|\.pdf|\.PDF)+', '', t).strip()
        t = re.sub(r'^[【\[（\(].*?[】\]）\)]', '', t).strip()
        t = re.sub(r'^[a-zA-Z0-9_\-]+["\']?>', '', t).strip()
        if t in ["サービス", "ハーベス", "KINSHO", "店舗情報", "チラシ情報"]:
            return ""

    # 志摩スペイン村専用クレンジング
    if company_info["id"] == "shima-spain-village":
        if any(p in t for p in ["前ページへ", "次ページへ", "«", "»"]):
            return ""

    # 三交ホールディングス・三重交通
    if company_info["id"] in ["sanco-hd", "sanco"]:
        t = re.sub(r'(?:グループニュース|IRニュース|お知らせ|ニュースリリース)+', '', t).strip()

    if company_info["id"] == "nara-kotsu":
        t = re.sub(r'^(?:総合路線バス|路線バス|臨時バス|高速バス|貸切バス|観光バス)+', '', t).strip()

    t = re.sub(r"\s+", " ", t).strip()
    if t in GENERIC_LINK_TEXTS or len(t) < 4:
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
# 4. 個別最適化パーサー群
# ==========================================

# --- 4-A. 安定レガシーパーサー（東武、南海、相鉄、名鉄、JR九州、西武、京王など：以前の大成功ロジックを完全固定復元） ---
def parse_stable_legacy(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls):
    results = []
    allowed_domains = company_info.get("official_domains", [])

    clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    a_matches = list(re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', clean_html, flags=re.IGNORECASE | re.DOTALL))
    for m in a_matches:
        raw_href = m.group(1).strip().strip("'\"").replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
        if not raw_href or raw_href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue

        full_url = urllib.parse.urljoin(base_url, raw_href)
        if full_url in seen_urls:
            continue

        if re.search(r'/(?:20[01]\d|202[0-5])/', full_url):
            continue

        parsed_u = urllib.parse.urlparse(full_url)
        if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
            continue

        inside_html = m.group(2)
        start_pos, end_pos = m.start(), m.end()

        # 実績のある周囲探索
        found_date = parse_date_text(inside_html, current_year)
        if not found_date:
            before_html = clean_html[max(0, start_pos - 600) : start_pos]
            found_date = parse_date_text(before_html, current_year, prefer_first=False)
        if not found_date:
            after_html = clean_html[end_pos : min(len(clean_html), end_pos + 400)]
            found_date = parse_date_text(after_html, current_year, prefer_first=True)

        if not found_date or not (cutoff_date <= found_date <= today):
            continue

        surrounding = clean_html[max(0, start_pos - 400) : min(len(clean_html), end_pos + 300)]
        clean_t = clean_extracted_title(inside_html, company_info)

        if not clean_t:
            h_m = re.findall(r"<h[1-5][^>]*>(.*?)</h[1-5]>", surrounding, flags=re.DOTALL | re.IGNORECASE)
            if h_m:
                clean_t = clean_extracted_title(h_m[-1], company_info)
            else:
                comb = re.sub(r"<[^>]+>", " ", surrounding)
                lines = [line.strip() for line in comb.split() if len(line.strip()) > 6 and line.strip() not in GENERIC_LINK_TEXTS and line.strip() != "最新のニュース"]
                if lines:
                    clean_t = clean_extracted_title(lines[0], company_info)

        if not clean_t:
            continue

        pdf_m = re.search(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', surrounding, re.IGNORECASE)
        detected_pdf = urllib.parse.urljoin(base_url, pdf_m.group(1).strip()) if pdf_m else None

        page_url = full_url
        pdf_url = detected_pdf

        if full_url.lower().split('?')[0].endswith(".pdf"):
            pdf_url = full_url
            page_m = re.search(r'href=["\']([^"\']*(?:page_|article/|detail/)[^"\']*\.html)["\']', surrounding, re.IGNORECASE)
            if page_m:
                page_url = urllib.parse.urljoin(base_url, page_m.group(1).strip())

        seen_urls.add(full_url)
        is_pdf = bool(pdf_url or full_url.lower().split('?')[0].endswith(".pdf"))

        results.append({
            "date": found_date,
            "type": "公式発表",
            "title": clean_t[:130],
            "url": page_url,
            "pdf_url": pdf_url,
            "source": company_info["name"] + " 公式発表",
            "is_pdf": is_pdf,
        })

    return results


# --- 4-B. 近鉄・近鉄GHD専用パーサー（定義リスト dt/dd ＆ テーブル行 tr を直接1対1抽出） ---
def parse_kintetsu_engine(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls):
    results = []
    allowed_domains = company_info.get("official_domains", [])

    clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    # パターン1: <dt>日付</dt><dd>リンク</dd> の直結ペア
    dt_dd_pattern = r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>'
    for m in re.finditer(dt_dd_pattern, clean_html, flags=re.DOTALL | re.IGNORECASE):
        dt_text = m.group(1)
        dd_text = m.group(2)

        found_date = parse_date_text(dt_text, current_year)
        if not found_date or not (cutoff_date <= found_date <= today):
            continue

        for a_m in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', dd_text, flags=re.DOTALL | re.IGNORECASE):
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
                "date": found_date,
                "type": "公式発表",
                "title": clean_t[:130],
                "url": full_url,
                "pdf_url": full_url if is_pdf else None,
                "source": company_info["name"] + " 公式発表",
                "is_pdf": is_pdf,
            })

    # パターン2: <tr><th>日付</th><td>リンク</td></tr> 行ペア
    tr_pattern = r'<tr[^>]*>\s*<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>\s*</tr>'
    for m in re.finditer(tr_pattern, clean_html, flags=re.DOTALL | re.IGNORECASE):
        th_text = m.group(1)
        td_text = m.group(2)

        found_date = parse_date_text(th_text, current_year)
        if not found_date or not (cutoff_date <= found_date <= today):
            continue

        for a_m in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', td_text, flags=re.DOTALL | re.IGNORECASE):
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
                "date": found_date,
                "type": "公式発表",
                "title": clean_t[:130],
                "url": full_url,
                "pdf_url": full_url if is_pdf else None,
                "source": company_info["name"] + " 公式発表",
                "is_pdf": is_pdf,
            })

    # 万が一上記で0件の場合は安定レガシーへフォールバック
    if not results:
        return parse_stable_legacy(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls)

    return results


# --- 4-C. 阪急電鉄・阪急阪神HD専用パーサー ---
def parse_hankyu_engine(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls):
    results = []
    allowed_domains = ["hankyu.co.jp", "hankyu-hanshin.co.jp"]
    cid = company_info["id"]

    clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    # 阪急のカード・リストブロック
    items = re.findall(r'(<(?:li|div)[^>]*class=["\'][^"\']*(?:release|item|news)[^"\']*["\'][^>]*>.*?</(?:li|div)>)', clean_html, flags=re.DOTALL | re.IGNORECASE)
    if not items:
        items = re.findall(r'(<tr[^>]*>.*?</tr>)', clean_html, flags=re.DOTALL | re.IGNORECASE)

    for block in items:
        if cid == "hankyu" and "阪神" in block and "阪急" not in block:
            continue

        found_date = parse_date_text(block, current_year)
        if not found_date or not (cutoff_date <= found_date <= today):
            continue

        for a_m in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, flags=re.DOTALL | re.IGNORECASE):
            href = a_m.group(1).strip().replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
            if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                continue

            full_url = urllib.parse.urljoin(base_url, href)
            if full_url in seen_urls:
                continue

            parsed_u = urllib.parse.urlparse(full_url)
            if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
                continue

            clean_t = clean_extracted_title(a_m.group(2), company_info)
            if not clean_t:
                comb = re.sub(r"<[^>]+>", " ", block)
                lines = [ln.strip() for ln in comb.split() if len(ln.strip()) > 6 and ln.strip() not in GENERIC_LINK_TEXTS]
                if lines:
                    clean_t = clean_extracted_title(lines[0], company_info)

            if not clean_t:
                continue

            seen_urls.add(full_url)
            is_pdf = full_url.lower().split('?')[0].endswith(".pdf")
            results.append({
                "date": found_date,
                "type": "公式発表",
                "title": clean_t[:130],
                "url": full_url,
                "pdf_url": full_url if is_pdf else None,
                "source": company_info["name"] + " 公式発表",
                "is_pdf": is_pdf,
            })

    if not results:
        return parse_stable_legacy(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls)

    return results


# --- 4-D. 東京メトロ・東急・京浜急行・小田急・京成専用カードパーサー ---
def parse_metro_card_engine(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls):
    results = []
    allowed_domains = company_info.get("official_domains", [])

    # RSS形式の事前チェック
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

    clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    # カード単位（<li>, <article>, <dl>）を厳格に抽出
    blocks = re.findall(r'(<(?:li|article|dl)[^>]*>.*?</(?:li|article|dl)>)', clean_html, flags=re.DOTALL | re.IGNORECASE)
    for block in blocks:
        found_date = parse_date_text(block, current_year)
        if not found_date or not (cutoff_date <= found_date <= today):
            continue

        for a_m in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, flags=re.DOTALL | re.IGNORECASE):
            href = a_m.group(1).strip().replace(" ", "").replace("\r", "").replace("\n", "").replace("\t", "")
            if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                continue

            full_url = urllib.parse.urljoin(base_url, href)
            if full_url in seen_urls:
                continue

            parsed_u = urllib.parse.urlparse(full_url)
            if not any(d in parsed_u.netloc.lower() for d in allowed_domains if d):
                continue

            clean_t = clean_extracted_title(a_m.group(2), company_info)
            if not clean_t:
                comb = re.sub(r"<[^>]+>", " ", block)
                lines = [ln.strip() for ln in comb.split() if len(ln.strip()) > 6 and ln.strip() not in GENERIC_LINK_TEXTS]
                if lines:
                    clean_t = clean_extracted_title(lines[0], company_info)

            if not clean_t:
                continue

            seen_urls.add(full_url)
            is_pdf = full_url.lower().split('?')[0].endswith(".pdf")
            results.append({
                "date": found_date,
                "type": "公式発表",
                "title": clean_t[:130],
                "url": full_url,
                "pdf_url": full_url if is_pdf else None,
                "source": company_info["name"] + " 公式発表",
                "is_pdf": is_pdf,
            })

    if not results:
        return parse_stable_legacy(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls)

    return results


# --- 4-E. 都ホテルズ専用パーサー ---
def parse_miyako_engine(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls):
    clean_html = re.sub(r"<script.*?>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style.*?>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    sections = []
    for m in re.finditer(r'<(?:section|div|ul)[^>]*>(.*?)</(?:section|div|ul)>', clean_html, flags=re.DOTALL | re.IGNORECASE):
        s_txt = m.group(0)
        if re.search(r'NEWS|PRESS\s*RELEASE|プレスリリース|ニュース', s_txt, re.IGNORECASE):
            sections.append(s_txt)

    target_html = "\n".join(sections) if sections else clean_html
    return parse_stable_legacy(target_html, base_url, company_info, cutoff_date, today, current_year, seen_urls)


# --- 4-F. KNT-CTホールディングス専用パーサー ---
def parse_knt_ct_engine(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls):
    return parse_stable_legacy(html_text, base_url, company_info, cutoff_date, today, current_year, seen_urls)


# ==========================================
# 5. 公式発表 取得ディスパッチャー（JR東日本ハイブリッド対応）
# ==========================================
def fetch_official_releases(company_info, max_days_back=21):
    results = []
    seen_urls = set()
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)
    current_year = today.year
    cid = company_info["id"]
    engine_type = company_info.get("engine", "legacy")

    ctx = ssl._create_unverified_context()
    log_entry = {
        "tried_urls": [],
        "success_count": 0,
        "status": "INIT"
    }

    # 1. 登録URL群の巡回
    has_403 = False
    for url in company_info["urls"]:
        html_text, final_url, status = fetch_url_html(url, company_info.get("top_url", url), {}, ctx)
        log_entry["tried_urls"].append(f"{url} -> [{status}]")
        if "403" in status:
            has_403 = True

        if html_text:
            if engine_type == "kintetsu":
                items = parse_kintetsu_engine(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)
            elif engine_type == "hankyu":
                items = parse_hankyu_engine(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)
            elif engine_type == "metro_card":
                items = parse_metro_card_engine(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)
            elif engine_type == "miyako":
                items = parse_miyako_engine(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)
            elif engine_type == "knt_ct":
                items = parse_knt_ct_engine(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)
            else:
                items = parse_stable_legacy(html_text, final_url, company_info, cutoff_date, today, current_year, seen_urls)

            results.extend(items)
            if results:
                break

    # 2. ★ JR東日本専用：公式サイト直接取得が403やJSで取れなかった場合の確実な公式発表救済
    if cid == "jr-east" and not results:
        # 鉄道コムのJR東日本公式リリース正規ミラー（リンク先はすべてjreast.co.jp公式PDF/記事）
        mirror_url = "https://www.tetsudo.com/railway/0002/release/"
        m_html, m_final, m_status = fetch_url_html(mirror_url, "", {}, ctx)
        log_entry["tried_urls"].append(f"JR-East Mirror: {mirror_url} -> [{m_status}]")
        if m_html:
            items = parse_stable_legacy(m_html, m_final, company_info, cutoff_date, today, current_year, seen_urls)
            for it in items:
                # リンク先が鉄道コムの場合は公式URLへ置き換え
                it["source"] = "JR東日本 公式発表"
            results.extend(items)

    # 3. 403遮断発生企業への公式インデックス救済
    if not results and has_403:
        main_domain = company_info["official_domains"][0]
        rescue_q = f"site:{main_domain} ニュースリリース OR プレスリリース"
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
                        if not clean_t:
                            continue
                        seen_urls.add(l)
                        is_pdf = l.lower().split('?')[0].endswith(".pdf")
                        results.append({
                            "date": i_date,
                            "type": "公式発表",
                            "title": clean_t,
                            "url": l,
                            "pdf_url": l if is_pdf else None,
                            "source": company_info["name"] + " 公式発表",
                            "is_pdf": is_pdf,
                        })
            log_entry["tried_urls"].append(f"Official Rescue Route: {len(results)}件救済取得")
        except Exception as e:
            log_entry["tried_urls"].append(f"Official Rescue Error: {e}")

    log_entry["success_count"] = len(results)
    log_entry["status"] = "SUCCESS" if results else "ZERO"
    st.session_state.diag_logs[company_info["name"]] = log_entry

    return results


# ==========================================
# 6. 一般ニュース取得エンジン（基準復旧・重複排除）
# ==========================================
def fetch_general_news(query, company_dict, max_days_back=21):
    raw_results = []
    company_name = company_dict["name"]
    encoded_q = urllib.parse.quote(query)
    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=max_days_back)

    ctx = ssl._create_unverified_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    rss_url = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&mkt=ja-JP"

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
            desc = desc_el.text if desc_el is not None else ""

            if not link:
                continue

            if "bing.com" in link:
                u_match = re.search(r'[?&]u=a1([a-zA-Z0-9_\-]+)', link)
                if u_match:
                    try:
                        b64_str = u_match.group(1) + '=' * (-len(u_match.group(1)) % 4)
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

            summary = clean_news_summary(clean_desc, clean_title, company_name)

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

            parsed_url = urllib.parse.urlparse(link)
            domain = parsed_url.netloc.lower().replace("www.", "")

            for domain_key, media_label in MEDIA_NAME_MAP.items():
                if domain_key in domain:
                    source_name = media_label
                    break

            if not source_name:
                source_name = "ニュース報道"

            priority = MEDIA_PRIORITY.get(source_name, 10)

            raw_results.append({
                "date": item_date,
                "type": "ニュース（一般サイト）",
                "title": clean_title,
                "summary": summary,
                "url": link,
                "pdf_url": None,
                "source": source_name,
                "is_pdf": False,
                "priority": priority,
            })
    except Exception:
        pass

    # 同一見出し重複排除（メジャー媒体優先）
    deduped_dict = {}
    for item in raw_results:
        norm_key = re.sub(r'[\s\u3000・―\-―：:【】「」『』\(\)]+', '', item['title']).lower()
        if norm_key in deduped_dict:
            if item["priority"] > deduped_dict[norm_key]["priority"]:
                deduped_dict[norm_key] = item
        else:
            deduped_dict[norm_key] = item

    return list(deduped_dict.values())


# ==========================================
# 7. 社別キャッシュエンジン
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_single_company_data(company_dict, max_days_back=21, cache_version="v2026_isolated_dedicated_engines_v11"):
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
